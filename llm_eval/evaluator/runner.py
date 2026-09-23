"""执行模式:逐题调用被评测 LLM,生成 RECORD 文件(并发+断点续跑)。"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .benchmark import load_benchmark
from .config import AppConfig
from .fileio import atomic_write_json

SYSTEM_PROMPT_EXECUTE = ("你是一位资深网络技术专家。请准确回答网络技术问题:"
                         "直接针对问题分条作答,覆盖关键要点,"
                         "不要展开与问题无关的背景知识,回答控制在 500 字以内。")

_ILLEGAL = '\\/:*?"<>|'


def sanitize_name(s: str) -> str:
    # 模型名常带路径形式前缀(如 deepseek-ai/DeepSeek-V4-Flash),只取最后一段作文件名
    s = s.split("/")[-1]
    for ch in _ILLEGAL:
        s = s.replace(ch, "-")
    return s.strip()


def record_path(report_dir: Path, model: str, thinking_mode: str,
                dataset_stem: str) -> Path:
    name = f"RECORD_{sanitize_name(model)}_{thinking_mode}_{dataset_stem}.json"
    return Path(report_dir) / sanitize_name(model) / name


def _load_existing(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []


def _is_done(item, case) -> bool:
    mr = item.get("model_response") if isinstance(item, dict) else None
    return (isinstance(mr, dict) and mr.get("status") == "ok"
            and item.get("question") == case.get("question"))


def _answer_one(client, case: dict, cfg: AppConfig, model: str,
                thinking_mode: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_EXECUTE},
        {"role": "user", "content": case["question"]},
    ]
    t0 = time.monotonic()
    try:
        result = client.chat(messages, temperature=cfg.temperature)
    except Exception as e:  # client 协议异常也不中断
        result = ChatResultShim(str(e))
    latency_ms = int((time.monotonic() - t0) * 1000)
    if getattr(result, "success", False):
        resp = {"answer": result.content, "status": "ok", "error": None,
                "latency_ms": latency_ms,
                "usage": dict(getattr(result, "usage", {}) or {}),
                "model": model, "thinking_mode": thinking_mode}
    else:
        resp = {"answer": "", "status": "error",
                "error": str(getattr(result, "error", "unknown")),
                "latency_ms": latency_ms, "usage": {},
                "model": model, "thinking_mode": thinking_mode}
    return resp


class ChatResultShim:
    def __init__(self, error: str):
        self.success = False
        self.error = error
        self.content = ""
        self.usage = {}


def run_execute(cfg: AppConfig, client) -> None:
    datasets = load_benchmark(cfg.benchmark_dir)
    model = cfg.evaluatee_llm.model
    thinking_mode = cfg.evaluatee_llm.thinking_mode

    for path, cases in datasets:
        out = record_path(cfg.report_dir, model, thinking_mode, path.stem)
        existing = _load_existing(out)
        done_by_id = {it.get("id"): it for it in existing
                      if isinstance(it, dict) and isinstance(it.get("id"), int)}

        items: list = []
        todo: list[dict] = []
        for case in cases:
            prior = done_by_id.get(case["id"])
            if prior is not None and _is_done(prior, case):
                items.append(prior)
            else:
                items.append(None)
                todo.append(case)
        index_by_id = {c["id"]: i for i, c in enumerate(cases)}
        skipped = len(cases) - len(todo)

        print(f"[{path.name}] 共 {len(cases)} 题,续跑跳过 {skipped},新作答 {len(todo)}")

        if todo:
            with ThreadPoolExecutor(max_workers=cfg.concurrency) as ex:
                futures = {
                    ex.submit(_answer_one, client, case, cfg, model, thinking_mode): case
                    for case in todo}
                for fut in as_completed(futures):
                    case = futures[fut]
                    resp = fut.result()
                    items[index_by_id[case["id"]]] = {**case, "model_response": resp}
                    atomic_write_json(out, items)

        final = json.loads(out.read_text(encoding="utf-8")) if out.exists() else items
        errors = sum(1 for it in final
                     if it.get("model_response", {}).get("status") == "error")
        print(f"[{path.name}] 完成:成功 {len(final) - errors},失败 {errors},"
              f"输出 {out}")
