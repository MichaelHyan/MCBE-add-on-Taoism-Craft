#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_guide_interact.py —— 根据 guide_interact.md 生成 entity:guide 的交互项与 say 事件

源文件每行一条:
    items:cinnabar_crystal-朱砂啊，夜里多走走，兴许就懂了。

生成结果（写入 Taoism_B/entities/guide.json）:
    1) components["minecraft:interact"]["interactions"] 追加一条交互项
       （1.16+/1.26.0 结构；has_equipment: hand = 物品id  +  is_family: player）
    2) events 追加一条 queue_command -> "say <交互文本>"

约定:
    - 生成的事件名统一前缀 "guide_say_"，便于识别与清理（脚本可重复运行，幂等）
    - 新交互项追加在原交互项之后：原有装备交互优先级不变，不会被新条目抢走
    - 写入前会先删除上次生成的内容，避免重复堆积
    - 默认跳过"已被原有交互抢先匹配"的物品（minecraft:interact 首匹配生效，
      这些物品即使生成也不会触发），可用 --include-shadowed 强制生成
    - 兼容 interact 的两种结构：1.16+/1.26.0 的 {"interactions": [...]}
      与 1.8.0 的裸数组 [ ... ]；写回时统一采用新结构

用法:
    python gen_guide_interact.py                # 生成并写入
    python gen_guide_interact.py --dry-run      # 只统计/预览，不写文件
    python gen_guide_interact.py --backup       # 写入前备份为 guide.json.bak
    python gen_guide_interact.py --revert       # 只删除脚本生成的内容
    python gen_guide_interact.py --include-shadowed   # 不跳过被遮挡的物品

注意:
    - 行格式以首个 "-" 切分，物品 id 必须形如 namespace:name，
      若文本中本身含 "-" 不影响；但 id 自身若含 "-" 会被切错，脚本会告警跳过。
    - 脚本会重排 JSON 缩进（2 空格），首次运行 diff 可能较大，属正常。
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile

# ---------------------------------------------------------------- 路径与常量

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_MD = os.path.join(BASE_DIR, 'Taoism_B', 'lines', 'guide_interact.md')
DEFAULT_JSON = os.path.join(BASE_DIR, 'Taoism_B', 'entities', 'guide.json')

EVENT_PREFIX = 'guide_say_'
INTERACT_TEXT = 'addon.get.items'

# 合法的 MCBE 物品标识符: namespace:name
ID_RE = re.compile(r'^[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+$')

