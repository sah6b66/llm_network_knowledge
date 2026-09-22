# LLM 网络知识掌握度评估程序 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `llm_eval/` 实现 execute/evaluate 双模式评估程序:执行模式逐题调用被评测 LLM 生成 RECORD,评估模式由裁判 LLM 逐评分点打分生成 EVALUATION 与 summary.md。

**Architecture:** 裁剪复制 `D:\nl2cli_light\src\external_llm\` 的 providers/thinking_handler 作为 LLM client(去掉故障转移与 adaptive);配置中仅 `evaluatee_llm` 与 `judge_llm` 两个同构 LLM 节点,`mode` 决定调用谁;并发 ThreadPoolExecutor + 每题完成即原子重写实现断点续跑;统计由程序计算,仅 summary 结论段调用裁判。

**Tech Stack:** Python 3.10+,唯一第三方依赖 `requests`;测试 pytest(LLM 全部 mock,不打真实 API)。

**Spec:** `docs/superpowers/specs/2026-09-21-llm-network-knowledge-eval-design.md`(本计划从 spec 出发,执行者须同时阅读 spec)

## Global Constraints

- Python ≥3.10;依赖仅 `requests` 与标准库;测试框架 pytest
- 所有 JSON 写出:UTF-8 无 BOM、`ensure_ascii=False`、`indent=2`
- 中文文本内引述一律用「」,禁止 ASCII 双引号进入中文字符串(历史教训:会破坏 JSON)
- 思考模式仅 `enabled`/`disabled` 两值;任何位置不得出现 adaptive
- LLM 调用失败只对同一模型重试退避,绝不切换模型(无 failover)
- 文件名中模型名/思考模式含 Windows 非法字符 `\/:*?"<>|` 时替换为 `-`
- `d:\network_knowledge_set` 本身不是 git 仓库:Task 1 在 `llm_eval/` 内 `git init`(程序自成一仓);若你(执行者)无权初始化 git,则跳过所有 Commit 步骤,其余不变
- 测试命令统一在 `d:\network_knowledge_set` 下执行:`python -m pytest llm_eval/tests/<file> -v`

---

### Task 1: 脚手架 + git 仓库 + fileio + config 模块

**Files:**
- Create: `llm_eval/conftest.py`
- Create: `llm_eval/evaluator/__init__.py`(空)
- Create: `llm_eval/evaluator/fileio.py`
- Create: `llm_eval/evaluator/config.py`
- Create: `llm_eval/requirements.txt`
- Test: `llm_eval/tests/test_fileio.py`、`llm_eval/tests/test_config.py`

**Interfaces:**
- Produces: `atomic_write_json(path: Path, data) -> None`(runner/judge/report 共用)
- Produces: `@dataclass LLMNode(provider, api_url, api_key, model, timeout=300, max_tokens=32768, thinking_mode="disabled")`
- Produces: `@dataclass AppConfig(mode, benchmark_dir: Path, report_dir: Path, evaluatee_llm: LLMNode, judge_llm: LLMNode, concurrency=4, max_retries=2, temperature=0.1)`
- Produces: `class ConfigError(Exception)`;`load_config(config_path: str | Path) -> AppConfig`(相对路径相对配置文件所在目录解析)

- [ ] **Step 1: 建目录与 conftest,git init**

```bash
mkdir -p llm_eval/evaluator llm_eval/tests
cd llm_eval && git init
printf '__pycache__/\nconfig.json\n.pytest_cache/\n' > .gitignore
```

`llm_eval/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
```

`llm_eval/requirements.txt`:

```
requests>=2.28
pytest>=7.0
```

- [ ] **Step 2: 写 fileio 失败测试**

`llm_eval/tests/test_fileio.py`:

```python
import json
from pathlib import Path

from evaluator.fileio import atomic_write_json


def test_atomic_write_json_roundtrip(tmp_path: Path):
    target = tmp_path / "out.json"
    atomic_write_json(target, [{"id": 1, "text": "中文「引号」"}])
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # 无 BOM
    assert json.loads(raw.decode("utf-8")) == [{"id": 1, "text": "中文「引号」"}]


def test_atomic_write_json_no_tmp_left(tmp_path: Path):
    atomic_write_json(tmp_path / "out.json", {"a": 1})
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_atomic_write_json_overwrite(tmp_path: Path):
    target = tmp_path / "out.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 2}
```

- [ ] **Step 3: 运行确认失败**

Run: `python -m pytest llm_eval/tests/test_fileio.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'evaluator.fileio'`

- [ ] **Step 4: 实现 fileio**

`llm_eval/evaluator/fileio.py`:

```python
"""原子 JSON 写出:临时文件 + os.replace,中断不损坏目标文件。"""
from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest llm_eval/tests/test_fileio.py -v`
Expected: 3 passed

- [ ] **Step 6: 写 config 失败测试**

`llm_eval/tests/test_config.py`:

```python
import json

import pytest

from evaluator.config import AppConfig, ConfigError, load_config

VALID = {
    "mode": "execute",
    "benchmark_dir": "../benchmark",
    "report_dir": "../report",
    "evaluatee_llm": {
        "provider": "GLM", "api_url": "https://x/v1", "api_key": "sk-1",
        "model": "glm-4.6", "thinking": {"mode": "enabled"},
    },
    "judge_llm": {
        "provider": "DeepSeek", "api_url": "https://y/v1", "api_key": "sk-2",
        "model": "deepseek-chat", "thinking": {"mode": "disabled"},
    },
    "concurrency": 4, "max_retries": 2, "temperature": 0.1,
}


def _write(tmp_path, cfg):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p


def test_load_valid_execute(tmp_path):
    cfg = load_config(_write(tmp_path, VALID))
    assert isinstance(cfg, AppConfig)
    assert cfg.mode == "execute"
    assert cfg.evaluatee_llm.thinking_mode == "enabled"
    assert cfg.judge_llm.thinking_mode == "disabled"
    # 相对路径相对配置文件目录解析
    assert cfg.benchmark_dir == (tmp_path / "../benchmark").resolve()
    assert cfg.report_dir == (tmp_path / "../report").resolve()


def test_defaults_applied(tmp_path):
    cfg = dict(VALID)
    for k in ("concurrency", "max_retries", "temperature"):
        cfg.pop(k)
    c = load_config(_write(tmp_path, cfg))
    assert (c.concurrency, c.max_retries, c.temperature) == (4, 2, 0.1)


@pytest.mark.parametrize("mutate", [
    lambda c: c.pop("mode"),
    lambda c: c.update(mode="run"),
    lambda c: c.pop("evaluatee_llm"),
    lambda c: c.pop("judge_llm"),
    lambda c: c["evaluatee_llm"].update(api_key=""),
    lambda c: c["evaluatee_llm"].update(model=""),
    lambda c: c["evaluatee_llm"]["thinking"].update(mode="adaptive"),
    lambda c: c.update(concurrency=0),
])
def test_invalid_config_raises(tmp_path, mutate):
    cfg = json.loads(json.dumps(VALID))
    mutate(cfg)
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, cfg))


def test_evaluate_mode_needs_judge_complete_and_model_name(tmp_path):
    cfg = json.loads(json.dumps(VALID))
    cfg["mode"] = "evaluate"
    cfg["judge_llm"].update(api_key="")
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, cfg))
    # evaluate 模式下 evaluatee 只需 model 名(用于目录定位)
    cfg2 = json.loads(json.dumps(VALID))
    cfg2["mode"] = "evaluate"
    cfg2["evaluatee_llm"].update(api_url="", api_key="")
    c = load_config(_write(tmp_path, cfg2))
    assert c.mode == "evaluate"
```

- [ ] **Step 7: 运行确认失败**

Run: `python -m pytest llm_eval/tests/test_config.py -v`
Expected: FAIL,`No module named 'evaluator.config'`

- [ ] **Step 8: 实现 config**

`llm_eval/evaluator/config.py`:

```python
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
    node = LLMNode(
        provider=str(raw.get("provider", "glm")),
        api_url=str(raw.get("api_url", "")),
        api_key=str(raw.get("api_key", "")),
        model=str(raw.get("model", "")),
        timeout=int(raw.get("timeout", 300)),
        max_tokens=int(raw.get("max_tokens", 32768)),
        thinking_mode=mode,
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

    concurrency = int(raw.get("concurrency", 4))
    max_retries = int(raw.get("max_retries", 2))
    temperature = float(raw.get("temperature", 0.1))
    if concurrency < 1:
        raise ConfigError("concurrency 必须为正整数")
    if max_retries < 0:
        raise ConfigError("max_retries 不能为负")
    if not 0.0 <= temperature <= 2.0:
        raise ConfigError("temperature 必须在 0~2 之间")

    return AppConfig(mode, benchmark_dir, report_dir, evaluatee, judge,
                     concurrency, max_retries, temperature)
```

