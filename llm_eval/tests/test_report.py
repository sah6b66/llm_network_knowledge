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
