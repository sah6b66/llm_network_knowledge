"""summary.md 生成:程序统计 + 裁判 LLM 结论。"""
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
    distribution = {n: 0 for n in range(1, 6)}
    for s in scores:
        distribution[s] += 1

    dims = {}
    for dim_key, dim_name, getter in DIMENSIONS:
        groups = defaultdict(list)
        for it, ev in answered:
            key = getter(it)
            if key:
                groups[key].append(ev["score"])
        dims[dim_key] = {k: {"count": len(v),
                              "avg": round(sum(v) / len(v), 2)}
                          for k, v in sorted(groups.items())}

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
                # 附题目 id 与维度(难度/协议层),供缺口清单展示
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

    low_scores = [
        {"id": it.get("id"), "difficulty": it.get("difficulty"),
         "protocol_layer": (it.get("category") or {}).get("protocol_layer"),
         "scenario": it.get("scenario"),
         "comment": (ev.get("comment") or "")[:80]}
        for it, ev in answered if ev["score"] <= 2]

    return {
        "total": len(items),
        "answered": len(answered),
        "answered_errors": sum(1 for it in items
                               if (it.get("model_response") or {}).get("status") == "error"),
        "parse_errors": sum(1 for it in items
                            if (it.get("model_response") or {}).get("status") == "ok"
                            and (it.get("evaluation") or {}).get("score") is None),
        "avg": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "distribution": distribution,
        "dims": dims,
        "point_rates": point_rates,
        "gaps": gaps,
        "low_scores": low_scores,
    }


DIM_LABELS = {k: n for k, n, _ in DIMENSIONS}


def _fmt_dist(dist: dict) -> str:
    return " ".join(f"{n}分×{dist.get(n, 0)}" for n in range(5, 0, -1))


def _stats_block(title: str, s: dict) -> str:
    lines = [f"### {title}", "",
             f"- 题数:{s['total']},有效评分:{s['answered']}",
             f"- 平均分:**{s['avg']:.2f}** / 5",
             f"- 分布:{_fmt_dist(s['distribution'])}",
             f"- 作答失败:{s['answered_errors']},评分失败:{s['parse_errors']}",
             ""]
    for dim_name, groups in s["dims"].items():
        if not groups:
            continue
        cells = " ".join(f"{k}({v['count']}题) {v['avg']:.2f}"
                         for k, v in groups.items())
        lines.append(f"- {DIM_LABELS.get(dim_name, dim_name)}:{cells}")
    lines.append("")
    return "\n".join(lines)


def render_summary_md(meta: dict, per_stem: dict[str, dict],
                      overall: dict, conclusion: str) -> str:
    out = [f"# LLM 网络知识掌握度评估总结",
           "",
           f"- 被评测模型:{meta['model']}(思考模式:{meta['thinking']})",
           f"- 裁判模型:{meta['judge_model']}",
           f"- 数据集:{', '.join(per_stem.keys())}",
           "", "## 总览", ""]
    out.append(_stats_block("全部数据集合并", overall))
    for stem, s in per_stem.items():
        out.append(_stats_block(stem, s))

    out.append("## 六维(全部数据集合并)")
    out.append("")
    for dim_key, groups in overall["dims"].items():
        if not groups:
            continue
        cells = " ".join(f"{k}({v['count']}题) {v['avg']:.2f}"
                         for k, v in groups.items())
        out.append(f"- {DIM_LABELS.get(dim_key, dim_key)}:{cells}")
    out.append("")

    out.append("## 评分点命中率(降序)")
    out.append("")
    ranked = sorted(overall["point_rates"].items(),
                    key=lambda kv: (-kv[1][2], kv[0]))
    for point, (h, t, r) in ranked:
        out.append(f"- {r * 100:.0f}%({h}/{t}) {point}")
    out.append("")

    out.append("## 知识缺口清单(命中率 < 50%)")
    out.append("")
    if overall["gaps"]:
        for point, h, t, ids in overall["gaps"]:
            id_str = ",".join(
                f"{d['id']}[{d['difficulty']}/{d['protocol_layer']}]"
                for d in ids)
            out.append(f"- {point}(命中 {h}/{t},涉及题 id:{id_str})")
    else:
        out.append("- 无")
    out.append("")

    out.append("## 低分题清单(总分 ≤ 2)")
    out.append("")
    if overall["low_scores"]:
        for l in overall["low_scores"]:
            out.append(f"- id={l['id']} [{l['difficulty']}/{l['protocol_layer']}/"
                       f"{l['scenario']}] {l['comment']}")
    else:
        out.append("- 无")
    out.append("")

    out.append("## 分析结论")
    out.append("")
    out.append(conclusion)
    out.append("")
    return "\n".join(out)


def _build_conclusion_prompt(meta: dict, overall: dict) -> str:
    stat_lines = [_stats_block("统计", overall)]
    if overall["gaps"]:
        stat_lines.append("知识缺口:" + ";".join(
            f"{p}({h}/{t})" for p, h, t, _ in overall["gaps"]))
    if overall["low_scores"]:
        stat_lines.append("低分题 id:" + ",".join(
            str(l["id"]) for l in overall["low_scores"]))
    return ("以下是一次 LLM 网络知识评测的统计数据。请写一段分析结论,涵盖:"
            "优势维度、薄弱维度、知识缺口归因、改进建议。直接输出结论正文,"
            "500 字以内,不要标题。\n\n" + "\n".join(stat_lines))


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
        overall = compute_stats(files)
        meta = {"model": eval_model, "judge_model": judge_model,
                "thinking": thinking}

        conclusion = ""
        try:
            result = client.chat(
                [{"role": "user",
                  "content": _build_conclusion_prompt(meta, overall)}],
                temperature=0.0)
            if getattr(result, "success", False):
                conclusion = (result.content or "").strip()
        except Exception:
            conclusion = ""
        if not conclusion:
            conclusion = "(结论生成失败:裁判 LLM 调用未成功,统计部分仍完整)"

        md = render_summary_md(meta, per_stem, overall, conclusion)
        out = out_dir / (
            f"EVALUATION_{sanitize_name(judge_model)}_"
            f"{sanitize_name(eval_model)}_{thinking}_summary.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8", newline="\n")
        print(f"[summary] {out}")