- [ ] **Step 9: 运行确认通过**

Run: `python -m pytest llm_eval/tests/ -v`
Expected: 全部 passed

- [ ] **Step 10: Commit**

```bash
cd llm_eval && git add . && git commit -m "feat: scaffold, atomic json io and config loading"
```

---

### Task 2: LLM client(裁剪复制 nl2cli_light)

**Files:**
- Create: `llm_eval/evaluator/thinking_handler.py`
- Create: `llm_eval/evaluator/llm_client.py`
- Test: `llm_eval/tests/test_llm_client.py`

**Interfaces:**
- Consumes: `LLMNode`(Task 1)
- Produces: `@dataclass ChatResult(success, content="", thinking="", usage: dict = {}, error="", error_type="")`
- Produces: `LLMClient(node: dict, max_retries: int = 2)`;`chat(messages: list[dict], temperature: float = 0.0) -> ChatResult`(内部重试退避,永不抛异常,失败以 `success=False` 返回)

- [ ] **Step 1: 复制 thinking_handler.py(原样)**

```bash
cp D:/nl2cli_light/src/external_llm/thinking_handler.py llm_eval/evaluator/thinking_handler.py
```

整文件原样复制,不修改(内部已含 `CleanedContent`、`extract_openai_compatible`、`extract_anthropic_compatible`、`extract_qianwen_dashscope`、`strip_embedded_thinking`、`strip_free_form_thinking`,Task 5 的 JSON 解析会用到 `strip_free_form_thinking`)。

- [ ] **Step 2: 写失败测试**

`llm_eval/tests/test_llm_client.py`:

```python
from unittest.mock import patch

from evaluator.llm_client import ChatResult, LLMClient, RETRYABLE_ERROR_TYPES

NODE = {"provider": "GLM", "api_url": "https://x/v1", "api_key": "sk-1",
        "model": "glm-4.6", "thinking": {"mode": "enabled"}, "timeout": 5}


def _ok_response(content="答案", thinking="思考", reasoning=False):
    msg = {"role": "assistant", "content": content}
    if reasoning:
        msg["reasoning_content"] = thinking
    return {"choices": [{"message": msg}], "usage": {"prompt_tokens": 10, "completion_tokens": 20}}


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
    def json(self):
        return self._p
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_chat_success_and_thinking_extraction():
    c = LLMClient(dict(NODE))
    with patch.object(c._provider._session, "post",
                      return_value=FakeResp(_ok_response(reasoning=True))):
        r = c.chat([{"role": "user", "content": "q"}], temperature=0.1)
    assert isinstance(r, ChatResult) and r.success
    assert r.content == "答案"
    assert r.thinking == "思考"
    assert r.usage == {"prompt_tokens": 10, "completion_tokens": 20}


def test_thinking_injection_glm_enabled():
    c = LLMClient(dict(NODE))
    p = c._provider._build_payload([{"role": "user", "content": "q"}], temperature=0.1)
    assert p["thinking"] == {"type": "enabled"}
    assert p["model"] == "glm-4.6"


def test_thinking_injection_glm_disabled():
    node = dict(NODE, thinking={"mode": "disabled"})
    p = LLMClient(node)._provider._build_payload([], temperature=0.0)
    assert p["thinking"] == {"type": "disabled"}


def test_thinking_injection_deepseek_reasoning_effort():
    node = dict(NODE, provider="DeepSeek")
    p = LLMClient(node)._provider._build_payload([], temperature=0.0)
    assert p["thinking"] == {"type": "enabled"}
    assert p["reasoning_effort"] == "high"


def test_thinking_injection_openai_reasoning():
    node = dict(NODE, provider="OpenAI")
    p = LLMClient(node)._provider._build_payload([], temperature=0.0)
    assert p["reasoning"] == {"effort": "high"}


def test_thinking_injection_anthropic_by_url():
    node = dict(NODE, provider="Anthropic",
                api_url="https://x/anthropic/v1/messages")
    c = LLMClient(node)
    p = c._provider._build_payload(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}])
    assert p["system"] == "s"
    assert p["thinking"] == {"type": "enabled"}
    assert all(m["role"] != "system" for m in p["messages"])


def test_thinking_injection_dashscope():
    node = dict(NODE, provider="QianWen", api_url="https://x/dashscope/api")
    p = LLMClient(node)._provider._build_payload([], temperature=0.0)
    assert p["parameters"]["enable_thinking"] is True


def test_retry_then_fail_returns_error_result():
    c = LLMClient(dict(NODE), max_retries=1)
    calls = {"n": 0}

    def boom(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        raise TimeoutError("request timed out")

    with patch.object(c._provider._session, "post", side_effect=boom), \
         patch("evaluator.llm_client.time.sleep") as sl:
        r = c.chat([{"role": "user", "content": "q"}])
    assert not r.success
    assert r.error_type in RETRYABLE_ERROR_TYPES
    assert calls["n"] == 2      # 1 次原始 + 1 次重试
    assert sl.call_count == 1   # 重试前退避一次


def test_non_retryable_no_retry():
    c = LLMClient(dict(NODE), max_retries=2)
    calls = {"n": 0}

    def boom(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        return FakeResp({}, status=401)

    with patch.object(c._provider._session, "post", side_effect=boom):
        r = c.chat([{"role": "user", "content": "q"}])
    assert not r.success and r.error_type == "auth"
    assert calls["n"] == 1


def test_env_var_api_key(monkeypatch):
    monkeypatch.setenv("MY_TEST_KEY", "sk-env")
    node = dict(NODE, api_key="${MY_TEST_KEY}")
    c = LLMClient(node)
    assert c._provider.api_key == "sk-env"


def test_invalid_thinking_mode_rejected():
    import pytest
    with pytest.raises(ValueError):
        LLMClient(dict(NODE, thinking={"mode": "adaptive"}))
```

- [ ] **Step 3: 运行确认失败**

Run: `python -m pytest llm_eval/tests/test_llm_client.py -v`
Expected: FAIL,`No module named 'evaluator.llm_client'`

- [ ] **Step 4: 实现 llm_client(从参考文件裁剪)**

以 `D:\nl2cli_light\src\external_llm\providers.py` 为底稿做如下裁剪(逐条执行,其余函数体保持原样复制),另需把模块内 `from .thinking_handler import ...` 的来源改为本包 `evaluator.thinking_handler`:

`llm_eval/evaluator/llm_client.py`:

