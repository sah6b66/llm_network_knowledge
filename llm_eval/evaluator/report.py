"""summary.md 生成:程序统计 + 裁判 LLM 结论。

所有统计均按数据集分别计算,不做跨数据集合并。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .config import AppConfig
from .runner import sanitize_name

DIMENSIONS = (
    ("difficulty", "难度", lambda it: it.get("difficulty")),
    ("scope", "范围", lambda it: (it.get("category") or {}).get("scope")),
    ("protocol_layer", "协议层",
     lambda it: (it.get("category") or {}).get("protocol_layer")),
    ("lifecycle", "生命周期",
     lambda it: (it.get("category") or {}).get("lifecycle")),
    ("scenario", "场景", lambda it: it.get("scenario")),
    ("device_type", "设备类型", lambda it: it.get("device_type")),
)


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
    for dim_key, _dim_name, getter in DIMENSIONS:
        groups = defaultdict(list)
        for it, ev in answered:
            key = getter(it)
            if key:
                groups[key].append(ev["score"])
        dims[dim_key] = {
            k: {"count": len(v),
                "dist": {n: sum(1 for s in v if s == n) for n in range(0, 6)},
                "avg": round(sum(v) / len(v), 2)}
            for k, v in sorted(groups.items())
        }

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


DIM_LABELS = {k: n for k, n, _ in DIMENSIONS}


def _overview_block(per_stem: dict[str, dict]) -> list[str]:
    lines = ["## 总体评价", ""]
    for stem, s in per_stem.items():
        lines.append(f"- {stem}:总数 {s['total']},完全通过(5分) {s['passed']},"
                     f"不通过(≠5分) {s['failed_count']},综合评分 {s['avg']:.2f}")
    lines += ["", "### 不满足项总体说明", ""]
    for stem, s in per_stem.items():
        lines.append(f"- {stem}(命中率<50% 评分点 {len(s['gaps'])} 个):")
        if s["gaps"]:
            for point, h, t, ids in s["gaps"]:
                id_str = ",".join(
                    f"{d['id']}[{d['difficulty']}/{d['protocol_layer']}]"
                    for d in ids)
                lines.append(f"  - {point}(命中 {h}/{t},涉及题 id:{id_str})")
        else:
            lines.append("  - 无")
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
