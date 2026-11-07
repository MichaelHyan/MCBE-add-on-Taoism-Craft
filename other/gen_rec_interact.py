#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_rec_interact.py —— 根据 rec_list.md 生成 entity:rec 的交互项与加分事件

源文件每行一条:
    diamond 1000
    iron_ingot 100

生成结果（写入 Taoism_B/entities/rec.json）:
    1) components["minecraft:interact"]["interactions"] 追加一条交互项
       （1.16+/1.26.0 结构；has_equipment: hand = 物品id + is_family: player）
    2) events 追加一条 queue_command，内含两条指令（数组）:
         scoreboard players add @p rec_point <数字>
         particle minecraft:totem_particle ~ ~1 ~

约定:
    - 事件名统一前缀 "rec_add_"，便于识别与清理（脚本可重复运行，幂等）
    - queue_command 的 target 为 "self"：由 rec 实体执行，@p 即最近的玩家，
      粒子落在实体自身位置
    - 物品 id 不含 ":" 时自动补 "minecraft:"；已带命名空间的原样保留
    - 写入前会先删除上次生成的内容，避免重复堆积
    - 兼容 interact 的两种结构：{"interactions": [...]} 与旧裸数组；
      写回时统一采用新结构

用法:
    python gen_rec_interact.py                    # 生成并写入
    python gen_rec_interact.py --dry-run          # 只统计/预览，不写文件
    python gen_rec_interact.py --backup           # 写入前备份为 rec.json.bak
    python gen_rec_interact.py --revert           # 只删除脚本生成的内容
    python gen_rec_interact.py --objective my_obj # 自定义计分板（默认 rec_point）

注意:
    - 行格式为 "<物品id> <整数>"，以最后一个空白切分，行尾多余空格会被忽略
    - 已知拼写可疑项只告警不改写（改源文件即可）
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ---------------------------------------------------------------- 路径与常量

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_MD = os.path.join(BASE_DIR, 'Taoism_B', 'lines', 'rec_list.md')
DEFAULT_JSON = os.path.join(BASE_DIR, 'Taoism_B', 'entities', 'rec.json')

EVENT_PREFIX = 'rec_add_'
INTERACT_TEXT = 'addon.get.items'
DEFAULT_OBJECTIVE = 'rec_point'
PARTICLE = 'minecraft:totem_particle'

# <物品id> <整数>
LINE_RE = re.compile(r'^(\S+)\s+(-?\d+)$')

# 疑似拼写问题：只告警，不改写
KNOWN_TYPOS = {
    'minecraft:breetroot': 'minecraft:beetroot',
    'minecraft:breetroot_seeds': 'minecraft:beetroot_seeds',
    'minecraft:dispensor': 'minecraft:dispenser',
}

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
    fd, tmp = tempfile.mkstemp(prefix='.rec_', suffix='.json', dir=folder)
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
    """把物品 id 洗成事件名可用的字符: minecraft:iron_ingot -> minecraft_iron_ingot"""
    return re.sub(r'[^0-9A-Za-z_]', '_', text)


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


def parse_md(path):
    """返回 (records, duplicates, bad, typos)。

    records 元素为 (item_id, score, lineno)，item_id 已补全命名空间。
    """
    records, duplicates, bad, typos = [], [], [], []
    seen = {}

    with open(path, 'r', encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue
            m = LINE_RE.match(line)
            if not m:
                bad.append((lineno, line, '格式应为 "<物品id> <整数>"'))
                continue
            item_id, score = m.group(1), int(m.group(2))
            if ':' not in item_id:
                item_id = 'minecraft:' + item_id
            if item_id in KNOWN_TYPOS:
                typos.append((lineno, item_id, KNOWN_TYPOS[item_id]))
            if item_id in seen:
                duplicates.append((item_id, seen[item_id], lineno))
                continue
            seen[item_id] = lineno
            records.append((item_id, score, lineno))

    return records, duplicates, bad, typos


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
        "use_item": True,
        "interact_text": INTERACT_TEXT,
    }


