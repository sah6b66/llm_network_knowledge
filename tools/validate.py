#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 requirements.md 校验测试集。

用法:
  python tools/validate.py <file.json> --mode topics   # 题目清单: 结构+topic+配额+交叉
  python tools/validate.py <file.json> --mode cases    # 批次用例: 结构+内容+id唯一
  python tools/validate.py <file.json> --mode full     # 完整数据集: 全部检查
  python tools/validate.py <file.json> --mode rfc_topics  # RFC 题目清单 topics_rfc.json
  python tools/validate.py <file.json> --mode rfc_cases   # RFC 年度批次用例
  python tools/validate.py <file.json> --mode rfc_full    # RFC 合并数据集(100 例)
  python tools/validate.py <file.json> --mode hw_topics   # 华为设备题目清单 topics_hw.json
  python tools/validate.py <file.json> --mode hw_cases    # 华为设备单产品批次用例
  python tools/validate.py <file.json> --mode hw_full     # 华为设备合并数据集(100 例)
"""
import argparse
import json
import re
import sys

ENUMS = {
    "difficulty": ["简单", "中", "难"],
    "scope": ["网络", "设备", "其他"],
    "protocol_layer": ["物理层", "链路层", "IP层", "传输层", "其他"],
    "lifecycle": ["规划", "建设", "维护", "优化", "其他"],
    "scenario": ["数据中心", "园区", "宽带城域", "Internet", "通用"],
    "device_type": ["交换机", "路由器", "防火墙", "WLAN", "不限定"],
}

QUOTAS = {
    "difficulty": {"简单": 20, "中": 50, "难": 30},
    "protocol_layer": {"物理层": 10, "链路层": 20, "IP层": 30, "传输层": 15, "其他": 25},
    "lifecycle": {"规划": 20, "建设": 20, "维护": 35, "优化": 15, "其他": 10},
    "scope": {"网络": 50, "设备": 45, "其他": 5},
    "scenario": {"数据中心": 25, "园区": 25, "宽带城域": 15, "Internet": 10, "通用": 25},
    "device_type": {"交换机": 20, "路由器": 20, "防火墙": 10, "WLAN": 10, "不限定": 40},
}

CISCO_PLATFORMS = ["IOS", "IOS-XE", "IOS-XR", "NX-OS"]
RECENT_YEARS = ["2022", "2023", "2024", "2025", "2026"]

RFC_YEARS = ["2021", "2022", "2023", "2024", "2025"]

HW_CATEGORIES = ["特性", "场景", "配置方案", "命令行", "告警处理", "日志"]
HW_PRODUCTS = {  # 产品族 -> (device_type, scenario)
    "CE交换机": ("交换机", "数据中心"),
    "S交换机": ("交换机", "园区"),
    "路由器NE": ("路由器", "通用"),
    "AR路由": ("路由器", "通用"),
    "防火墙": ("防火墙", "通用"),
    "WLAN": ("WLAN", "园区"),
}
HW_ID_BLOCKS = [("CE交换机", 1, 25), ("S交换机", 26, 35), ("路由器NE", 36, 55),
                ("AR路由", 56, 70), ("防火墙", 71, 85), ("WLAN", 86, 100)]
HW_QUOTAS = {  # 产品族 -> {问题分类: 条数}
    "CE交换机": {"特性": 2, "场景": 1, "配置方案": 4, "命令行": 9, "告警处理": 4, "日志": 5},
    "S交换机": {"特性": 1, "场景": 0, "配置方案": 1, "命令行": 3, "告警处理": 3, "日志": 2},
    "路由器NE": {"特性": 2, "场景": 0, "配置方案": 3, "命令行": 7, "告警处理": 4, "日志": 4},
    "AR路由": {"特性": 1, "场景": 0, "配置方案": 3, "命令行": 5, "告警处理": 3, "日志": 3},
    "防火墙": {"特性": 2, "场景": 0, "配置方案": 2, "命令行": 5, "告警处理": 3, "日志": 3},
    "WLAN": {"特性": 1, "场景": 0, "配置方案": 2, "命令行": 6, "告警处理": 3, "日志": 3},
}
_HW_MODEL_PREFIXES = [("NetEngine", "路由器NE"), ("AirEngine", "WLAN"),
                      ("USG", "防火墙"), ("AR", "AR路由"),
                      ("CE", "CE交换机"), ("S", "S交换机")]
_HW_VERSION_RE = re.compile(r"^V\d+R\d{3}C\d{2}$")


def _hw_family(model):
    for prefix, fam in _HW_MODEL_PREFIXES:
        if re.match(rf"^{re.escape(prefix)}\d", model):
            return fam
    return None


def get_tags(c):
    t = c.get("tags")
    return t if isinstance(t, list) else []


def check_structure(cases, need_content, errors):
    for i, c in enumerate(cases):
        p = f"用例[{i}] id={c.get('id')}"
        if not isinstance(c, dict):
            errors.append(f"{p} 必须是对象")
            continue
        if not isinstance(c.get("id"), int):
            errors.append(f"{p} id 缺失或非整数")
        if c.get("difficulty") not in ENUMS["difficulty"]:
            errors.append(f"{p} difficulty 非法: {c.get('difficulty')}")
        cat = c.get("category")
        if not isinstance(cat, dict):
            errors.append(f"{p} 缺少 category")
        else:
            for k in ("scope", "protocol_layer", "lifecycle"):
                if cat.get(k) not in ENUMS[k]:
                    errors.append(f"{p} category.{k} 非法: {cat.get(k)}")
        for k in ("scenario", "device_type"):
            if c.get(k) not in ENUMS[k]:
                errors.append(f"{p} {k} 非法: {c.get(k)}")
        tags = c.get("tags")
        if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
            errors.append(f"{p} tags 必须为非空字符串数组")
        has_num = any(t.startswith("RFC") and t[3:].isdigit() for t in get_tags(c))
        has_year = any(t.startswith("RFC-") and t[4:] in RECENT_YEARS for t in get_tags(c))
        if has_year and not has_num:
            errors.append(f"{p} 含 RFC-年份 标签但缺少 RFC 编号标签")
        if need_content:
            for k in ("question", "answer"):
                v = c.get(k)
                if not isinstance(v, str) or not v.strip():
                    errors.append(f"{p} {k} 缺失或为空")
            sp = c.get("scoring_points")
            ok = isinstance(sp, list) and 3 <= len(sp) <= 8 and all(
                isinstance(s, str) and s.strip() for s in sp)
            if not ok:
                errors.append(f"{p} scoring_points 必须为 3-8 条非空字符串")
    ids = [cid for c in cases
           if isinstance(c, dict) and isinstance(cid := c.get("id"), int)]
    if len(ids) != len(set(ids)):
        errors.append("存在重复 id")
    return ids


def check_quotas(cases, errors):
    getters = {
        "difficulty": lambda c: c.get("difficulty"),
        "scope": lambda c: (c.get("category") or {}).get("scope"),
        "protocol_layer": lambda c: (c.get("category") or {}).get("protocol_layer"),
        "lifecycle": lambda c: (c.get("category") or {}).get("lifecycle"),
        "scenario": lambda c: c.get("scenario"),
        "device_type": lambda c: c.get("device_type"),
    }
    for dim, table in QUOTAS.items():
        actual = {}
        for c in cases:
            v = getters[dim](c)
            actual[v] = actual.get(v, 0) + 1
        for k, want in table.items():
            got = actual.get(k, 0)
            if got != want:
                errors.append(f"配额不符 [{dim}] {k}: 实际 {got}, 要求 {want}")


def check_cross(cases, errors):
    cli = [c for c in cases if "CLI" in get_tags(c)]
    if len(cli) < 20:
        errors.append(f"CLI 题不足: {len(cli)} < 20")
    hw = [c for c in cli if "华为" in get_tags(c)]
    if len(hw) < 10:
        errors.append(f"华为 CLI 题不足: {len(hw)} < 10")
    for plat, minimum in (("VRPv5", 3), ("VRPv8", 4)):
        n = sum(1 for c in hw if plat in get_tags(c))
        if n < minimum:
            errors.append(f"华为 {plat} 题不足: {n} < {minimum}")
    cs = [c for c in cli if "Cisco" in get_tags(c)]
    if len(cs) < 8:
        errors.append(f"Cisco CLI 题不足: {len(cs)} < 8")
    covered = [p for p in CISCO_PLATFORMS if any(p in get_tags(c) for c in cs)]
    if len(covered) < 2:
        errors.append(f"Cisco 平台覆盖不足 2 个: 当前 {covered}")
    diff = [c for c in cases if "版本差异" in get_tags(c)]
    if len(diff) < 5:
        errors.append(f"版本差异对比题不足: {len(diff)} < 5")
    recent = {}
    for c in cases:
        for t in get_tags(c):
            if t.startswith("RFC-") and t[4:] in RECENT_YEARS:
                recent[t[4:]] = recent.get(t[4:], 0) + 1
    total = sum(recent.values())
    if total < 15:
        errors.append(f"近4年 RFC 题不足: {total} < 15")
    for y in RECENT_YEARS:
        if recent.get(y, 0) < 2:
            errors.append(f"RFC-{y} 题不足: {recent.get(y, 0)} < 2")


def _rfc_tag_info(c, p, errors):
    years = [t[4:] for t in get_tags(c)
             if t.startswith("RFC-") and t[4:] in RFC_YEARS]
    numbers = [t[3:] for t in get_tags(c)
               if t.startswith("RFC") and t[3:].isdigit()]
    if len(years) != 1:
        errors.append(f"{p} RFC-年份标签必须恰有一个(2021-2025): {years}")
    if len(numbers) != 1:
        errors.append(f"{p} RFC 编号标签必须恰有一个(如 RFC8996): {numbers}")
    return (years[0] if len(years) == 1 else None,
            numbers[0] if len(numbers) == 1 else None)


def _check_rfc_item(c, i, need_content, errors):
    """校验单个 RFC 条目,返回 {id, year, number, rfc, difficulty}(无法解析的字段为 None)。"""
    if not isinstance(c, dict):
        errors.append(f"用例[{i}] 必须是对象")
        return None
    p = f"用例[{i}] id={c.get('id')}"
    cid = c.get("id")
    if not isinstance(cid, int):
        errors.append(f"{p} id 缺失或非整数")
        cid = None
    cat = c.get("category")
    if not isinstance(cat, dict):
        errors.append(f"{p} 缺少 category")
    else:
        if cat.get("scope") != "其他":
            errors.append(f"{p} category.scope 必须为 其他: {cat.get('scope')}")
        if cat.get("protocol_layer") not in ENUMS["protocol_layer"]:
            errors.append(f"{p} category.protocol_layer 非法: {cat.get('protocol_layer')}")
        if cat.get("lifecycle") != "其他":
            errors.append(f"{p} category.lifecycle 必须为 其他: {cat.get('lifecycle')}")
    for k in ("scenario", "device_type"):
        if c.get(k) != "其他":
            errors.append(f"{p} {k} 必须为 其他: {c.get(k)}")
    tags = c.get("tags")
    if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
        errors.append(f"{p} tags 必须为非空字符串数组")
    year, number = _rfc_tag_info(c, p, errors)
    rfc = c.get("rfc")
    if isinstance(rfc, int):
        if number and number != str(rfc):
            errors.append(f"{p} rfc 字段({rfc})与编号标签(RFC{number})不一致")
    elif "rfc" in c:
        errors.append(f"{p} rfc 字段必须为整数")
    if need_content:
        if c.get("difficulty") not in ("简单", "中"):
            errors.append(f"{p} 难度非法(difficulty 仅允许 简单/中): {c.get('difficulty')}")
        for k in ("question", "answer"):
            v = c.get(k)
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{p} {k} 缺失或为空")
        sp = c.get("scoring_points")
        ok = isinstance(sp, list) and 3 <= len(sp) <= 8 and all(
            isinstance(s, str) and s.strip() for s in sp)
        if not ok:
            errors.append(f"{p} scoring_points 必须为 3-8 条非空字符串")
    return {"id": cid, "year": year, "number": number,
            "rfc": rfc if isinstance(rfc, int) else None,
            "difficulty": c.get("difficulty")}


def _rfc_year_errors(infos, errors):
    for y in RFC_YEARS:
        n = sum(1 for x in infos if x["year"] == y)
        if n != 10:
            errors.append(f"RFC-{y} 题数 {n} != 10(每年 10 篇)")


def check_rfc_topics(items, errors):
    infos = []
    for i, c in enumerate(items):
        info = _check_rfc_item(c, i, False, errors)
        if info:
            infos.append(info)
        if isinstance(c, dict):
            t = c.get("topic")
            if not isinstance(t, str) or not t.strip():
                errors.append(f"用例[{i}] id={c.get('id')} topic 缺失或为空")
            if "rfc" not in c:
                errors.append(f"用例[{i}] id={c.get('id')} 缺少 rfc 字段")
    if len(items) != 50:
        errors.append(f"题目数 {len(items)} != 50")
    ids = [x["id"] for x in infos if x["id"] is not None]
    if sorted(ids) != list(range(1, 51)):
        errors.append("id 必须为 1-50 连续唯一")
    _rfc_year_errors(infos, errors)
    nums = [x["rfc"] or x["number"] for x in infos]
    if len(nums) != len(set(nums)):
        errors.append("RFC 编号存在重复")


def _rfc_case_infos(items, errors):
    """单条校验,返回 infos。难度统一与 id 范围由调用方按模式检查。"""
    infos = [x for x in (_check_rfc_item(c, i, True, errors)
                         for i, c in enumerate(items)) if x]
    ids = [x["id"] for x in infos if x["id"] is not None]
    if len(ids) != len(set(ids)):
        errors.append("id 必须唯一")
    return infos


def check_rfc_cases(items, errors):
    infos = _rfc_case_infos(items, errors)
    diffs = {x["difficulty"] for x in infos}
    if len(diffs) > 1:
        errors.append(f"难度必须统一: {sorted(diffs)}")
    ids = [x["id"] for x in infos if x["id"] is not None]
    if any(not 1 <= i <= 50 for i in ids):
        errors.append("id 必须在 1-50 内且唯一")
    years = {x["year"] for x in infos}
    if len(years) > 1:
        errors.append(f"批次文件必须只含同一年份: {sorted(years)}")


def check_rfc_full(items, errors):
    infos = _rfc_case_infos(items, errors)
    if len(items) != 100:
        errors.append(f"用例数 {len(items)} != 100")
    ids = [x["id"] for x in infos if x["id"] is not None]
    if sorted(ids) != list(range(1, 101)):
        errors.append("id 必须为 1-100 连续唯一")
    for y in RFC_YEARS:
        n = sum(1 for x in infos if x["year"] == y)
        if n != 20:
            errors.append(f"RFC-{y} 题数 {n} != 20(每年 10 篇 × 简单/中)")
    pairs: dict[str, list] = {}
    for x in infos:
        if x["number"]:
            pairs.setdefault(x["number"], []).append(x["difficulty"])
    for num, diffs in pairs.items():
        if sorted(diffs) != ["中", "简单"]:
            errors.append(f"RFC{num} 编号应恰出现 2 次(简单+中): "
                          f"实际 {len(diffs)} 次 {sorted(diffs)}")


def _check_hw_item(c, i, need_content, errors):
    """校验单个华为设备条目,返回 {id, family, cat}(无法解析的字段为 None)。"""
    if not isinstance(c, dict):
        errors.append(f"用例[{i}] 必须是对象")
        return None
    p = f"用例[{i}] id={c.get('id')}"
    cid = c.get("id")
    if not isinstance(cid, int):
        errors.append(f"{p} id 缺失或非整数")
        cid = None
    cat = c.get("category")
    if not isinstance(cat, dict):
        errors.append(f"{p} 缺少 category")
    else:
        for k, want in (("scope", "设备"), ("protocol_layer", "其他"),
                        ("lifecycle", "其他")):
            if cat.get(k) != want:
                errors.append(f"{p} category.{k} 必须为 {want}: {cat.get(k)}")
    tags = c.get("tags")
    family = qcat = None
    model = version = None
    if not isinstance(tags, list) or not all(
            isinstance(t, str) and t.strip() for t in tags):
        errors.append(f"{p} tags 必须为非空字符串数组")
    else:
        model = tags[0]
        family = _hw_family(model)
        if family is None:
            errors.append(f"{p} tags[0] 无法识别产品族: {model}")
        version = tags[1] if len(tags) > 1 else ""
        if not _HW_VERSION_RE.match(version or ""):
            errors.append(f"{p} tags[1] 版本格式应为 VxxRxxxCxx: {version}")
        qcat = tags[2] if len(tags) > 2 else ""
        if qcat not in HW_CATEGORIES:
            errors.append(f"{p} tags[2] 问题分类非法: {qcat}")
    if family:
        dtype, scen = HW_PRODUCTS[family]
        if c.get("scenario") != scen:
            errors.append(f"{p} scenario 必须为 {scen}: {c.get('scenario')}")
        if c.get("device_type") != dtype:
            errors.append(f"{p} device_type 必须为 {dtype}: {c.get('device_type')}")
    if c.get("difficulty") not in ENUMS["difficulty"]:
        errors.append(f"{p} difficulty 非法: {c.get('difficulty')}")
    elif qcat in HW_CATEGORIES:
        want = "简单" if qcat in ("特性", "场景") else "中"
        if c.get("difficulty") != want:
            errors.append(f"{p} 难度不符: {qcat} 类应为 {want}")
    if need_content:
        for k in ("question", "answer"):
            v = c.get(k)
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{p} {k} 缺失或为空")
        sp = c.get("scoring_points")
        ok = isinstance(sp, list) and 3 <= len(sp) <= 8 and all(
            isinstance(s, str) and s.strip() for s in sp)
        if not ok:
            errors.append(f"{p} scoring_points 必须为 3-8 条非空字符串")
        q = c.get("question")
        if isinstance(q, str) and model and model not in q:
            errors.append(f"{p} question 未点名设备型号: {model}")
        if isinstance(q, str) and version and _HW_VERSION_RE.match(version) \
                and version not in q:
            errors.append(f"{p} question 未点名设备版本: {version}")
    return {"id": cid, "family": family, "cat": qcat}


def _hw_block_errors(infos, errors):
    for x in infos:
        if x["id"] is None or x["family"] is None:
            continue
        expected = next((f for f, lo, hi in HW_ID_BLOCKS if lo <= x["id"] <= hi),
                        None)
        if expected is not None and x["family"] != expected:
            errors.append(f"id={x['id']} id 块不符: 应属 {expected}, "
                          f"实为 {x['family']}")


def _hw_quota_errors(infos, errors):
    for fam, table in HW_QUOTAS.items():
        for qcat, want in table.items():
            got = sum(1 for x in infos
                      if x["family"] == fam and x["cat"] == qcat)
            if got != want:
                errors.append(f"配额不符 [{fam}] {qcat}: 实际 {got}, 要求 {want}")


def check_hw_topics(items, errors):
    infos = []
    for i, c in enumerate(items):
        info = _check_hw_item(c, i, False, errors)
        if info:
            infos.append(info)
        if isinstance(c, dict):
            t = c.get("topic")
            if not isinstance(t, str) or not t.strip():
                errors.append(f"用例[{i}] id={c.get('id')} topic 缺失或为空")
    if len(items) != 100:
        errors.append(f"题目数 {len(items)} != 100")
    ids = [x["id"] for x in infos if x["id"] is not None]
    if sorted(ids) != list(range(1, 101)):
        errors.append("id 必须为 1-100 连续唯一")
    _hw_block_errors(infos, errors)
    _hw_quota_errors(infos, errors)


def check_hw_cases(items, errors):
    infos = [x for x in (_check_hw_item(c, i, True, errors)
                         for i, c in enumerate(items)) if x]
    fams = {x["family"] for x in infos if x["family"]}
    if len(fams) > 1:
        errors.append(f"批次必须为同一产品族: {sorted(fams)}")


def check_hw_full(items, errors):
    infos = [x for x in (_check_hw_item(c, i, True, errors)
                         for i, c in enumerate(items)) if x]
    if len(items) != 100:
        errors.append(f"用例数 {len(items)} != 100")
    ids = [x["id"] for x in infos if x["id"] is not None]
    if sorted(ids) != list(range(1, 101)):
        errors.append("id 必须为 1-100 连续唯一")
    _hw_block_errors(infos, errors)
    _hw_quota_errors(infos, errors)
    seen = {}
    for c in items:
        if not isinstance(c, dict) or not isinstance(c.get("question"), str):
            continue
        q = c["question"]
        if q in seen:
            errors.append(f"question 存在重复: id={seen[q]} 与 id={c.get('id')}")
        else:
            seen[q] = c.get("id")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--mode", required=True,
                    choices=["topics", "cases", "full",
                             "rfc_topics", "rfc_cases", "rfc_full",
                             "hw_topics", "hw_cases", "hw_full"])
    args = ap.parse_args()
    errors = []
    raw = open(args.file, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("文件含 BOM")
    try:
        cases = json.loads(raw.decode("utf-8-sig"))
    except Exception as e:
        print(f"FAIL: JSON 解析失败: {e}")
        sys.exit(1)
    if not isinstance(cases, list):
        print("FAIL: 顶层必须是数组")
        sys.exit(1)
    need_content = args.mode in ("cases", "full", "rfc_cases", "rfc_full",
                                 "hw_cases", "hw_full")
    if args.mode.startswith("rfc_"):
        if args.mode == "rfc_topics":
            check_rfc_topics(cases, errors)
        elif args.mode == "rfc_cases":
            check_rfc_cases(cases, errors)
        else:
            check_rfc_full(cases, errors)
    elif args.mode.startswith("hw_"):
        if args.mode == "hw_topics":
            check_hw_topics(cases, errors)
        elif args.mode == "hw_cases":
            check_hw_cases(cases, errors)
        else:
            check_hw_full(cases, errors)
    else:
        ids = check_structure(cases, need_content, errors)
        if args.mode == "topics":
            if len(cases) != 100:
                errors.append(f"题目数 {len(cases)} != 100")
            for i, c in enumerate(cases):
                t = c.get("topic")
                if not isinstance(t, str) or not t.strip():
                    errors.append(f"用例[{i}] id={c.get('id')} topic 缺失或为空")
            check_quotas(cases, errors)
            check_cross(cases, errors)
        elif args.mode == "full":
            if len(cases) != 100:
                errors.append(f"用例数 {len(cases)} != 100")
            if sorted(ids) != list(range(1, 101)):
                errors.append("id 必须为 1-100 连续唯一")
            check_quotas(cases, errors)
            check_cross(cases, errors)
    if errors:
        print(f"FAIL ({len(errors)} 项):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print(f"PASS: {len(cases)} 条, 模式 {args.mode}")


if __name__ == "__main__":
    main()
