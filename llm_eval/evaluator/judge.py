"""评估模式:裁判 LLM 逐评分点判定 + 总分,生成 EVALUATION 文件。"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import AppConfig
from .fileio import atomic_write_json
from .runner import sanitize_name
from .thinking_handler import strip_free_form_thinking

RECORD_NAME_RE = re.compile(r"^RECORD_(.+)_(enabled|disabled)_(dataset.*)\.json$")
EVALUATION_NAME_TMPL = "EVALUATION_{judge}_{model}_{thinking}_{stem}.json"

JUDGE_SYSTEM_PROMPT = (
    "你是网络技术领域的资深评审专家。你需要根据题目、参考答案与评分要点,"
    "评判被评测模型回答的质量。判定只看要点是否被正确覆盖:"
    "回答简洁或详细本身不影响评分,与参考答案措辞不同但含义正确不算错误。"
    "严格按照指定的 JSON 格式输出评分结果,不要输出 JSON 以外的任何内容。")


def parse_record_filename(name: str) -> tuple[str, str, str] | None:
    m = RECORD_NAME_RE.match(name)
    return (m.group(1), m.group(2), m.group(3)) if m else None


def build_judge_prompt(case: dict) -> str:
    points = "\n".join(f"{i}. {p}" for i, p in enumerate(case["scoring_points"], 1))
    model_answer = case.get("model_response", {}).get("answer", "")
    return f"""## 题目
{case['question']}

## 参考答案
{case['answer']}

## 评分要点
{points}

## 被评测模型的回答
{model_answer}

