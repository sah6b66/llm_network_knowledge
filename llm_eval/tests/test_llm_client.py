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


def test_ssl_verify_defaults_false():
    c = LLMClient(dict(NODE))
    assert c._provider._ssl_verify is False
    assert c._provider._session.verify is False


def test_ssl_verify_true_enables_certificate_check():
    c = LLMClient(dict(NODE, ssl_verify=True))
    assert c._provider._ssl_verify is True
    assert c._provider._session.verify is True