```python
"""LLM 客户端 — 裁剪自 nl2cli_light providers.py。

保留:多 provider 思考注入、重试指数退避、连接池、ssl_verify、${ENV} key 解析。
裁剪:backup_llm/auto_switch 故障转移、adaptive 思考模式、thinking budget。
chat() 失败不抛异常,以 ChatResult(success=False) 返回。
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

import requests
import requests.adapters
import urllib3

from .thinking_handler import (
    extract_anthropic_compatible,
    extract_openai_compatible,
    extract_qianwen_dashscope,
)

logger = logging.getLogger(__name__)

RETRYABLE_ERROR_TYPES = {"network", "timeout", "quota", "server"}


@dataclass
class ChatResult:
    success: bool
    content: str = ""
    thinking: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    error_type: str = ""


@dataclass
class ProviderConfig:
    include_top_p: bool = True
    use_dashscope_format: bool = False
    response_extractor: Any = extract_openai_compatible
    thinking_strategy: str = "openai_thinking"


_PROVIDER_CONFIGS = {
    "glm": ProviderConfig(),
    "deepseek": ProviderConfig(include_top_p=False, thinking_strategy="deepseek_thinking"),
    "qianwen_dashscope": ProviderConfig(use_dashscope_format=True,
                                        response_extractor=extract_qianwen_dashscope,
                                        thinking_strategy="dashscope_thinking"),
    "qianwen_openai": ProviderConfig(thinking_strategy="qianwen_openai"),
    "anthropic": ProviderConfig(include_top_p=False,
                                response_extractor=extract_anthropic_compatible,
                                thinking_strategy="anthropic_thinking"),
    "openai": ProviderConfig(thinking_strategy="openai_reasoning"),
    "minimax": ProviderConfig(thinking_strategy="minimax_thinking"),
    "vllm": ProviderConfig(thinking_strategy="vllm_thinking"),
}


class _BaseProvider:
    """复制参考实现的 LLMProvider 基类,逐字保留:
    __init__(连接池/ssl_verify/api_key 的 ${ENV} 解析/timeout/max_tokens)、
    _resolve_api_key、_handle_request_error、_execute_request、close。
    修改点:__init__ 去掉 self.config 之外无;保留原样即可。"""

    ERROR_NETWORK = "network"
    ERROR_TIMEOUT = "timeout"
    ERROR_AUTH = "auth"
    ERROR_PERMISSION = "permission"
    ERROR_QUOTA = "quota"
    ERROR_SERVER = "server"
    ERROR_API = "api"

    def __init__(self, config: Dict[str, Any]):
        # —— 以下整段从参考实现 LLMProvider.__init__ 复制 ——
        self.config = config
        self.api_key = self._resolve_api_key(config.get("api_key", ""))
        self.base_url = config.get("api_url", "")
        self.model = config.get("model", "")
        self.timeout = config.get("timeout", 60)
        self.max_tokens = config.get("max_tokens", 32768)

        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=4, pool_maxsize=16, max_retries=0)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        self._ssl_verify = config.get("ssl_verify", True)
        if not self._ssl_verify:
            self._session.verify = False
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def close(self):
        self._session.close()

    def _resolve_api_key(self, api_key: str) -> str:
        import os
        if api_key.startswith("${") and api_key.endswith("}"):
            return os.environ.get(api_key[2:-1], api_key)
        return api_key

    def _handle_request_error(self, e: Exception) -> Dict[str, Any]:
        # —— 从参考实现逐字复制(错误类型分类) ——
        error_msg = str(e)
        low = error_msg.lower()
        if "timed out" in low or "timeout" in low:
            t = self.ERROR_TIMEOUT
        elif "401" in error_msg or "unauthorized" in low:
            t = self.ERROR_AUTH
        elif "403" in error_msg or "forbidden" in low:
            t = self.ERROR_PERMISSION
        elif "429" in error_msg or "too many requests" in low:
            t = self.ERROR_QUOTA
        elif "500" in error_msg or "502" in error_msg or "503" in error_msg:
            t = self.ERROR_SERVER
        else:
            t = self.ERROR_NETWORK
        return {"success": False, "error": error_msg, "error_type": t, "content": ""}

    def _execute_request(self, headers: Dict, payload: Dict) -> Dict[str, Any]:
        # —— 从参考实现逐字复制(POST + 状态码分支 + code!=0 分支 + _extract_response) ——
        try:
            response = self._session.post(
                self.base_url, headers=headers, json=payload, timeout=self.timeout)
            if response.status_code == 401:
                return self._handle_request_error(Exception("401 Unauthorized: API密钥无效或已过期"))
            if response.status_code == 403:
                return self._handle_request_error(Exception("403 Forbidden: 权限不足"))
            if response.status_code == 429:
                return self._handle_request_error(Exception("429 Too Many Requests: API额度不足或请求过于频繁"))
            if response.status_code >= 500:
                return self._handle_request_error(
                    Exception(f"{response.status_code} Server Error: 服务器错误"))
            response.raise_for_status()
            result = response.json()
            if result.get("code") and result.get("code") not in (0, 200):
                return {"success": False, "error": f"API错误: {result.get('msg', 'Unknown')}",
                        "error_type": self.ERROR_API, "content": "", "raw": result}
            return self._extract_response(result)
        except requests.exceptions.Timeout:
            return self._handle_request_error(Exception("请求超时"))
        except requests.exceptions.ConnectionError as e:
            return self._handle_request_error(Exception(f"网络连接失败: {str(e)}"))
        except Exception as e:
            return self._handle_request_error(e)

    def _extract_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class OpenAICompatibleProvider(_BaseProvider):
    """从参考实现复制 OpenAICompatibleProvider,修改点:
    - _inject_thinking 删除 budget 参数与 adaptive 相关分支:
        * deepseek_thinking: 保留 type 注入;mode != disabled 时 reasoning_effort="high"(去掉 budget 映射)
        * dashscope_thinking / qianwen_openai: enable_thinking 布尔(去掉 thinking_budget)
        * openai_reasoning: effort_map 仅 {"disabled": "none", "enabled": "high"}
        * anthropic 分支不在此类
    - 其余(_build_headers/_build_payload/_extract_response/chat)逐字复制"""

    def __init__(self, config: Dict[str, Any], provider_config: ProviderConfig):
        super().__init__(config)
        self._pc = provider_config

    def _build_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"}

    def _build_payload(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        if self._pc.use_dashscope_format:
            params = {"temperature": kwargs.get("temperature", 0.7),
                      "max_tokens": kwargs.get("max_tokens", self.max_tokens)}
            if self._pc.include_top_p:
                params["top_p"] = kwargs.get("top_p", 0.9)
            payload = {"model": kwargs.get("model", self.model),
                       "input": {"messages": messages}, "parameters": params}
        else:
            payload = {"model": kwargs.get("model", self.model), "messages": messages,
                       "temperature": kwargs.get("temperature", 0.7),
                       "max_tokens": kwargs.get("max_tokens", self.max_tokens)}
            if self._pc.include_top_p:
                payload["top_p"] = kwargs.get("top_p", 0.9)
        mode = self.config.get("thinking_mode", "disabled")
        self._inject_thinking(payload, mode)
        return payload

    def _inject_thinking(self, payload: Dict, mode: str) -> None:
        strategy = self._pc.thinking_strategy
        if strategy == "openai_thinking":
            payload["thinking"] = {"type": mode}
        elif strategy == "deepseek_thinking":
            payload["thinking"] = {"type": mode}
            if mode != "disabled":
                payload["reasoning_effort"] = "high"
        elif strategy == "dashscope_thinking":
            target = payload.get("parameters", payload)
            target["enable_thinking"] = (mode != "disabled")
        elif strategy == "qianwen_openai":
            payload["enable_thinking"] = (mode != "disabled")
        elif strategy == "openai_reasoning":
            effort_map = {"disabled": "none", "enabled": "high"}
            payload["reasoning"] = {"effort": effort_map.get(mode, "none")}
        elif strategy == "minimax_thinking":
            payload["reasoning_split"] = (mode != "disabled")
        elif strategy == "vllm_thinking":
            payload["chat_template_kwargs"] = {"enable_thinking": (mode != "disabled")}

    def _extract_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = self._pc.response_extractor(result)
        return {"success": True, "content": cleaned.content,
                "thinking": cleaned.thinking, "usage": result.get("usage", {}), "raw": result}

    def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        return self._execute_request(self._build_headers(),
                                     self._build_payload(messages, **kwargs))


class AnthropicCompatibleProvider(_BaseProvider):
    """从参考实现复制,修改点:_inject_thinking 只注入 {"type": mode},删除 budget/adaptive。"""

    def __init__(self, config: Dict[str, Any], provider_config: ProviderConfig):
        super().__init__(config)
        self._pc = provider_config

    def _build_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"}

    def _transform_messages(self, messages: List[Dict]):
        system_message, user_messages = "", []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                user_messages.append({"role": msg["role"], "content": msg["content"]})
        return system_message, user_messages

    def _build_payload(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        system_message, user_messages = self._transform_messages(messages)
        payload = {"model": kwargs.get("model", self.model),
                   "messages": user_messages,
                   "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                   "temperature": kwargs.get("temperature", 0.7)}
        if system_message:
            payload["system"] = system_message
        payload["thinking"] = {"type": self.config.get("thinking_mode", "disabled")}
        return payload

    def _extract_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = extract_anthropic_compatible(result)
        return {"success": True, "content": cleaned.content,
                "thinking": cleaned.thinking, "usage": result.get("usage", {}), "raw": result}

    def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        return self._execute_request(self._build_headers(),
                                     self._build_payload(messages, **kwargs))


def _create_provider(node: Dict[str, Any]) -> _BaseProvider:
    """从参考实现 LLMClient._create_provider 裁剪:去掉 backup/全局配置继承;
    anthropic 兼容按 URL 判定,千问按 provider 名+api_format/URL 分流,其余按名字查表。"""
    provider_name = str(node.get("provider", "glm")).lower()
    api_url = node.get("api_url", "")

    if "/anthropic" in api_url or "/api/anthropic" in api_url:
        return AnthropicCompatibleProvider(node, _PROVIDER_CONFIGS["anthropic"])

    if provider_name in ("qianwen", "qw", "dashscope"):
        api_format = str(node.get("api_format", "")).lower()
        is_openai_compatible = (
            api_format == "openai" or "compatible-mode" in api_url
            or "/v1/chat/completions" in api_url)
        key = "qianwen_openai" if is_openai_compatible else "qianwen_dashscope"
        return OpenAICompatibleProvider(node, _PROVIDER_CONFIGS[key])

    table = {"openai": "openai", "gpt": "openai", "minimax": "minimax",
             "deepseek": "deepseek", "vllm": "vllm"}
    return OpenAICompatibleProvider(node, _PROVIDER_CONFIGS[table.get(provider_name, "glm")])


class LLMClient:
    """单 provider 客户端:重试 + 指数退避,无故障转移。"""

    def __init__(self, node: Dict[str, Any], max_retries: int = 2):
        node = dict(node)
        if not isinstance(node.get("thinking"), dict):
            node["thinking"] = {}
        mode = node["thinking"].get("mode", node.get("thinking_mode", "disabled"))
        if mode not in ("enabled", "disabled"):
            raise ValueError(f"thinking.mode 仅支持 enabled/disabled,收到:{mode!r}")
        node["thinking_mode"] = mode
        node.setdefault("timeout", 300)
        node.setdefault("max_tokens", 32768)
        self.model = str(node.get("model", ""))
        self.max_retries = max(0, int(max_retries))
        self._provider = _create_provider(node)

    def close(self):
        self._provider.close()

    @staticmethod
    def _backoff(attempt: int) -> float:
        base = min(1.0 * (2 ** attempt), 30.0)
        return base + random.uniform(0, base * 0.5)

    def chat(self, messages: List[Dict], temperature: float = 0.0) -> ChatResult:
        last = ChatResult(False, error="未发起调用")
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            result = self._provider.chat(messages, temperature=temperature)
            if result.get("success"):
                return ChatResult(True, content=result.get("content", ""),
                                  thinking=result.get("thinking", ""),
                                  usage=result.get("usage", {}) or {})
            last = ChatResult(False, error=str(result.get("error", "")),
                              error_type=str(result.get("error_type", "")))
            retryable = last.error_type in RETRYABLE_ERROR_TYPES
            if retryable and attempt < attempts - 1:
                time.sleep(self._backoff(attempt))
                continue
            break
        return last
```

