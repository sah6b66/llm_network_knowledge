"""配置加载与校验。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    pass


@dataclass
class LLMNode:
    provider: str
    api_url: str
    api_key: str
    model: str
    timeout: int = 300
    max_tokens: int = 32768
    thinking_mode: str = "disabled"
    ssl_verify: bool = False


@dataclass
class AppConfig:
    mode: str
    benchmark_dir: Path
    report_dir: Path
    evaluatee_llm: LLMNode
    judge_llm: LLMNode
    concurrency: int = 4
    max_retries: int = 2
    temperature: float = 0.1


def _load_llm_node(name: str, raw: Any, need_conn: bool) -> LLMNode:
    if not isinstance(raw, dict):
        raise ConfigError(f"{name} 必须是对象")
    thinking = raw.get("thinking") or {}
    if not isinstance(thinking, dict):
        raise ConfigError(f"{name}.thinking 必须是对象")
    mode = thinking.get("mode", "disabled")
    if mode not in ("enabled", "disabled"):
        raise ConfigError(f"{name}.thinking.mode 仅支持 enabled/disabled,收到:{mode!r}")
    try:
        timeout = int(raw.get("timeout", 300))
        max_tokens = int(raw.get("max_tokens", 32768))
    except (ValueError, TypeError) as e:
        raise ConfigError(f"{name}.timeout/max_tokens 必须为数值: {e}") from e
    ssl_verify = raw.get("ssl_verify", False)
    if not isinstance(ssl_verify, bool):
        raise ConfigError(f"{name}.ssl_verify 必须为布尔值,收到:{ssl_verify!r}")
    node = LLMNode(
        provider=str(raw.get("provider", "glm")),
        api_url=str(raw.get("api_url", "")),
        api_key=str(raw.get("api_key", "")),
        model=str(raw.get("model", "")),
        timeout=timeout,
        max_tokens=max_tokens,
        thinking_mode=mode,
        ssl_verify=ssl_verify,
    )
    if need_conn:
        for field in ("api_url", "api_key", "model"):
            if not getattr(node, field):
                raise ConfigError(f"{name}.{field} 不能为空")
    return node


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"配置文件不存在:{path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ConfigError(f"配置文件不是合法 JSON:{e}") from e
    if not isinstance(raw, dict):
        raise ConfigError("配置顶层必须是对象")

    mode = raw.get("mode")
    if mode not in ("execute", "evaluate"):
        raise ConfigError(f"mode 必须为 execute 或 evaluate,收到:{mode!r}")

    base = path.resolve().parent
    for key in ("benchmark_dir", "report_dir"):
        if not raw.get(key):
            raise ConfigError(f"{key} 不能为空")
    benchmark_dir = (base / raw["benchmark_dir"]).resolve()
    report_dir = (base / raw["report_dir"]).resolve()

    evaluatee = _load_llm_node(
        "evaluatee_llm", raw.get("evaluatee_llm"), need_conn=(mode == "execute"))
    judge = _load_llm_node(
        "judge_llm", raw.get("judge_llm"), need_conn=(mode == "evaluate"))
    if mode == "evaluate" and not evaluatee.model:
        raise ConfigError("evaluate 模式下 evaluatee_llm.model 不能为空(用于定位报告目录)")

    try:
        concurrency = int(raw.get("concurrency", 4))
        max_retries = int(raw.get("max_retries", 2))
        temperature = float(raw.get("temperature", 0.1))
    except (ValueError, TypeError) as e:
        raise ConfigError(f"concurrency/max_retries/temperature 必须为数值: {e}") from e
    if concurrency < 1:
        raise ConfigError("concurrency 必须为正整数")
    if max_retries < 0:
        raise ConfigError("max_retries 不能为负")
    if not 0.0 <= temperature <= 2.0:
        raise ConfigError("temperature 必须在 0~2 之间")

    return AppConfig(mode, benchmark_dir, report_dir, evaluatee, judge,
                     concurrency, max_retries, temperature)
