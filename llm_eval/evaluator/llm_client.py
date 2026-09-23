"""LLM 客户端 — 裁剪自 nl2cli_light providers.py。

保留:多 provider 思考注入、重试指数退避、连接池、ssl_verify、${ENV} key 解析。
裁剪:backup_llm/auto_switch 故障转移、adaptive 思考模式、thinking budget。
chat() 失败不抛异常,以 ChatResult(success=False) 返回。
"""
from __future__ import annotations

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
    修改点:ssl_verify 缺省改为 False(与配置文件缺省一致),其余保留原样。"""

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

        self._ssl_verify = config.get("ssl_verify", False)
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