注意:若 thinking_handler.py 的 `extract_*` 函数对 GLM 类响应未把 `reasoning_content` 并入 thinking,以参考实现实际行为为准(测试 `_ok_response(reasoning=True)` 与参考实现的提取逻辑一致即为正确,不要为测试改提取逻辑)。

- [ ] **Step 5: 运行确认通过(必要时对照参考实现修正提取函数假设)**

Run: `python -m pytest llm_eval/tests/test_llm_client.py -v`
Expected: 11 passed。若 thinking 提取断言失败,读 `evaluator/thinking_handler.py` 中 `extract_openai_compatible` 的真实行为,修正**测试**中的响应构造使其匹配(实现不改)。

- [ ] **Step 6: Commit**

```bash
cd llm_eval && git add . && git commit -m "feat: llm client trimmed from nl2cli_light (no failover, no adaptive)"
```

---

### Task 3: benchmark 发现与校验

**Files:**
- Create: `llm_eval/evaluator/benchmark.py`
- Test: `llm_eval/tests/test_benchmark.py`

**Interfaces:**
- Produces: `discover_datasets(benchmark_dir: Path) -> list[Path]`(文件名以 `dataset` 开头、`.json` 结尾,按名排序)
- Produces: `validate_dataset(path: Path) -> tuple[list[dict] | None, list[str]]`(合法返回 `(cases, [])`;否则 `(None, errors)`,错误信息含 1 起始条目序号与字段名)
- Produces: `load_benchmark(benchmark_dir: Path) -> list[tuple[Path, list[dict]]]`(打印跳过信息,返回全部合法文件;目录不存在或无合法文件时报错)

- [ ] **Step 1: 写失败测试**

`llm_eval/tests/test_benchmark.py`:

```python
import json

import pytest

from evaluator.benchmark import discover_datasets, load_benchmark, validate_dataset

CASE = {"id": 1, "difficulty": "中",
        "category": {"scope": "网络", "protocol_layer": "IP层", "lifecycle": "维护"},
        "scenario": "园区", "device_type": "路由器",
        "question": "问题?", "answer": "答案",
        "scoring_points": ["要点1"], "tags": ["OSPF"]}


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_discover_filters_and_sorts(tmp_path):
    _write(tmp_path, "dataset_b.json", [CASE])
    _write(tmp_path, "dataset_a.json", [CASE])
    _write(tmp_path, "topics.json", [CASE])
    _write(tmp_path, "record.json", [CASE])
    names = [p.name for p in discover_datasets(tmp_path)]
    assert names == ["dataset_a.json", "dataset_b.json"]


def test_validate_ok(tmp_path):
    cases, errs = validate_dataset(_write(tmp_path, "dataset_x.json",
                                          [{**CASE, "id": 1}, {**CASE, "id": 2}]))
    assert errs == [] and len(cases) == 2


def test_validate_not_array(tmp_path):
    cases, errs = validate_dataset(_write(tmp_path, "dataset_x.json", {"a": 1}))
    assert cases is None and errs and "数组" in errs[0]


def test_validate_empty_array(tmp_path):
    cases, errs = validate_dataset(_write(tmp_path, "dataset_x.json", []))
    assert cases is None and errs


def test_validate_missing_field_with_index(tmp_path):
    bad = {k: v for k, v in CASE.items() if k != "scoring_points"}
    cases, errs = validate_dataset(_write(tmp_path, "dataset_x.json", [CASE, bad]))
    assert cases is None
    assert any("第 2 条" in e and "scoring_points" in e for e in errs)


def test_validate_bad_category(tmp_path):
    bad = {**CASE, "category": {"scope": "网络"}}
    _, errs = validate_dataset(_write(tmp_path, "dataset_x.json", [bad]))
    assert any("category" in e for e in errs)


def test_validate_empty_question(tmp_path):
    _, errs = validate_dataset(_write(tmp_path, "dataset_x.json", [{**CASE, "question": ""}]))
    assert any("question" in e for e in errs)


def test_validate_duplicate_id(tmp_path):
    _, errs = validate_dataset(_write(tmp_path, "dataset_x.json",
                                      [CASE, {**CASE, "id": 1}]))
    assert any("id" in e and "唯一" in e for e in errs)


def test_load_benchmark_skips_invalid(tmp_path, capsys):
    _write(tmp_path, "dataset_good.json", [CASE])
    _write(tmp_path, "dataset_bad.json", [{"no": "fields"}])
    loaded = load_benchmark(tmp_path)
    assert [p.name for p, _ in loaded] == ["dataset_good.json"]
    out = capsys.readouterr().out
    assert "dataset_bad.json" in out and "已跳过" in out


def test_load_benchmark_no_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_benchmark(tmp_path / "nope")


def test_load_benchmark_no_valid(tmp_path):
    _write(tmp_path, "dataset_bad.json", [{"no": "fields"}])
    with pytest.raises(RuntimeError):
        load_benchmark(tmp_path)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest llm_eval/tests/test_benchmark.py -v`
Expected: FAIL,`No module named 'evaluator.benchmark'`

- [ ] **Step 3: 实现 benchmark**

`llm_eval/evaluator/benchmark.py`:

```python
"""benchmark 数据集发现与格式校验。"""
from __future__ import annotations

import json
from pathlib import Path

_STR_FIELDS = ("difficulty", "scenario", "device_type", "answer")
_CATEGORY_KEYS = ("scope", "protocol_layer", "lifecycle")


def discover_datasets(benchmark_dir: Path) -> list[Path]:
    if not benchmark_dir.is_dir():
        raise FileNotFoundError(f"benchmark 目录不存在:{benchmark_dir}")
    return sorted(p for p in benchmark_dir.glob("dataset*.json") if p.suffix == ".json")


def _check_str_fields(item: dict, idx: int, errors: list[str]) -> None:
    for f in _STR_FIELDS:
        if not isinstance(item.get(f), str):
            errors.append(f"第 {idx} 条字段 {f} 缺失或不是字符串")
    q = item.get("question")
    if not (isinstance(q, str) and q.strip()):
        errors.append(f"第 {idx} 条字段 question 缺失或为空")
    sp = item.get("scoring_points")
    if not (isinstance(sp, list) and sp
            and all(isinstance(x, str) for x in sp)):
        errors.append(f"第 {idx} 条字段 scoring_points 必须为非空字符串数组")
    tags = item.get("tags")
    if not (isinstance(tags, list) and all(isinstance(x, str) for x in tags)):
        errors.append(f"第 {idx} 条字段 tags 必须为字符串数组")
    cat = item.get("category")
    if not isinstance(cat, dict):
        errors.append(f"第 {idx} 条字段 category 缺失或不是对象")
    else:
        for k in _CATEGORY_KEYS:
            if not isinstance(cat.get(k), str):
                errors.append(f"第 {idx} 条 category.{k} 缺失或不是字符串")


def validate_dataset(path: Path) -> tuple[list[dict] | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, [f"{path.name}: JSON 解析失败({e})"]
    if not isinstance(data, list):
        return None, [f"{path.name}: 顶层必须是数组"]
    if not data:
        return None, [f"{path.name}: 数组为空"]

    errors: list[str] = []
    seen_ids: set[int] = set()
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            errors.append(f"第 {idx} 条不是对象")
            continue
        i = item.get("id")
        if not isinstance(i, int) or isinstance(i, bool):
            errors.append(f"第 {idx} 条字段 id 缺失或不是整数")
        elif i in seen_ids:
            errors.append(f"第 {idx} 条 id={i} 重复,id 必须唯一")
        else:
            seen_ids.add(i)
        _check_str_fields(item, idx, errors)

    if errors:
        return None, errors
    return data, []


def load_benchmark(benchmark_dir: Path) -> list[tuple[Path, list[dict]]]:
    loaded: list[tuple[Path, list[dict]]] = []
    for path in discover_datasets(benchmark_dir):
        cases, errors = validate_dataset(path)
        if cases is None:
            print(f"[跳过] {path.name} 格式不正确:{';'.join(errors[:5])}"
                  + ("..." if len(errors) > 5 else "") + " 已跳过")
            continue
        loaded.append((path, cases))
    if not loaded:
        raise RuntimeError(f"{benchmark_dir} 下没有格式合法的 dataset*.json 文件")
    return loaded
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest llm_eval/tests/test_benchmark.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
cd llm_eval && git add . && git commit -m "feat: benchmark discovery and schema validation"
```