def make_event(score, objective):
    return {
        "queue_command": {
            "command": [
                "scoreboard players add @p %s %d" % (objective, score),
                "particle %s ~ ~1 ~" % PARTICLE,
            ],
            "target": "self",
        }
    }


def unique_event_name(events, base):
    name, i = base, 2
    while name in events:
        name = '%s_%d' % (base, i)
        i += 1
    return name


def _unwrap_interact(raw):
    """把 minecraft:interact 解包成 (entries, holder)。"""
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
    """删除所有由本脚本生成的 interact 项与事件，返回 (事件数, 交互数)。"""
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
        prog='gen_rec_interact.py',
        description='根据 rec_list.md 生成 entity:rec 的交互项与加分事件')
    ap.add_argument('--md', default=DEFAULT_MD,
                    help='物品/分值源文件 (默认: %(default)s)')
    ap.add_argument('--json', dest='json_path', default=DEFAULT_JSON,
                    help='目标实体文件 (默认: %(default)s)')
    ap.add_argument('--objective', default=DEFAULT_OBJECTIVE,
                    help='计分板 objective 名 (默认: %(default)s)')
    ap.add_argument('--dry-run', action='store_true',
                    help='只统计与预览，不写入文件')
    ap.add_argument('--backup', action='store_true',
                    help='写入前把原文件备份为 rec.json.bak')
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

    records, duplicates, bad, typos = parse_md(args.md)
    print('[INFO] 解析源文件: 有效 %d 条 / 重复 %d 条 / 异常 %d 条'
          % (len(records), len(duplicates), len(bad)))

    for item_id, first, cur in duplicates:
        print('[WARN] 重复 id %r 已忽略 (首次第 %d 行, 重复第 %d 行)'
              % (item_id, first, cur))
    for lineno, line, why in bad:
        print('[WARN] 第 %d 行已跳过: %s | %s' % (lineno, why, line))
    for lineno, item_id, guess in typos:
        print('[WARN] 第 %d 行 %r 疑似拼写有误，应为 %r，照原样生成'
              % (lineno, item_id, guess))

    # 取出（并规范化）现有交互列表 —— 内部统一为 list
    raw_interact = components.get('minecraft:interact')
    if raw_interact is None:
        interact = []
    elif isinstance(raw_interact, dict) and isinstance(raw_interact.get('interactions'), list):
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

    for item_id, score, lineno in records:
        # 原有交互首匹配生效，被遮挡的物品即使生成也不会触发
        if item_id in occupied:
            shadowed.append((item_id, lineno))
            if not args.include_shadowed:
                continue

        base = EVENT_PREFIX + slug(item_id)
        event_name = unique_event_name(events, base)
        events[event_name] = make_event(score, args.objective)
        interact.append(make_interact(item_id, event_name))
        created += 1

    if not interact:
        components.pop('minecraft:interact', None)
    else:
        components['minecraft:interact'] = {'interactions': interact}

    print('[INFO] 生成交互项 %d 条 / 事件 %d 条 (objective=%s)'
          % (created, created, args.objective))

    if shadowed:
        if args.include_shadowed:
            print('[WARN] 以下 %d 个物品已被原有交互抢先匹配，'
                  '生成的加分不会触发:' % len(shadowed))
        else:
            print('[INFO] 已跳过 %d 个被原有交互抢占的物品（不生成）:'
                  % len(shadowed))
        for item_id, lineno in shadowed:
            print('       - %-40s (源文件第 %d 行)' % (item_id, lineno))

    if args.dry_run:
        if created:
            demo = None
            for item_id, score, lineno in records:
                if not args.include_shadowed and item_id in occupied:
                    continue
                demo_ev = EVENT_PREFIX + slug(item_id)
                demo = {
                    'interact': make_interact(item_id, demo_ev),
                    'events': {demo_ev: make_event(score, args.objective)},
                }
                break
            if demo:
                print('[DRY-RUN] 首条生成示例:')
                print(json.dumps(demo, ensure_ascii=False, indent=2))
        print('[DRY-RUN] 未写入文件。')
        return 0

    save_json(args.json_path, data, backup=args.backup)
    print('[OK] 已写入: %s' % args.json_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())