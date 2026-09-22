"""summary.md 生成:程序统计 + 裁判 LLM 结论。

所有统计均按数据集分别计算,不做跨数据集合并。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .config import AppConfig
from .runner import sanitize_name

DIFFICULTY_ORDER = ["难", "中", "简单"]

DIMENSIONS = (
    ("difficulty", "难度", lambda it: it.get("difficulty"),
     DIFFICULTY_ORDER),
    ("scope", "范围", lambda it: (it.get("category") or {}).get("scope"),
     ["网络", "设备", "其他"]),
    ("protocol_layer", "协议层",
     lambda it: (it.get("category") or {}).get("protocol_layer"),
     ["传输层", "IP层", "链路层", "物理层", "其他"]),
    ("lifecycle", "生命周期",
     lambda it: (it.get("category") or {}).get("lifecycle"),
     ["规划", "建设", "维护", "优化", "其他"]),
    ("scenario", "场景", lambda it: it.get("scenario"),
     ["园区", "宽带城域", "数据中心", "Internet", "通用"]),
    ("device_type", "设备类型", lambda it: it.get("device_type"),
     ["交换机", "路由器", "防火墙", "WLAN", "不限定"]),
)

RFC_YEAR_ORDER = ["2021", "2022", "2023", "2024", "2025"]

HW_FAMILY_ORDER = ["CE交换机", "S交换机", "路由器", "AR路由", "防火墙", "WLAN"]
HW_QTYPE_ORDER = ["特性", "场景", "配置方案", "命令行", "告警处理", "日志"]
_HW_MODEL_PREFIXES = [("NetEngine", "路由器"), ("AirEngine", "WLAN"),
                      ("USG", "防火墙"), ("AR", "AR路由"),
                      ("CE", "CE交换机"), ("S", "S交换机")]


def _rfc_year(it: dict) -> str | None:
    for t in it.get("tags") or []:
        if t.startswith("RFC-") and t[4:].isdigit():
            return t[4:]
    return None


def _hw_family(it: dict) -> str | None:
    tags = it.get("tags") or []
    model = tags[0] if tags and isinstance(tags[0], str) else ""
    for prefix, fam in _HW_MODEL_PREFIXES:
        if re.match(rf"^{re.escape(prefix)}\d", model):
            return fam
    return None


def _dim_stats(groups: dict, order: list) -> dict:
    # 按预定义顺序输出;顺序表外的取值排在末尾
    keys = ([k for k in order if k in groups]
            + sorted(k for k in groups if k not in order))
    return {
        k: {"count": len(groups[k]),
            "dist": {n: sum(1 for s in groups[k] if s == n) for n in range(0, 6)},
            "avg": round(sum(groups[k]) / len(groups[k]), 2)}
        for k in keys
    }


def _valid_scores(items):
    for it in items:
        ev = it.get("evaluation") or {}
        mr = it.get("model_response") or {}
        if mr.get("status") == "ok" and isinstance(ev.get("score"), int):
            yield it, ev


def compute_stats(files: list[Path]) -> dict:
    items: list[dict] = []
    for p in files:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            items.extend(it for it in data if isinstance(it, dict))

    answered = list(_valid_scores(items))
    scores = [ev["score"] for _, ev in answered]
    distribution = {n: 0 for n in range(0, 6)}
    for s in scores:
        distribution[s] += 1

    dims = {}
    if items and all(_rfc_year(it) is not None for it in items):
        # RFC 专项数据集(全部条目带 RFC-YYYY 标签):
        # 维度得分分布按年份 + 难度(简单=basic,中=detail)统计
        groups = defaultdict(list)
        for it, ev in answered:
            y = _rfc_year(it)
            if y:
                groups[y].append(ev["score"])
        dims["year"] = _dim_stats(groups, RFC_YEAR_ORDER)
        groups = defaultdict(list)
        for it, ev in answered:
            if it.get("difficulty"):
                groups[it["difficulty"]].append(ev["score"])
        dims["difficulty"] = _dim_stats(groups, DIFFICULTY_ORDER)
    elif items and all(_hw_family(it) is not None for it in items):
        # 华为设备数据集(全部条目 tags[0] 为可识别的华为设备型号):
        # 维度得分分布按设备类别 + 问题类型统计
        groups = defaultdict(list)
        for it, ev in answered:
            fam = _hw_family(it)
            if fam:
                groups[fam].append(ev["score"])
        dims["hw_family"] = _dim_stats(groups, HW_FAMILY_ORDER)
        groups = defaultdict(list)
        for it, ev in answered:
            tags = it.get("tags") or []
            if len(tags) > 2:
                groups[tags[2]].append(ev["score"])
        dims["hw_qtype"] = _dim_stats(groups, HW_QTYPE_ORDER)
    else:
        for dim_key, _dim_name, getter, order in DIMENSIONS:
            groups = defaultdict(list)
            for it, ev in answered:
                key = getter(it)
                if key:
                    groups[key].append(ev["score"])
            dims[dim_key] = _dim_stats(groups, order)

    hit = defaultdict(lambda: [0, 0])  # point -> [hits, total]
    point_ids = defaultdict(list)
    for it, ev in answered:
        for pr in ev.get("point_results") or []:
            point = pr.get("point")
            if not point:
                continue
            hit[point][1] += 1
            if pr.get("hit"):
                hit[point][0] += 1
            else:
                point_ids[point].append({
                    "id": it.get("id"),
                    "difficulty": it.get("difficulty"),
                    "protocol_layer": (it.get("category") or {}).get("protocol_layer"),
                })
    point_rates = {p: (h, t, round(h / t, 4)) for p, (h, t) in hit.items()
                   if t > 0}
    gaps = sorted(
        ([(p, h, t, point_ids[p]) for p, (h, t, r) in point_rates.items()
          if r < 0.5]),
        key=lambda g: g[2] / max(g[1], 1))

    failed_cases = sorted(
        ({
            "id": it.get("id"),
            "question": it.get("question") or "",
            "score": ev["score"],
            "difficulty": it.get("difficulty"),
            "protocol_layer": (it.get("category") or {}).get("protocol_layer"),
            "missed": [{"point": pr.get("point"), "comment": pr.get("comment") or ""}
                       for pr in ev.get("point_results") or []
                       if not pr.get("hit")],
        } for it, ev in answered if ev["score"] != 5),
        key=lambda c: (c["score"], c["id"]))

    return {
        "total": len(items),
        "answered": len(answered),
        "answered_errors": sum(1 for it in items
                               if (it.get("model_response") or {}).get("status") == "error"),
        "parse_errors": sum(1 for it in items
                            if (it.get("model_response") or {}).get("status") == "ok"
                            and (it.get("evaluation") or {}).get("score") is None),
        "passed": distribution[5],
        "failed_count": sum(distribution[n] for n in range(0, 5)),
        "avg": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "distribution": distribution,
        "dims": dims,
        "gaps": gaps,
        "failed_cases": failed_cases,
    }


DIM_LABELS = {k: n for k, n, *_ in DIMENSIONS}
DIM_LABELS["year"] = "年份"
DIM_LABELS["hw_family"] = "设备类别"
DIM_LABELS["hw_qtype"] = "问题类型"


def _overview_block(per_stem: dict[str, dict]) -> list[str]:
    lines = ["## 总体评价", ""]
    for stem, s in per_stem.items():
        lines.append(f"- {stem}:总数 {s['total']},完全通过(5分) {s['passed']},"
                     f"不通过(≠5分) {s['failed_count']},综合评分 {s['avg']:.2f}")
    lines.append("")
    return lines


def _dataset_section(stem: str, s: dict) -> list[str]:
    lines = [f"## {stem}", "",
             "### 统计", "",
             f"- 总数:{s['total']},有效评分:{s['answered']},"
             f"完全通过(5分):{s['passed']},不通过(≠5分):{s['failed_count']}",
             f"- 综合评分(平均分):**{s['avg']:.2f}** / 5",
             f"- 作答失败:{s['answered_errors']},评分失败:{s['parse_errors']}",
             "", "### 维度得分分布", "",
             "| 维度 | 总数 | 5分 | 4分 | 3分 | 2分 | 1分 | 0分 | 评分 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for dim_key, groups in s["dims"].items():
        if not groups:
            continue
        dim_name = DIM_LABELS.get(dim_key, dim_key)
        for value, v in groups.items():
            dist = v["dist"]
            dist_cells = " | ".join(str(dist[n]) for n in range(5, -1, -1))
            lines.append(f"| {dim_name}-{value} | {v['count']} | {dist_cells} "
                         f"| {v['avg']:.2f} |")
    lines += ["", "### 不通过详情(按得分升序)", ""]
    if s["failed_cases"]:
        for c in s["failed_cases"]:
            lines.append(f"#### id={c['id']} 得分 {c['score']}"
                         f"({c['difficulty']}/{c['protocol_layer']})")
            lines.append(f"**问题**:{c['question']}")
            lines.append("**不通过项**:")
            for m in c["missed"]:
                comment = f" — {m['comment']}" if m["comment"] else ""
                lines.append(f"- {m['point']}{comment}")
            lines.append("")
    else:
        lines += ["全部测试例完全通过(5分)。", ""]
    return lines


def render_summary_md(meta: dict, per_stem: dict[str, dict],
                      conclusion: str) -> str:
    out = [f"# LLM 网络知识掌握度评估总结",
           "",
           f"- 被评测模型:{meta['model']}(思考模式:{meta['thinking']})",
           f"- 裁判模型:{meta['judge_model']}",
           f"- 数据集:{', '.join(per_stem.keys())}",
           ""]
    out += _overview_block(per_stem)
    out += ["## 分析结论", "", conclusion, ""]
    for stem, s in per_stem.items():
        out += _dataset_section(stem, s)
    return "\n".join(out)


def _build_conclusion_prompt(per_stem: dict[str, dict]) -> str:
    stat_lines = []
    for stem, s in per_stem.items():
        stat_lines.append(
            f"[{stem}] 总数 {s['total']},完全通过 {s['passed']},"
            f"不通过 {s['failed_count']},综合评分 {s['avg']:.2f}")
        if s["gaps"]:
            stat_lines.append(f"[{stem}] 知识缺口:" + ";".join(
                f"{p}({h}/{t})" for p, h, t, _ in s["gaps"]))
    stems = "、".join(per_stem.keys())
    return ("以下是一次 LLM 网络知识评测各数据集(未合并)的统计数据。请写一段分析"
            f"结论,分别针对 {stems} 各数据集涵盖:优势维度、薄弱维度、知识缺口归因、"
            "改进建议。直接输出结论正文,500 字以内,不要标题。\n\n"
            + "\n".join(stat_lines))


def run_summaries(cfg: AppConfig, client,
                  produced: list[tuple[str, Path]]) -> None:
    if not produced:
        print("没有生成任何 EVALUATION,跳过 summary")
        return
    judge_model = cfg.judge_llm.model
    eval_model = cfg.evaluatee_llm.model

    by_thinking: dict[str, list[Path]] = defaultdict(list)
    for thinking, path in produced:
        by_thinking[thinking].append(path)

    out_dir = Path(cfg.report_dir) / sanitize_name(eval_model)
    for thinking, files in sorted(by_thinking.items()):
        per_stem = {}
        for f in files:
            stem = f.stem.replace(
                f"EVALUATION_{sanitize_name(judge_model)}_"
                f"{sanitize_name(eval_model)}_{thinking}_", "")
            per_stem[stem] = compute_stats([f])
        meta = {"model": eval_model, "judge_model": judge_model,
                "thinking": thinking}

        conclusion = ""
        try:
            result = client.chat(
                [{"role": "user",
                  "content": _build_conclusion_prompt(per_stem)}],
                temperature=0.0)
            if getattr(result, "success", False):
                conclusion = (result.content or "").strip()
        except Exception:
            conclusion = ""
        if not conclusion:
            conclusion = "(结论生成失败:裁判 LLM 调用未成功,统计部分仍完整)"

        md = render_summary_md(meta, per_stem, conclusion)
        out = out_dir / (
            f"EVALUATION_{sanitize_name(judge_model)}_"
            f"{sanitize_name(eval_model)}_{thinking}_summary.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8", newline="\n")
        print(f"[summary] {out}")