---

### Task 4: 执行模式 runner

**Files:**
- Create: `llm_eval/evaluator/runner.py`
- Test: `llm_eval/tests/test_runner.py`

**Interfaces:**
- Consumes: `AppConfig`/`LLMNode`(Task 1)、`LLMClient.chat(messages, temperature) -> ChatResult`(Task 2)、`load_benchmark`(Task 3)、`atomic_write_json`(Task 1)
- Produces: `sanitize_name(s: str) -> str`
- Produces: `record_path(report_dir: Path, model: str, thinking_mode: str, dataset_stem: str) -> Path`
- Produces: `run_execute(cfg: AppConfig, client) -> None`(client 只需具备 `chat(messages, temperature) -> ChatResult` 协议;打印统计)

- [ ] **Step 1: 写失败测试**

`llm_eval/tests/test_runner.py`:

```python
import json

from evaluator.config import AppConfig, LLMNode
from evaluator.llm_client import ChatResult
from evaluator.runner import record_path, run_execute, sanitize_name


def _cfg(tmp_path):
    return AppConfig(
        mode="execute",
        benchmark_dir=tmp_path / "benchmark",
        report_dir=tmp_path / "report",
        evaluatee_llm=LLMNode("GLM", "https://x", "sk", "glm-4.6",
                              thinking_mode="enabled"),
        judge_llm=LLMNode("GLM", "https://x", "sk", "judge"),
        concurrency=2, max_retries=0, temperature=0.1)


def _dataset(tmp_path, name="dataset_unit.json"):
    d = tmp_path / "benchmark"
    d.mkdir(exist_ok=True)
    cases = [{
        "id": i, "difficulty": "中",
        "category": {"scope": "网络", "protocol_layer": "IP层", "lifecycle": "维护"},
        "scenario": "园区", "device_type": "路由器",
        "question": f"问题{i}?", "answer": f"答案{i}",
        "scoring_points": ["要点"], "tags": ["T"],
    } for i in (1, 2)]
    p = d / name
    p.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    return p


class FakeClient:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def chat(self, messages, temperature=0.0):
        self.calls.append((messages, temperature))
        return self._results.pop(0)


def _ok(content="答"):
    return ChatResult(True, content=content, usage={"prompt_tokens": 1})


def test_sanitize_name():
    assert sanitize_name('a/b\\c:d*e?f"g<h>i|j') == "a-b-c-d-e-f-g-h-i-j"


def test_record_path():
    p = record_path(_cfg(__import__("pathlib").Path(".")).report_dir,
                    "glm-4.6", "enabled", "dataset_detail")
    assert p.name == "RECORD_glm-4.6_enabled_dataset_detail.json"


def test_run_execute_writes_record(tmp_path):
    cfg = _cfg(tmp_path)
    _dataset(tmp_path)
    client = FakeClient([_ok("答1"), _ok("答2")])
    run_execute(cfg, client)
    out = record_path(cfg.report_dir, "glm-4.6", "enabled", "dataset_unit")
    items = json.loads(out.read_text(encoding="utf-8"))
    assert len(items) == 2
    mr = items[0]["model_response"]
    assert mr["status"] == "ok" and mr["answer"] == "答1"
    assert mr["model"] == "glm-4.6" and mr["thinking_mode"] == "enabled"
    assert mr["latency_ms"] >= 0 and mr["error"] is None
    assert mr["usage"] == {"prompt_tokens": 1}
    # 原字段保留且顺序:model_response 在最后
    assert list(items[0])[-1] == "model_response"
    assert items[0]["question"] == "问题1?"
    # 被评测 prompt:user 为题目原文
    msgs, temp = client.calls[0]
    assert msgs[-1]["content"] == "问题1?" and temp == 0.1


def test_run_execute_resume_skips_ok(tmp_path):
    cfg = _cfg(tmp_path)
    _dataset(tmp_path)
    out = record_path(cfg.report_dir, "glm-4.6", "enabled", "dataset_unit")
    done = json.loads(_dataset(tmp_path).read_text(encoding="utf-8"))
    done[0]["model_response"] = {"answer": "旧答案", "status": "ok", "error": None,
                                 "latency_ms": 1, "usage": {},
                                 "model": "glm-4.6", "thinking_mode": "enabled"}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
    client = FakeClient([_ok("新答案2")])  # 只会问第 2 题
    run_execute(cfg, client)
    assert len(client.calls) == 1
    items = json.loads(out.read_text(encoding="utf-8"))
    assert items[0]["model_response"]["answer"] == "旧答案"


def test_run_execute_reasks_when_question_changed(tmp_path):
    cfg = _cfg(tmp_path)
    _dataset(tmp_path)
    out = record_path(cfg.report_dir, "glm-4.6", "enabled", "dataset_unit")
    old = json.loads(_dataset(tmp_path).read_text(encoding="utf-8"))
    old[0]["question"] = "旧的问题1?"   # 与当前数据集不同
    old[0]["model_response"] = {"answer": "旧", "status": "ok", "error": None,
                                "latency_ms": 1, "usage": {},
                                "model": "glm-4.6", "thinking_mode": "enabled"}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    client = FakeClient([_ok("重答1"), _ok("答2")])
    run_execute(cfg, client)
    assert len(client.calls) == 2


def test_run_execute_error_recorded_not_fatal(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    _dataset(tmp_path)
    client = FakeClient([ChatResult(False, error="网络失败", error_type="network"), _ok()])
    run_execute(cfg, client)
    out = record_path(cfg.report_dir, "glm-4.6", "enabled", "dataset_unit")
    items = json.loads(out.read_text(encoding="utf-8"))
    statuses = sorted(i["model_response"]["status"] for i in items)
    assert statuses == ["error", "ok"]
    assert items[0]["model_response"].get("error") or items[1]["model_response"].get("error")
    out_log = capsys.readouterr().out
    assert "失败" in out_log
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest llm_eval/tests/test_runner.py -v`
Expected: FAIL,`No module named 'evaluator.runner'`

- [ ] **Step 3: 实现 runner**

`llm_eval/evaluator/runner.py`:

```python
"""执行模式:逐题调用被评测 LLM,生成 RECORD 文件(并发+断点续跑)。"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .benchmark import load_benchmark
from .config import AppConfig
from .fileio import atomic_write_json

SYSTEM_PROMPT_EXECUTE = "你是一位资深网络技术专家,请准确、完整地回答网络技术问题。"

_ILLEGAL = '\\/:*?"<>|'


def sanitize_name(s: str) -> str:
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest llm_eval/tests/test_runner.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd llm_eval && git add . && git commit -m "feat: execute mode runner with concurrency and resume"
```

---

### Task 5: 评估模式 judge

**Files:**
- Create: `llm_eval/evaluator/judge.py`
- Test: `llm_eval/tests/test_judge.py`

**Interfaces:**
- Consumes: `AppConfig`(Task 1)、`LLMClient.chat`(Task 2)、`atomic_write_json`(Task 1)、`sanitize_name`(Task 4)
- Produces: `RECORD_NAME_RE`;`parse_record_filename(name: str) -> tuple[str, str, str] | None`(模型名, 思考模式, stem)
- Produces: `JUDGE_SYSTEM_PROMPT`、`build_judge_prompt(case: dict) -> str`
- Produces: `parse_judge_json(text: str) -> dict | None`(校验 point_results/score 结构,不合法返回 None)
- Produces: `run_evaluate(cfg: AppConfig, client) -> None`(含 EVALUATION 写出与断点;summary 由 Task 6 的 `run_summaries` 收尾——本任务先留调用点)

