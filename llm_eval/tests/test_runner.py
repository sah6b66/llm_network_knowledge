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
    # 含 "/" 的模型名只取最后一段(如 org/model → model),其余非法字符替换为 "-"
    assert sanitize_name("deepseek-ai/DeepSeek-V4-Flash") == "DeepSeek-V4-Flash"
    assert sanitize_name('a/b\\c:d*e?f"g<h>i|j') == "b-c-d-e-f-g-h-i-j"


def test_record_path_slash_model_name():
    p = record_path(_cfg(__import__("pathlib").Path(".")).report_dir,
                    "deepseek-ai/DeepSeek-V4-Flash", "disabled", "dataset_x")
    assert p.parent.name == "DeepSeek-V4-Flash"
    assert p.name == "RECORD_DeepSeek-V4-Flash_disabled_dataset_x.json"


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