## 评分要求
1. 逐条判断「评分要点」在回答中是否命中:回答实质正确地覆盖该要点记 hit=true,仅提及关键词但表述错误或含糊其辞记 hit=false;comment 用一句话给出判定依据
2. 综合给出 1-5 的整数总分,总分应与要点命中情况一致:5=全部命中且无错误,4=大部分命中,3=约半数命中,2=掌握较差,1=基本未掌握;回答含严重概念错误时下调一档
3. 只输出 JSON,不要输出任何其他内容,格式如下:
{{"point_results": [{{"point": "要点原文", "hit": true, "comment": "判定依据"}}], "score": 4, "comment": "总体评价"}}"""


def _balanced_brace_extract(text: str, start: int) -> str | None:
    depth, in_string, escape = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_judge_json(text: str) -> dict | None:
    cleaned = strip_free_form_thinking(text)
    candidates: list[str] = []
    try:
        candidates.append(cleaned.strip())
    except Exception:
        pass
    candidates.extend(re.findall(r"```(?:json)?\s*\n(.*?)\n```", cleaned, re.DOTALL)[::-1])
    for i in range(len(cleaned) - 1, -1, -1):
        if cleaned[i] == "{":
            frag = _balanced_brace_extract(cleaned, i)
            if frag:
                candidates.append(frag)
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        score = obj.get("score")
        if not (isinstance(score, int) and not isinstance(score, bool)
                and 1 <= score <= 5):
            continue
        pr = obj.get("point_results")
        if not (isinstance(pr, list) and all(
                isinstance(x, dict) and isinstance(x.get("point"), str)
                and isinstance(x.get("hit"), bool) for x in pr)):
            continue
        if not isinstance(obj.get("comment"), str):
            obj["comment"] = ""
        return obj
    return None


def _judge_one(client, item: dict, judge_model: str) -> dict:
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": build_judge_prompt(item)},
    ]
    last_text = ""
    for _ in range(2):  # 首评 + 解析失败重试一次
        result = client.chat(messages, temperature=0.0)
        if not getattr(result, "success", False):
            return {"judge_model": judge_model, "point_results": [],
                    "score": None,
                    "comment": f"裁判调用失败:{getattr(result, 'error', '')}"}
        last_text = result.content or ""
        parsed = parse_judge_json(last_text)
        if parsed is not None:
            return {"judge_model": judge_model,
                    "point_results": parsed["point_results"],
                    "score": parsed["score"], "comment": parsed["comment"]}
    return {"judge_model": judge_model, "point_results": [], "score": None,
            "comment": "", "parse_error": last_text[:500]}


def _is_scored(item) -> bool:
    ev = item.get("evaluation") if isinstance(item, dict) else None
    return isinstance(ev, dict) and ev.get("score") is not None


def evaluation_path(report_dir: Path, judge: str, model: str,
                    thinking: str, stem: str) -> Path:
    name = EVALUATION_NAME_TMPL.format(judge=sanitize_name(judge),
                                       model=sanitize_name(model),
                                       thinking=thinking, stem=stem)
    return Path(report_dir) / sanitize_name(model) / name


def run_evaluate(cfg: AppConfig, client) -> None:
    judge_model = cfg.judge_llm.model
    eval_model = cfg.evaluatee_llm.model
    record_dir = Path(cfg.report_dir) / sanitize_name(eval_model)
    if not record_dir.is_dir():
        raise FileNotFoundError(f"被评测模型报告目录不存在:{record_dir}")

    records = sorted(p for p in record_dir.glob("RECORD_*.json")
                     if parse_record_filename(p.name))
    if not records:
        raise RuntimeError(f"{record_dir} 下没有文件名合法的 RECORD 文件")

    produced: list[tuple[str, Path]] = []  # (thinking, eval_path) 供 summary 使用
    for rec_path in records:
        _, thinking, stem = parse_record_filename(rec_path.name)
        try:
            items = json.loads(rec_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"[跳过] {rec_path.name} RECORD 解析失败:{e}")
            continue
        if not isinstance(items, list):
            print(f"[跳过] {rec_path.name} RECORD 顶层不是数组")
            continue
        null_count = sum(1 for it in items if not isinstance(it, dict))
        if null_count:
            print(f"[警告] {rec_path.name} 有 {null_count} 条空占位(执行模式未完成),"
                  f"本次不评估;完成 execute 后重跑 evaluate 会自动补上")
            items = [it for it in items if isinstance(it, dict)]

        out = evaluation_path(cfg.report_dir, judge_model, eval_model,
                              thinking, stem)
        existing = []
        if out.exists():
            try:
                loaded = json.loads(out.read_text(encoding="utf-8"))
                existing = loaded if isinstance(loaded, list) else []
            except (json.JSONDecodeError, UnicodeDecodeError):
                existing = []
        scored_by_id = {it.get("id"): it for it in existing
                        if isinstance(it, dict) and _is_scored(it)
                        and it.get("question") is not None}

        work: list = []
        todo: list[dict] = []
        for item in items:
            prior = scored_by_id.get(item.get("id"))
            if prior is not None and prior.get("question") == item.get("question"):
                work.append(prior)
            elif (item.get("model_response") or {}).get("status") != "ok":
                # 作答失败:不调用裁判,直接记 score:null
                work.append(dict(item, evaluation={
                    "judge_model": judge_model, "point_results": [],
                    "score": None, "comment": "作答失败,未评分"}))
            else:
                work.append(None)
                todo.append(item)
        index_by_id = {it["id"]: i for i, it in enumerate(items) if "id" in it}
        print(f"[{rec_path.name}] 共 {len(items)} 题,续跑跳过 "
              f"{len(items) - len(todo)},新评估 {len(todo)}")

        # items 为基底;work 位置对应 items
        if todo:
            with ThreadPoolExecutor(max_workers=cfg.concurrency) as ex:
                futures = {ex.submit(_judge_one, client, it, judge_model): it
                           for it in todo}
                for fut in as_completed(futures):
                    item = futures[fut]
                    ev = fut.result()
                    merged = dict(item)
                    merged["evaluation"] = ev
                    work[index_by_id[item["id"]]] = merged
                    snapshot = [w if w is not None else items[j]
                                for j, w in enumerate(work)]
                    atomic_write_json(out, snapshot)
        else:
            # 全部已评分:写回先前的评分结果,避免用原始 RECORD 覆盖 EVALUATION
            atomic_write_json(out, [w for w in work if w is not None])
        produced.append((thinking, out))

    from .report import run_summaries
    run_summaries(cfg, client, produced)