- [ ] **Step 1: 写失败测试**

`llm_eval/tests/test_judge.py`:

```python
import json

from evaluator.judge import (
    build_judge_prompt, parse_judge_json, parse_record_filename)
from evaluator.llm_client import ChatResult

CASE = {"id": 7, "question": "问?", "answer": "参考答案",
        "scoring_points": ["要点A", "要点B"],
        "model_response": {"answer": "模型回答", "status": "ok"}}


def test_parse_record_filename():
    assert parse_record_filename("RECORD_glm-4.6_enabled_dataset_detail.json") == \
        ("glm-4.6", "enabled", "dataset_detail")
    assert parse_record_filename("RECORD_my_model_disabled_dataset_basic.json") == \
        ("my_model", "disabled", "dataset_basic")
    assert parse_record_filename("RECORD_glm-4.6_adaptive_dataset_x.json") is None
    assert parse_record_filename("topics.json") is None


def test_build_judge_prompt_contains_all_parts():
    p = build_judge_prompt(CASE)
    for part in ("问?", "参考答案", "要点A", "要点B", "模型回答", "point_results", "score"):
        assert part in p


def test_parse_judge_json_plain():
    text = json.dumps({"point_results": [
        {"point": "要点A", "hit": True, "comment": "命中"}],
        "score": 4, "comment": "良好"}, ensure_ascii=False)
    r = parse_judge_json(text)
    assert r["score"] == 4 and r["point_results"][0]["hit"] is True


def test_parse_judge_json_code_block():
    text = "评估如下:\n```json\n{\"point_results\": [], \"score\": 3, \"comment\": \"c\"}\n```"
    assert parse_judge_json(text)["score"] == 3


def test_parse_judge_json_with_leading_thinking_text():
    text = "让我分析一下……{\"point_results\": [], \"score\": 2, \"comment\": \"c\"}"
    assert parse_judge_json(text)["score"] == 2


def test_parse_judge_json_invalid_score():
    assert parse_judge_json('{"point_results": [], "score": 9, "comment": "c"}') is None
    assert parse_judge_json('{"point_results": [], "score": "4", "comment": "c"}') is None
    assert parse_judge_json("完全不是 JSON") is None
```

再加集成测试(评估流程与断点),`llm_eval/tests/test_judge_run.py`:

```python
import json
from pathlib import Path

from evaluator.config import AppConfig, LLMNode
from evaluator.judge import run_evaluate
from evaluator.llm_client import ChatResult


def _cfg(tmp_path: Path) -> AppConfig:
    return AppConfig(
        mode="evaluate",
        benchmark_dir=tmp_path / "benchmark", report_dir=tmp_path / "report",
        evaluatee_llm=LLMNode("GLM", "https://x", "sk", "eval-model",
                              thinking_mode="enabled"),
        judge_llm=LLMNode("GLM", "https://x", "sk", "judge-model"),
        concurrency=2, max_retries=0)


def _record(tmp_path: Path, answered=2):
    d = tmp_path / "report" / "eval-model"
    d.mkdir(parents=True)
    items = []
    for i in range(1, answered + 1):
        items.append({
            "id": i, "difficulty": "中",
            "category": {"scope": "网络", "protocol_layer": "IP层", "lifecycle": "维护"},
            "scenario": "园区", "device_type": "路由器",
            "question": f"问题{i}?", "answer": f"答案{i}",
            "scoring_points": ["要点"], "tags": ["T"],
            "model_response": {"answer": f"答{i}", "status": "ok", "error": None,
                               "latency_ms": 1, "usage": {},
                               "model": "eval-model", "thinking_mode": "enabled"},
        })
    p = d / "RECORD_eval-model_enabled_dataset_unit.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return p


class FakeClient:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def chat(self, messages, temperature=0.0):
        self.calls.append((messages, temperature))
        return self._results.pop(0)


def _judge_payload(score=4):
    return ChatResult(True, content=json.dumps(
        {"point_results": [{"point": "要点", "hit": True, "comment": "ok"}],
         "score": score, "comment": "总评"}, ensure_ascii=False))


def test_run_evaluate_writes_evaluation(tmp_path):
    cfg = _cfg(tmp_path)
    _record(tmp_path)
    client = FakeClient([_judge_payload(4), _judge_payload(5)])
    run_evaluate(cfg, client)
    out = tmp_path / "report" / "eval-model" / \
        "EVALUATION_judge-model_eval-model_enabled_dataset_unit.json"
    items = json.loads(out.read_text(encoding="utf-8"))
    assert [it["evaluation"]["score"] for it in items] == [4, 5]
    assert items[0]["evaluation"]["judge_model"] == "judge-model"
    assert list(items[0])[-1] == "evaluation"
    msgs, temp = client.calls[0]
    assert temp == 0.0


def test_run_evaluate_resume_skips_scored(tmp_path):
    cfg = _cfg(tmp_path)
    _record(tmp_path)
    client = FakeClient([_judge_payload(4)])  # 只评第 1 题
    run_evaluate(cfg, client) if False else None
    # 先正常评一题制造半成品:
    import evaluator.judge as J
    out = tmp_path / "report" / "eval-model" / \
        "EVALUATION_judge-model_eval-model_enabled_dataset_unit.json"
    items = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    # 直接构造半成品文件:
    half = json.loads((tmp_path / "report" / "eval-model" /
                       "RECORD_eval-model_enabled_dataset_unit.json")
                      .read_text(encoding="utf-8"))
    half[0]["evaluation"] = {"judge_model": "judge-model",
                             "point_results": [{"point": "要点", "hit": True,
                                                "comment": "ok"}],
                             "score": 3, "comment": "旧"}
    out.write_text(json.dumps(half[:1], ensure_ascii=False), encoding="utf-8")
    client2 = FakeClient([_judge_payload(5)])
    run_evaluate(cfg, client2)
    assert len(client2.calls) == 1
    final = json.loads(out.read_text(encoding="utf-8"))
    assert final[0]["evaluation"]["score"] == 3      # 已评分的保留
    assert final[1]["evaluation"]["score"] == 5      # 未评分的新评


def test_run_evaluate_parse_fail_marks_null(tmp_path):
    cfg = _cfg(tmp_path)
    _record(tmp_path, answered=1)
    client = FakeClient([ChatResult(True, content="垃圾输出"),
                         ChatResult(True, content="还是垃圾")])
    run_evaluate(cfg, client)
    out = tmp_path / "report" / "eval-model" / \
        "EVALUATION_judge-model_eval-model_enabled_dataset_unit.json"
    items = json.loads(out.read_text(encoding="utf-8"))
    ev = items[0]["evaluation"]
    assert ev["score"] is None and "parse_error" in ev
    assert len(client.calls) == 2  # 首评 + 重试一次
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest llm_eval/tests/test_judge.py llm_eval/tests/test_judge_run.py -v`
Expected: FAIL,`No module named 'evaluator.judge'`

- [ ] **Step 3: 实现 judge**

`llm_eval/evaluator/judge.py`:

```python
"""评估模式:裁判 LLM 逐评分点判定 + 总分,生成 EVALUATION 文件。"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import AppConfig
from .fileio import atomic_write_json
from .runner import sanitize_name
from .thinking_handler import strip_free_form_thinking

RECORD_NAME_RE = re.compile(r"^RECORD_(.+)_(enabled|disabled)_(dataset.+)\.json$")
EVALUATION_NAME_TMPL = "EVALUATION_{judge}_{model}_{thinking}_{stem}.json"

JUDGE_SYSTEM_PROMPT = (
    "你是网络技术领域的资深评审专家。你需要根据题目、参考答案与评分要点,"
    "评判被评测模型回答的质量,并严格按照指定的 JSON 格式输出评分结果,"
    "不要输出 JSON 以外的任何内容。")


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
1. 逐条判断「评分要点」在回答中是否命中:hit 为 true/false,comment 用一句话给出判定依据
2. 综合给出 1-5 的整数总分:5=完全掌握,4=大部分掌握,3=基本掌握,2=掌握较差,1=基本未掌握
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
            else:
                work.append(None)
                todo.append(item)
        index_by_id = {it["id"]: i for i, it in enumerate(items) if "id" in it}
        print(f"[{rec_path.name}] 共 {len(items)} 题,续跑跳过 "
              f"{len(items) - len(todo)},新评估 {len(todo)}")

        if todo:
            with ThreadPoolExecutor(max_workers=cfg.concurrency) as ex:
                futures = {ex.submit(_judge_one, client, it, judge_model): it
                           for it in todo}
                for fut in as_completed(futures):
                    item = futures[fut]
                    ev = fut.result()
                    merged = dict(item)
                    merged["evaluation"] = ev
                    if item.get("id") in index_by_id:
                        work[index_by_id[item["id"]]] = merged
                    atomic_write_json(out, [w for w in work if w is not None]
                                      if None in work else work)
        else:
            atomic_write_json(out, [w for w in work if w is not None])
        produced.append((thinking, out))

    from .report import run_summaries
    run_summaries(cfg, client, produced)
```

注意上面 `atomic_write_json` 的写出内容在 todo 完成过程中可能含 None 占位——修正实现时改为:写出前把 `work` 中 None 位置用**原始 RECORD item**(无 evaluation)填充,保证 EVALUATION 文件任意时刻都是完整数组。实现这一点的正确写法:

```python
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
            atomic_write_json(out, list(items))
```

以这段正确写法为准替换前面对应代码块。

- [ ] **Step 4: 运行确认通过(此时 run_summaries 尚未实现,先临时注释调用再恢复)**

Run: `python -m pytest llm_eval/tests/test_judge.py -v`
Expected: 6 passed
(`test_judge_run.py` 依赖 Task 6 的 `run_summaries`,本步先只跑纯函数测试;实现 Task 6 后回跑全量)

- [ ] **Step 5: Commit**

```bash
cd llm_eval && git add . && git commit -m "feat: judge mode with point-wise scoring and resume"
```

---

### Task 6: summary 报告

**Files:**
- Create: `llm_eval/evaluator/report.py`
- Test: `llm_eval/tests/test_report.py`

**Interfaces:**
- Consumes: `AppConfig`、`LLMClient.chat`、`atomic_write_json`、`sanitize_name`、Task 5 传入的 `produced: list[tuple[str, Path]]`
- Produces: `compute_stats(files: list[Path]) -> dict`(键:`total/answered/answered_errors/parse_errors/avg/distribution/dims/point_rates/gaps/low_scores`)
- Produces: `render_summary_md(meta: dict, per_stem: dict[str, dict], overall: dict, conclusion: str) -> str`
- Produces: `run_summaries(cfg: AppConfig, client, produced: list[tuple[str, Path]]) -> None`(按思考模式分组,每模式一份 summary;结论由裁判生成,失败时落固定文案)

- [ ] **Step 1: 写失败测试**

`llm_eval/tests/test_report.py`:

```python
import json
from pathlib import Path

from evaluator.report import compute_stats, render_summary_md, run_summaries


def _item(i, score, cat=("网络", "IP层", "维护"), diff="中", scen="园区",
           dev="路由器", hit=True, mr_status="ok"):
    return {
        "id": i, "difficulty": diff,
        "category": {"scope": cat[0], "protocol_layer": cat[1], "lifecycle": cat[2]},
        "scenario": scen, "device_type": dev,
        "question": f"q{i}", "answer": "a",
        "scoring_points": ["要点A", "要点B"], "tags": [],
        "model_response": {"answer": "ans", "status": mr_status},
        "evaluation": (None if score is None else {
            "judge_model": "J", "score": score, "comment": "c",
            "point_results": [
                {"point": "要点A", "hit": hit, "comment": ""},
                {"point": "要点B", "hit": False, "comment": ""}]}),
    }


def _eval_file(tmp_path: Path, name, items):
    d = tmp_path / "report" / "m"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return p


def test_compute_stats_basic(tmp_path):
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_x.json", [
        _item(1, 5), _item(2, 3, cat=("设备", "IP层", "规划"), diff="难"),
    ])
    s = compute_stats([p])
    assert s["total"] == 2 and s["answered"] == 2 and s["avg"] == 4.0
    assert s["distribution"] == {1: 0, 2: 0, 3: 1, 4: 0, 5: 1}
    assert s["dims"]["difficulty"]["中"]["count"] == 1
    assert s["dims"]["difficulty"]["中"]["avg"] == 5.0
    assert s["dims"]["scope"]["设备"]["avg"] == 3.0
    assert s["point_rates"]["要点A"] == (2, 2, 1.0)
    assert s["point_rates"]["要点B"] == (0, 2, 0.0)
    assert any(g[0] == "要点B" for g in s["gaps"])


def test_compute_stats_excludes_invalid(tmp_path):
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_x.json", [
        _item(1, 4), _item(2, None), _item(3, 2, mr_status="error"),
    ])
    s = compute_stats([p])
    assert s["total"] == 3 and s["answered"] == 1
    assert s["parse_errors"] == 1 and s["answered_errors"] == 1
    assert s["avg"] == 4.0
    assert [l["id"] for l in s["low_scores"]] == []  # score 2 未计入(answered error)


def test_compute_stats_low_scores(tmp_path):
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_x.json", [
        _item(1, 1), _item(2, 2), _item(3, 4),
    ])
    s = compute_stats([p])
    assert [l["id"] for l in s["low_scores"]] == [1, 2]


def test_render_summary_md_contains_sections():
    stats = {"total": 2, "answered": 2, "answered_errors": 0, "parse_errors": 0,
             "avg": 4.0, "distribution": {1: 0, 2: 0, 3: 0, 4: 1, 5: 1},
             "dims": {"difficulty": {"中": {"count": 2, "avg": 4.0}}},
             "point_rates": {"要点A": (2, 2, 1.0)},
             "gaps": [], "low_scores": []}
    md = render_summary_md(
        {"judge_model": "J", "model": "m", "thinking": "enabled"},
        {"dataset_x": stats}, stats, "结论文字")
    for sec in ("总览", "六维", "评分点命中率", "低分题", "分析结论", "结论文字"):
        assert sec in md
    assert "EVALUATION_J_m_enabled_summary" in md or "4.00" in md


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, messages, temperature=0.0):
        self.calls.append(messages)
        from evaluator.llm_client import ChatResult
        return ChatResult(True, content=self.content)


def test_run_summaries_writes_file(tmp_path):
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_x.json",
                   [_item(1, 4)])
    from evaluator.config import AppConfig, LLMNode
    cfg = AppConfig("evaluate", tmp_path / "benchmark", tmp_path / "report",
                    LLMNode("G", "u", "k", "m"), LLMNode("G", "u", "k", "J"))
    client = FakeClient("这是分析结论。")
    run_summaries(cfg, client, [("enabled", p)])
    out = tmp_path / "report" / "m" / "EVALUATION_J_m_enabled_summary.md"
    assert out.exists()
    assert "这是分析结论。" in out.read_text(encoding="utf-8")


def test_run_summaries_conclusion_failure_fallback(tmp_path):
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_x.json",
                   [_item(1, 4)])
    from evaluator.config import AppConfig, LLMNode
    from evaluator.llm_client import ChatResult
    cfg = AppConfig("evaluate", tmp_path / "benchmark", tmp_path / "report",
                    LLMNode("G", "u", "k", "m"), LLMNode("G", "u", "k", "J"))

    class Boom:
        def chat(self, messages, temperature=0.0):
            return ChatResult(False, error="x")

    run_summaries(cfg, Boom(), [("enabled", p)])
    out = tmp_path / "report" / "m" / "EVALUATION_J_m_enabled_summary.md"
    assert out.exists()
    assert "结论生成失败" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest llm_eval/tests/test_report.py -v`
Expected: FAIL,`No module named 'evaluator.report'`

- [ ] **Step 3: 实现 report**

`llm_eval/evaluator/report.py`:

```python
"""summary.md 生成:程序统计 + 裁判 LLM 结论。"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .config import AppConfig
from .fileio import atomic_write_json
from .runner import sanitize_name

DIMENSIONS = (
    ("难度", lambda it: it.get("difficulty")),
    ("范围", lambda it: (it.get("category") or {}).get("scope")),
    ("协议层", lambda it: (it.get("category") or {}).get("protocol_layer")),
    ("生命周期", lambda it: (it.get("category") or {}).get("lifecycle")),
    ("场景", lambda it: it.get("scenario")),
    ("设备类型", lambda it: it.get("device_type")),
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
    for dim_name, getter in DIMENSIONS:
        groups = defaultdict(list)
        for it, ev in answered:
            key = getter(it)
            if key:
                groups[key].append(ev["score"])
        dims[dim_name] = {k: {"count": len(v),
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
                point_ids[point].append(it.get("id"))
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
        lines.append(f"- {dim_name}:{cells}")
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
            out.append(f"- {point}(命中 {h}/{t},涉及题 id:{ids})")
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
```

- [ ] **Step 4: 回跑 judge 集成测试与全量测试**

Run: `python -m pytest llm_eval/tests/ -v`
Expected: 全部 passed(含 test_judge_run.py 三个集成用例)

- [ ] **Step 5: Commit**

```bash
cd llm_eval && git add . && git commit -m "feat: summary report with dimension stats and judge conclusion"
```

---

### Task 7: main 入口 + config.example + README + 冒烟

**Files:**
- Create: `llm_eval/main.py`
- Create: `llm_eval/config.example.json`
- Create: `llm_eval/README.md`
- Test: `llm_eval/tests/test_main.py`

**Interfaces:**
- Consumes: 全部前序模块
- Produces: CLI 入口 `python llm_eval/main.py [--config llm_eval/config.json]`;退出码 0 成功 / 2 运行错误

- [ ] **Step 1: 写失败测试**

`llm_eval/tests/test_main.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]      # d:\network_knowledge_set
MAIN = Path(__file__).resolve().parents[1] / "main.py"


def _run(args):
    return subprocess.run([sys.executable, str(MAIN), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          cwd=ROOT)


def test_missing_config_fails():
    r = _run(["--config", "llm_eval/tests/_no_such.json"])
    assert r.returncode != 0
    assert "配置" in (r.stderr + r.stdout)


def test_execute_mode_end_to_end_with_stub_server(tmp_path):
    """端到端冒烟:本地起一个 OpenAI 兼容 stub HTTP 服务,跑 execute 再跑 evaluate。"""
    import http.server
    import threading

    calls = {"execute": 0, "judge": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            if self.headers.get("Authorization") == "Bearer sk-judge":
                calls["judge"] += 1
                body = {"choices": [{"message": {"content": json.dumps({
                    "point_results": [{"point": "要点", "hit": True, "comment": "ok"}],
                    "score": 4, "comment": "总评"})}}]}
            else:
                calls["execute"] += 1
                body = {"choices": [{"message": {"content": "模型回答"}}]}
            data = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"

    bench = tmp_path / "benchmark"
    bench.mkdir()
    (bench / "dataset_smoke.json").write_text(json.dumps([{
        "id": 1, "difficulty": "简单",
        "category": {"scope": "网络", "protocol_layer": "IP层", "lifecycle": "维护"},
        "scenario": "通用", "device_type": "不限定",
        "question": "冒烟问题?", "answer": "冒烟参考答案",
        "scoring_points": ["要点"], "tags": []}], ensure_ascii=False),
        encoding="utf-8")

    for mode, key in (("execute", "sk-eval"), ("evaluate", "sk-judge")):
        cfg = {"mode": mode, "benchmark_dir": str(bench),
               "report_dir": str(tmp_path / "report"),
               "evaluatee_llm": {"provider": "GLM", "api_url": url,
                                 "api_key": "sk-eval", "model": "smoke-model",
                                 "timeout": 10, "thinking": {"mode": "enabled"}},
               "judge_llm": {"provider": "GLM", "api_url": url,
                             "api_key": "sk-judge", "model": "judge-model",
                             "timeout": 10, "thinking": {"mode": "disabled"}},
               "concurrency": 2, "max_retries": 0, "temperature": 0.1}
        p = tmp_path / f"config_{mode}.json"
        p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        r = _run(["--config", str(p)])
        assert r.returncode == 0, r.stdout + r.stderr

    assert calls["execute"] == 1 and calls["judge"] == 1
    rp = tmp_path / "report" / "smoke-model"
    record = rp / "RECORD_smoke-model_enabled_dataset_smoke.json"
    evaluation = rp / "EVALUATION_judge-model_smoke-model_enabled_dataset_smoke.json"
    summary = rp / "EVALUATION_judge-model_smoke-model_enabled_summary.md"
    assert record.exists() and evaluation.exists() and summary.exists()
    ev = json.loads(evaluation.read_text(encoding="utf-8"))
    assert ev[0]["evaluation"]["score"] == 4
    srv.shutdown()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest llm_eval/tests/test_main.py -v`
Expected: FAIL(main.py 不存在)

- [ ] **Step 3: 实现 main.py**

`llm_eval/main.py`:

```python
"""LLM 网络知识掌握度评估程序入口。

用法:
    python llm_eval/main.py --config llm_eval/config.json
模式(execute/evaluate)在配置文件中指定。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _main() -> int:
    parser = argparse.ArgumentParser(description="LLM 网络知识掌握度评估")
    parser.add_argument("--config", default=str(Path(__file__).parent / "config.json"))
    args = parser.parse_args()

    from evaluator.config import ConfigError, load_config
    from evaluator.llm_client import LLMClient

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"配置错误:{e}", file=sys.stderr)
        return 2

    if cfg.mode == "execute":
        from evaluator.runner import run_execute
        client = LLMClient(cfg.evaluatee_llm.__dict__, max_retries=cfg.max_retries)
        try:
            run_execute(cfg, client)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"执行失败:{e}", file=sys.stderr)
            return 2
        finally:
            client.close()
    else:
        from evaluator.judge import run_evaluate
        client = LLMClient(cfg.judge_llm.__dict__, max_retries=cfg.max_retries)
        try:
            run_evaluate(cfg, client)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"评估失败:{e}", file=sys.stderr)
            return 2
        finally:
            client.close()
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_main())
```

注意:`LLMNode.__dict__` 作为 node dict 传入时字段名与 LLMClient 期望一致(provider/api_url/api_key/model/timeout/max_tokens),但 thinking 为 `thinking_mode` 字符串——LLMClient 已兼容(读取 `node["thinking_mode"]`),无需转换。

`llm_eval/config.example.json`:

```json
{
  "mode": "execute",
  "benchmark_dir": "../benchmark",
  "report_dir": "../report",
  "evaluatee_llm": {
    "provider": "GLM",
    "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "api_key": "sk-your-evaluatee-key",
    "model": "glm-4.6",
    "timeout": 300,
    "max_tokens": 32768,
    "thinking": {"mode": "enabled"}
  },
  "judge_llm": {
    "provider": "GLM",
    "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "api_key": "sk-your-judge-key",
    "model": "glm-4.6",
    "timeout": 300,
    "max_tokens": 32768,
    "thinking": {"mode": "enabled"}
  },
  "concurrency": 4,
  "max_retries": 2,
  "temperature": 0.1
}
```

`llm_eval/README.md`:

```markdown
# LLM 网络知识掌握度评估程序

## 安装
    pip install -r requirements.txt

## 使用
1. 复制 `config.example.json` 为 `config.json`,填写两个 LLM(被评测/裁判)的
   连接信息与 thinking.mode(enabled/disabled)
2. 执行模式(`"mode": "execute"`):逐题调用被评测 LLM,产出
   `report/<模型>/RECORD_<模型>_<思考模式>_<数据集>.json`(支持并发与断点续跑,
   中断后重跑自动跳过已完成题目)
3. 评估模式(`"mode": "evaluate"`):裁判 LLM 逐评分点打分并给 1-5 总分,产出
   `EVALUATION_<裁判>_<模型>_<思考模式>_<数据集>.json` 与
   `EVALUATION_<裁判>_<模型>_<思考模式>_summary.md`
4. 数据集放在 `benchmark/` 下,文件名以 `dataset` 开头、格式校验通过的才会执行

    python main.py --config config.json

## 测试
    python -m pytest tests/ -v
```

- [ ] **Step 4: 运行全量测试**

Run: `python -m pytest llm_eval/tests/ -v`
Expected: 全部 passed(含端到端冒烟)

- [ ] **Step 5: Commit**

```bash
cd llm_eval && git add . && git commit -m "feat: cli entry, example config, readme and e2e smoke test"
```

---

## Self-Review 结论(已执行)

- **Spec 覆盖**:spec 第 2 节(client 裁剪)→Task 2;第 3-4 节(目录/配置)→Task 1/7;第 5 节(执行模式全部子节)→Task 3/4;第 6 节(评估模式)→Task 5;第 7 节(summary)→Task 6;第 8 节错误表→各任务内分支+main.py 退出码;第 9 节测试→各任务 TDD;第 10 节交付物→Task 7。无遗漏。
- **占位符扫描**:Task 5 Step 3 曾出现两版写出逻辑,已明确「以正确写法为准」并给出完整代码;无 TBD/TODO。
- **类型一致性**:`ChatResult` 字段、`atomic_write_json(path, data)`、`sanitize_name`、`record_path`、`parse_record_filename` 返回三元组、`compute_stats` 键名在各任务间已核对一致;`run_summaries(cfg, client, produced)` 与 Task 5 调用点签名一致。
- **已知注意点**(写给执行者):Task 2 Step 5 的 thinking 提取断言以参考实现真实行为为准修正测试构造,不改实现;Task 5 Step 4 阶段性只跑纯函数测试,Task 6 完成后回跑全量。
