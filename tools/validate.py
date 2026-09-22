#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 requirements.md 校验测试集。

用法:
  python tools/validate.py <file.json> --mode topics   # 题目清单: 结构+topic+配额+交叉
  python tools/validate.py <file.json> --mode cases    # 批次用例: 结构+内容+id唯一
  python tools/validate.py <file.json> --mode full     # 完整数据集: 全部检查
"""
import argparse
import json
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
    ids = [c.get("id") for c in cases
           if isinstance(c, dict) and isinstance(c.get("id"), int)]
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--mode", required=True, choices=["topics", "cases", "full"])
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
    need_content = args.mode in ("cases", "full")
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
