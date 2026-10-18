#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcstructure format_version 2 -> 1 降级工具
==========================================

背景
----
基岩版 26.x 某次更新后，结构方块导出的 .mcstructure 使用 format_version = 2：

    format_version = 2
    structure.block_indices = List<IntArray>        # 整块 int 数组

旧版客户端（format_version = 1）期望：

    format_version = 1
    structure.block_indices = List<List<Int>>       # 两层：方块层 + 液体层

两层含义
--------
layer0 = 方块层，值是 palette 索引
layer1 = 液体层，值是 palette 索引

关键：-1 不等于 air
--------------------
    -1        放置结构时跳过该格，保留目标位置原有方块（结构空位行为）
    air 索引  放置空气，会清除目标位置原有方块

因此转换时必须原样保留 layer0 里的 -1，绝不能替换成 minecraft:air 的索引，
否则结构空位会变成空气、把建筑周围的地形一并挖掉。

旧客户端读到高于自身支持的 format_version 时会直接拒绝整个文件
（连 palette 都不解析），表现为「结构完全加载不出来 / 手机版打不开」。
这与建筑里放了什么方块无关 —— 纯原版方块同样会失败。

用法
----
    python downgrade_mcstructure.py                      # 处理脚本所在目录
    python downgrade_mcstructure.py <目录>               # 处理指定目录
    python downgrade_mcstructure.py <目录> --dry-run     # 只预演，不写文件
    python downgrade_mcstructure.py <目录> --verify-only # 只校验，不转换
    python downgrade_mcstructure.py <目录> --no-backup   # 跳过备份（不建议）

特性
----
* 幂等：只处理 format_version == 2 的文件，已是 1 的直接跳过。
  反复运行不会重复补层。
* 自动备份：转换前把原文件复制到 <目录>/_fv2_backup/
* 转后自检：重新解析并逐项校验层数、长度、索引范围。
* 层数自适应：
    - 单层文件（只有方块层）  -> 补一层全 -1 的液体层
    - 双层文件（方块层+液体层）-> 保留原液体层，绝不丢弃已有的水
* 只改容器编码，不动 palette 方块内容 / 方块实体 / entities / 坐标。

