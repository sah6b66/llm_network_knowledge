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
    client2 = FakeClient([_judge_payload(5), ChatResult(True, content="结论文字")])
    run_evaluate(cfg, client2)
    assert len(client2.calls) == 2  # 1 次评分 + 1 次 summary 结论调用
    final = json.loads(out.read_text(encoding="utf-8"))
    assert final[0]["evaluation"]["score"] == 3      # 已评分的保留
    assert final[1]["evaluation"]["score"] == 5      # 未评分的新评


def test_run_evaluate_parse_fail_marks_null(tmp_path):
    cfg = _cfg(tmp_path)
    _record(tmp_path, answered=1)
    client = FakeClient([ChatResult(True, content="垃圾输出"),
                         ChatResult(True, content="还是垃圾"),
                         ChatResult(True, content="结论文字")])
    run_evaluate(cfg, client)
    out = tmp_path / "report" / "eval-model" / \
        "EVALUATION_judge-model_eval-model_enabled_dataset_unit.json"
    items = json.loads(out.read_text(encoding="utf-8"))
    ev = items[0]["evaluation"]
    assert ev["score"] is None and "parse_error" in ev
    assert len(client.calls) == 3  # 2 次评分尝试 + 1 次 summary 结论调用


def test_run_evaluate_rerun_preserves_evaluations(tmp_path):
    cfg = _cfg(tmp_path)
    _record(tmp_path)
    out = tmp_path / "report" / "eval-model" / \
        "EVALUATION_judge-model_eval-model_enabled_dataset_unit.json"
    client1 = FakeClient([_judge_payload(4), _judge_payload(5),
                          ChatResult(True, content="结论")])
    run_evaluate(cfg, client1)
    # 再次运行确认已完成:不应有任何评分调用,且评分结果保持不变
    client2 = FakeClient([ChatResult(True, content="结论")])
    run_evaluate(cfg, client2)
    assert len(client2.calls) == 1  # 仅 summary 结论调用
    items = json.loads(out.read_text(encoding="utf-8"))
    assert [it["evaluation"]["score"] for it in items] == [4, 5]
    assert all("evaluation" in it for it in items)


def test_run_evaluate_skips_error_status_items(tmp_path):
    cfg = _cfg(tmp_path)
    p = _record(tmp_path, answered=1)
    items = json.loads(p.read_text(encoding="utf-8"))
    items[0]["model_response"]["status"] = "error"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    client = FakeClient([ChatResult(True, content="结论")])
    run_evaluate(cfg, client)
    assert len(client.calls) == 1  # 仅 summary 结论调用,零次评分
    out = tmp_path / "report" / "eval-model" / \
        "EVALUATION_judge-model_eval-model_enabled_dataset_unit.json"
    final = json.loads(out.read_text(encoding="utf-8"))
    ev = final[0]["evaluation"]
    assert ev["score"] is None
    assert "作答失败" in ev["comment"]


def test_run_evaluate_tolerates_null_placeholders(tmp_path, capsys):
    """执行模式中断会在 RECORD 留下裸 null 占位,evaluate 不应崩溃。"""
    cfg = _cfg(tmp_path)
    p = _record(tmp_path)  # 2 条已完成
    items = json.loads(p.read_text(encoding="utf-8"))
    items.append(None)  # 模拟执行中断留下的占位
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    client = FakeClient([_judge_payload(4), _judge_payload(5),
                         ChatResult(True, content="结论文字")])
    run_evaluate(cfg, client)
    out = tmp_path / "report" / "eval-model" / \
        "EVALUATION_judge-model_eval-model_enabled_dataset_unit.json"
    final = json.loads(out.read_text(encoding="utf-8"))
    assert len(final) == 2  # null 占位不进入 EVALUATION
    assert [it["evaluation"]["score"] for it in final] == [4, 5]
    assert len(client.calls) == 3  # 2 次评分 + 1 次 summary 结论调用
    assert "空占位" in capsys.readouterr().out