# ---------------------------------------------------------------- 基础工具


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data, backup=False):
    """原子替换写入，避免写一半损坏文件。"""
    if backup and os.path.isfile(path):
        bak = path + '.bak'
        shutil.copy2(path, bak)
        print('[OK] 已备份: %s' % bak)

    folder = os.path.dirname(path) or '.'
    fd, tmp = tempfile.mkstemp(prefix='.guide_', suffix='.json', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def slug(text):
    """把物品 id 洗成事件名可用的字符: items:cinnabar_crystal -> items_cinnabar_crystal"""
    return re.sub(r'[^0-9A-Za-z_]', '_', text)


def clean_text(text):
    """清理会破坏 say 命令的字符。"""
    t = text.replace('\\', '')
    t = t.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
    return re.sub(r'[ \u3000]{2,}', ' ', t).strip()


def _event_name_of(entry):
    """取出交互项上的 event 名，非预期结构返回空串。"""
    if not isinstance(entry, dict):
        return ''
    on_int = entry.get('on_interact')
    if not isinstance(on_int, dict):
        return ''
    ev = on_int.get('event', '')
    return ev if isinstance(ev, str) else ''


# ---------------------------------------------------------------- md 解析


def _split_id_text(line):
    if '-' not in line:
        return None, None
    left, right = line.split('-', 1)
    left, right = left.strip(), right.strip()
    if not ID_RE.match(left):
        return None, None
    return left, right


def parse_md(path):
    """返回 (records, duplicates, bad)。records 元素为 (item_id, text, lineno)。"""
    records, duplicates, bad = [], [], []
    seen = {}

    with open(path, 'r', encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue
            if '-' not in line:
                bad.append((lineno, line, '缺少分隔符 "-"'))
                continue
            item_id, text = _split_id_text(line)
            if item_id is None:
                bad.append((lineno, line, '物品 id 不合法，无法按首个 "-" 切分'))
                continue
            if not text:
                bad.append((lineno, line, '交互文本为空'))
                continue
            if item_id in seen:
                duplicates.append((item_id, seen[item_id], lineno))
                continue
            seen[item_id] = lineno
            records.append((item_id, text, lineno))

    return records, duplicates, bad


# ---------------------------------------------------------------- 生成/清理


def make_interact(item_id, event_name):
    return {
        "on_interact": {
            "filters": {
                "all_of": [
                    {
                        "test": "has_equipment",
                        "subject": "other",
                        "domain": "hand",
                        "value": item_id,
                    },
                    {
                        "test": "is_family",
                        "subject": "other",
                        "value": "player",
                    },
                ]
            },
            "event": event_name,
        },
        "use_item": False,
        "interact_text": INTERACT_TEXT,
    }


def make_event(text):
    return {"queue_command": {"command": "say " + text, "target": "self"}}


def unique_event_name(events, base):
    name, i = base, 2
    while name in events:
        name = '%s_%d' % (base, i)
        i += 1
    return name


def _unwrap_interact(raw):
    """把 minecraft:interact 解包成 (entries, holder)。

    holder 取值:
        'wrapped' -> 1.16+/1.26.0: {"interactions": [...]}
        'list'    -> 1.8.0 旧数组: [ ... ]
        'single'  -> 1.8.0 单对象: { ... }
    其他情况返回 (None, None)。
    """
    if isinstance(raw, dict) and isinstance(raw.get('interactions'), list):
        return raw['interactions'], 'wrapped'
    if isinstance(raw, list):
        return raw, 'list'
    if isinstance(raw, dict):
        return [raw], 'single'
    return None, None


def _wrap_interact(entries, holder):
    """按原结构（或新结构）重新包装 interact，返回新的 component 值或 None。"""
    if not entries:
        return None
    if holder == 'single':
        return entries[0]
    if holder == 'list':
        return entries
    return {'interactions': entries}


def remove_generated(entity):
    """删除所有由本脚本生成的 interact 项与事件，返回 (事件数, 交互数)。

    兼容两种 interact 结构，清理后按原结构写回（新结构保持 wrapped 形式）。
    """
    removed_ev = 0
    removed_it = 0

    events = entity.get('events')
    if isinstance(events, dict):
        for key in list(events.keys()):
            if key.startswith(EVENT_PREFIX):
                del events[key]
                removed_ev += 1

    components = entity.get('components')
    if isinstance(components, dict):
        raw = components.get('minecraft:interact')
        if raw is None:
            return removed_ev, removed_it

        entries, holder = _unwrap_interact(raw)
        if entries is None:
            return removed_ev, removed_it

        kept = []
        for entry in entries:
            if _event_name_of(entry).startswith(EVENT_PREFIX):
                removed_it += 1
                continue
            kept.append(entry)

        new_val = _wrap_interact(kept, holder)
        if new_val is None:
            components.pop('minecraft:interact', None)
        else:
            components['minecraft:interact'] = new_val

    return removed_ev, removed_it


def collect_hand_values(interact_list):
    """收集已有交互项里 has_equipment(hand) 的所有 value，用于判定物品是否被遮挡。"""
    values = set()
    for entry in interact_list:
        if not isinstance(entry, dict):
            continue
        filters = entry.get('on_interact', {}).get('filters')
        if not isinstance(filters, dict):
            continue
        if 'all_of' in filters:
            conds = filters['all_of']
        elif 'any_of' in filters:
            conds = filters['any_of']
        else:
            conds = [filters]
        if isinstance(conds, dict):
            conds = [conds]
        for cond in conds:
            if not isinstance(cond, dict):
                continue
            if cond.get('test') != 'has_equipment':
                continue
            val = cond.get('value')
            if isinstance(val, str):
                values.add(val)
            elif isinstance(val, list):
                values.update(str(v) for v in val)
    return values


# ---------------------------------------------------------------- 主流程


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='gen_guide_interact.py',
        description='根据 guide_interact.md 生成 entity:guide 的交互项与 say 事件')
    ap.add_argument('--md', default=DEFAULT_MD,
                    help='交互文本源文件 (默认: %(default)s)')
    ap.add_argument('--json', dest='json_path', default=DEFAULT_JSON,
                    help='目标实体文件 (默认: %(default)s)')
    ap.add_argument('--dry-run', action='store_true',
                    help='只统计与预览，不写入文件')
    ap.add_argument('--backup', action='store_true',
                    help='写入前把原文件备份为 guide.json.bak')
    ap.add_argument('--revert', action='store_true',
                    help='只删除脚本生成的内容，不重新生成')
    ap.add_argument('--include-shadowed', action='store_true',
                    help='不跳过"已被原有交互抢先匹配"的物品（默认跳过）')
    args = ap.parse_args(argv)

    for path in (args.md, args.json_path):
        if not os.path.isfile(path):
            print('[ERR] 文件不存在: %s' % path)
            return 2

    try:
        data = load_json(args.json_path)
    except ValueError as exc:
        print('[ERR] JSON 解析失败: %s' % exc)
        return 2

    entity = data.get('minecraft:entity')
    if not isinstance(entity, dict):
        print('[ERR] 未找到 minecraft:entity 节点')
        return 2

    components = entity.setdefault('components', {})
    events = entity.setdefault('events', {})

    removed_ev, removed_it = remove_generated(entity)
    print('[INFO] 清理上次生成内容: 事件 %d 条 / 交互 %d 条' % (removed_ev, removed_it))

    if args.revert:
        if args.dry_run:
            print('[DRY-RUN] 未写入文件。')
            return 0
        save_json(args.json_path, data, backup=args.backup)
        print('[OK] 已清除生成内容并写回: %s' % args.json_path)
        return 0

    records, duplicates, bad = parse_md(args.md)
    print('[INFO] 解析源文件: 有效 %d 条 / 重复 %d 条 / 异常 %d 条'
          % (len(records), len(duplicates), len(bad)))

    for item_id, first, cur in duplicates:
        print('[WARN] 重复 id %r 已忽略 (首次第 %d 行, 重复第 %d 行)'
              % (item_id, first, cur))
    for lineno, line, why in bad:
        print('[WARN] 第 %d 行已跳过: %s | %s' % (lineno, why, line))

    # 取出（并规范化）现有交互列表 —— 内部统一为 list
    raw_interact = components.get('minecraft:interact')
    if raw_interact is None:
        interact = []
    elif isinstance(raw_interact, dict) and isinstance(raw_interact.get('interactions'), list):
        # 1.16+ / 1.26.0 新结构
        interact = list(raw_interact['interactions'])
    elif isinstance(raw_interact, dict):
        interact = [raw_interact]
    elif isinstance(raw_interact, list):
        interact = list(raw_interact)
    else:
        print('[ERR] minecraft:interact 类型异常: %s, 请手动检查'
              % type(raw_interact).__name__)
        return 2

    occupied = collect_hand_values(interact)
    shadowed = []
    created = 0

    for item_id, text, lineno in records:
        # 原有交互首匹配生效，被遮挡的物品即使生成也不会触发
        if item_id in occupied:
            shadowed.append((item_id, lineno))
            if not args.include_shadowed:
                continue

        if '@' in text:
            print('[WARN] 第 %d 行文本含 "@"，say 中可能被当作选择器: %r'
                  % (lineno, text))

        base = EVENT_PREFIX + slug(item_id)
        event_name = unique_event_name(events, base)
        events[event_name] = make_event(clean_text(text))
        interact.append(make_interact(item_id, event_name))
        created += 1

    if not interact:
        components.pop('minecraft:interact', None)
    else:
        # 1.16+ / 1.26.0 结构：{ "interactions": [...] }
        components['minecraft:interact'] = {'interactions': interact}

    print('[INFO] 生成交互项 %d 条 / say 事件 %d 条' % (created, created))

    if shadowed:
        if args.include_shadowed:
            print('[WARN] 以下 %d 个物品已被原有交互抢先匹配，'
                  '生成的 say 不会触发:' % len(shadowed))
        else:
            print('[INFO] 已跳过 %d 个被原有交互抢占的物品（不生成 say）:'
                  % len(shadowed))
        for item_id, lineno in shadowed:
            print('       - %-40s (源文件第 %d 行)' % (item_id, lineno))

    if args.dry_run:
        if created:
            demo_id, demo_text, _ = [r for r in records
                                     if r[0] not in shadowed_ids(shadowed)
                                     or args.include_shadowed][0]
            demo_ev = EVENT_PREFIX + slug(demo_id)
            demo = {
                'interact': make_interact(demo_id, demo_ev),
                'events': {demo_ev: make_event(clean_text(demo_text))},
            }
            print('[DRY-RUN] 首条生成示例:')
            print(json.dumps(demo, ensure_ascii=False, indent=2))
        print('[DRY-RUN] 未写入文件。')
        return 0

    save_json(args.json_path, data, backup=args.backup)
    print('[OK] 已写入: %s' % args.json_path)
    return 0


def shadowed_ids(shadowed):
    return set(item_id for item_id, _ in shadowed)


if __name__ == '__main__':
    sys.exit(main())