退出码：全部成功 0，有失败 1
"""

import argparse
import glob
import os
import shutil
import struct
import sys

# ---------------------------------------------------------------- NBT 读取

class Reader(object):
    __slots__ = ("data", "pos")

    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        v = self.data[self.pos:self.pos + n]
        if len(v) != n:
            raise ValueError("unexpected EOF at offset %d" % self.pos)
        self.pos += n
        return v

    def u8(self):
        return self.take(1)[0]

    def i16(self):
        return struct.unpack("<h", self.take(2))[0]

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def i64(self):
        return struct.unpack("<q", self.take(8))[0]

    def f32(self):
        return struct.unpack("<f", self.take(4))[0]

    def f64(self):
        return struct.unpack("<d", self.take(8))[0]

    def string(self):
        n = self.i16()
        return self.take(n).decode("utf-8", "replace")


def _read_payload(r, t):
    """按 tag 类型 t 读取 payload。返回内部表示：
       compound -> ('compound', [(name, type, value), ...])
       list     -> ('list', elem_type, [values])
       int_arr  -> ('int_array', [ints])
       long_arr -> ('long_array', [longs])
       其它     -> 标量
    """
    if t == 1:
        return r.u8()
    if t == 2:
        return r.i16()
    if t == 3:
        return r.i32()
    if t == 4:
        return r.i64()
    if t == 5:
        return r.f32()
    if t == 6:
        return r.f64()
    if t == 7:
        return r.take(r.i32())
    if t == 8:
        return r.string()
    if t == 9:
        et = r.u8()
        n = r.i32()
        return ("list", et, [_read_payload(r, et) for _ in range(n)])
    if t == 10:
        items = []
        while True:
            tt = r.u8()
            if tt == 0:          # TAG_End
                break
            name = r.string()
            items.append((name, tt, _read_payload(r, tt)))
        return ("compound", items)
    if t == 11:
        n = r.i32()
        return ("int_array", [r.i32() for _ in range(n)])
    if t == 12:
        n = r.i32()
        return ("long_array", [r.i64() for _ in range(n)])
    raise ValueError("unknown tag type %d" % t)


def parse(path):
    with open(path, "rb") as f:
        data = f.read()
    r = Reader(data)
    t = r.u8()
    if t != 10:
        raise ValueError("root tag is not TAG_Compound (got %d)" % t)
    r.string()                   # 根节点名字，通常为空
    return _read_payload(r, 10)


# ---------------------------------------------------------------- NBT 写出

def _write_string(s):
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b


def _write_payload(t, v):
    if t == 1:
        return struct.pack("<b", v - 256 if v > 127 else v)
    if t == 2:
        return struct.pack("<h", v)
    if t == 3:
        return struct.pack("<i", v)
    if t == 4:
        return struct.pack("<q", v)
    if t == 5:
        return struct.pack("<f", v)
    if t == 6:
        return struct.pack("<d", v)
    if t == 7:
        return struct.pack("<i", len(v)) + v
    if t == 8:
        return _write_string(v)
    if t == 9:
        et, items = v[1], v[2]
        out = [bytes([et]), struct.pack("<i", len(items))]
        for item in items:
            out.append(_write_payload(et, item))
        return b"".join(out)
    if t == 10:
        out = []
        for name, tt, vv in v[1]:
            out.append(bytes([tt]))
            out.append(_write_string(name))
            out.append(_write_payload(tt, vv))
        out.append(b"\x00")
        return b"".join(out)
    if t == 11:
        out = [struct.pack("<i", len(v[1]))]
        for x in v[1]:
            out.append(struct.pack("<i", x))
        return b"".join(out)
    if t == 12:
        out = [struct.pack("<i", len(v[1]))]
        for x in v[1]:
            out.append(struct.pack("<q", x))
        return b"".join(out)
    raise ValueError("cannot write tag type %d" % t)


def serialize(root):
    # 裸 NBT：TAG_Compound + 空名字 + payload。没有魔数，没有压缩。
    return b"\x0a" + _write_string("") + _write_payload(10, root)


def save(path, root):
    with open(path, "wb") as f:
        f.write(serialize(root))


# ---------------------------------------------------------------- 字段工具

def get_field(compound, key):
    """在 compound 里找 key，返回 (type, value)；找不到返回 None。"""
    for name, t, v in compound[1]:
        if name == key:
            return t, v
    return None


def set_field(compound, key, t, v):
    """就地替换 compound 里的 key；不存在则追加。"""
    for i, (name, _, _) in enumerate(compound[1]):
        if name == key:
            compound[1][i] = (name, t, v)
            return True
    compound[1].append((key, t, v))
    return False


def get_layers(structure):
    """返回 (layers, outer_elem_type)。layers 是 [[int,...], ...]。"""
    t, bi = get_field(structure, "block_indices")
    elem_type = bi[1]
    layers = []
    for item in bi[2]:
        kind = item[0]
        if kind == "int_array":
            layers.append(list(item[1]))
        elif kind == "list":
            layers.append(list(item[2]))
        else:
            raise ValueError("unexpected block_indices element: %r" % (kind,))
    return layers, elem_type


def get_palette(structure):
    """返回 (names, block_palette_compound)。"""
    _, pal = get_field(structure, "palette")
    _, default = get_field(pal, "default")
    _, bp = get_field(default, "block_palette")
    names = []
    for entry in bp[2]:
        _, nm = get_field(entry, "name")
        names.append(nm)
    return names, bp


# ---------------------------------------------------------------- 转换逻辑

def is_v2(root):
    f = get_field(root, "format_version")
    return f is not None and f[1] == 2


def downgrade(root):
    """把 fv=2 的 root 就地改成 fv=1。返回描述信息 dict。

    只改容器编码：
        format_version      2 -> 1
        block_indices       List<IntArray> -> List<List<Int>>
        图层值               原样保留（包括 -1）
        缺失的液体层         补一层全 -1
    """
    _, size = get_field(root, "size")
    sx, sy, sz = size[2]
    cells = sx * sy * sz

    _, structure = get_field(root, "structure")
    layers, _ = get_layers(structure)
    if not layers:
        raise ValueError("block_indices is empty")
    for l in layers:
        if len(l) != cells:
            raise ValueError("layer length %d != cells %d" % (len(l), cells))

    names, _ = get_palette(structure)

    # 原样保留 layer0：
    #   -1 是结构空位（放置时跳过），不是 air（放置时会清除方块）。
    #   把所有 -1 换成 air 索引会导致结构空位变成空气。
    layer0 = list(layers[0])

    # 层1：有就保留（保住已有的水），没有就补全 -1
    if len(layers) >= 2:
        layer1 = list(layers[1])
        liquid_kept = sum(1 for x in layer1 if x != -1)
    else:
        layer1 = [-1] * cells
        liquid_kept = 0

    set_field(structure, "block_indices", 9,
              ("list", 9, [("list", 3, layer0), ("list", 3, layer1)]))
    set_field(root, "format_version", 3, 1)

    return {
        "cells": cells,
        "palette": len(names),
        "kept_void": sum(1 for x in layer0 if x == -1),
        "liquid_kept": liquid_kept,
        "layers_before": len(layers),
    }


def check(root):
    """校验是否为合法的 fv=1 结构。返回 (ok, 说明)。"""
    f = get_field(root, "format_version")
    if f is None or f[1] != 1:
        return False, "format_version != 1"

    _, size = get_field(root, "size")
    sx, sy, sz = size[2]
    cells = sx * sy * sz

    _, structure = get_field(root, "structure")
    t, bi = get_field(structure, "block_indices")
    if bi[1] != 9:
        return False, "block_indices elem_type=%d (expect 9)" % bi[1]
    if len(bi[2]) != 2:
        return False, "layers=%d (expect 2)" % len(bi[2])

    l0 = list(bi[2][0][2])
    l1 = list(bi[2][1][2])
    if len(l0) != cells or len(l1) != cells:
        return False, "layer length %d/%d != cells %d" % (len(l0), len(l1), cells)

    names, _ = get_palette(structure)
    n = len(names)
    # v1 里 -1（结构空位）是合法值，且原生导出会与 air 索引混用
    for x in l0:
        if x != -1 and not (0 <= x < n):
            return False, "layer0 index %d out of palette range %d" % (x, n)
    for x in l1:
        if x != -1 and not (0 <= x < n):
            return False, "layer1 index %d out of palette range %d" % (x, n)

    return True, "ok"


def cell_names(root):
    """展开成每格的方块名 / 液体名，用于逐格比对。

    -1 返回 None，表示结构空位（放置时跳过），不是空气。
    """
    _, structure = get_field(root, "structure")
    layers, _ = get_layers(structure)
    names, _ = get_palette(structure)

    def nm(i):
        if i == -1:
            return None
        return names[i] if 0 <= i < len(names) else "?OUT_OF_RANGE_%d" % i

    blocks = [nm(i) for i in layers[0]]
    if len(layers) >= 2:
        liquids = [nm(x) for x in layers[1]]
    else:
        liquids = [None] * len(blocks)
    return blocks, liquids


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(
        description="Downgrade mcstructure format_version 2 -> 1")
    ap.add_argument("target", nargs="?", default=None,
                    help="directory to process (default: this script's directory)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    ap.add_argument("--verify-only", action="store_true",
                    help="only validate existing files, do not convert")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip backup to _fv2_backup/ (not recommended)")
    args = ap.parse_args()

    target = args.target or os.path.dirname(os.path.abspath(__file__))
    target = os.path.abspath(target)
    if not os.path.isdir(target):
        print("ERROR: not a directory: %s" % target)
        return 1

    files = sorted(glob.glob(os.path.join(target, "*.mcstructure")))
    if not files:
        print("No .mcstructure files found in %s" % target)
        return 0

    backup_dir = os.path.join(target, "_fv2_backup")
    print("Directory : %s" % target)
    print("Files     : %d" % len(files))
    print("Mode      : %s" % ("verify-only" if args.verify_only
                              else ("dry-run" if args.dry_run else "convert")))
    print("")

    converted = skipped = failed = 0

    for path in files:
        name = os.path.basename(path)
        try:
            root = parse(path)
        except Exception as exc:
            print("  FAIL  %-32s parse error: %s" % (name, exc))
            failed += 1
            continue

        f = get_field(root, "format_version")
        fv = f[1] if f else None

        if args.verify_only:
            ok, msg = check(root)
            print("  %-5s %-32s fv=%s  %s"
                  % ("OK" if ok else "BAD", name, fv, msg))
            if not ok:
                failed += 1
            else:
                converted += 1
            continue

        if fv != 2:
            print("  SKIP  %-32s fv=%s (already compatible)" % (name, fv))
            skipped += 1
            continue

        if args.dry_run:
            _, size = get_field(root, "size")
            sx, sy, sz = size[2]
            _, structure = get_field(root, "structure")
            layers, _ = get_layers(structure)
            names, _ = get_palette(structure)
            void = sum(1 for x in layers[0] if x == -1)
            print("  WOULD %-32s fv=2 layers=%d cells=%d palette=%d void=%d -> fv=1 layers=2"
                  % (name, len(layers), sx * sy * sz, len(names), void))
            converted += 1
            continue

        # 备份
        if not args.no_backup:
            if not os.path.isdir(backup_dir):
                os.makedirs(backup_dir)
            bak = os.path.join(backup_dir, name)
            if not os.path.exists(bak):
                shutil.copy2(path, bak)

        try:
            info = downgrade(root)
            save(path, root)
        except Exception as exc:
            print("  FAIL  %-32s convert error: %s" % (name, exc))
            failed += 1
            continue

        # 转后自检
        try:
            again = parse(path)
            ok, msg = check(again)
        except Exception as exc:
            print("  FAIL  %-32s verify parse error: %s" % (name, exc))
            failed += 1
            continue

        print("  %-5s %-32s cells=%-6d pal=%-3d void=%-5d liquid=%-3d layers=%d->2  %s"
              % ("OK" if ok else "BAD", name, info["cells"], info["palette"],
                 info["kept_void"], info["liquid_kept"], info["layers_before"], msg))
        if ok:
            converted += 1
        else:
            failed += 1

    print("")
    print("Summary: converted=%d skipped=%d failed=%d" % (converted, skipped, failed))
    if not args.no_backup and not args.dry_run and not args.verify_only:
        print("Backup : %s" % backup_dir)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())