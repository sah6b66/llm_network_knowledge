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
                {"point": "要点B", "hit": False, "comment": "B的评语"}]}),
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
    assert s["distribution"] == {0: 0, 1: 0, 2: 0, 3: 1, 4: 0, 5: 1}
    assert s["passed"] == 1 and s["failed_count"] == 1
    assert s["dims"]["difficulty"]["中"]["count"] == 1
    assert s["dims"]["difficulty"]["中"]["avg"] == 5.0
    assert s["dims"]["difficulty"]["中"]["dist"] == {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 1}
    assert s["dims"]["scope"]["设备"]["avg"] == 3.0
    assert any(g[0] == "要点B" for g in s["gaps"])
    assert "point_rates" not in s and "low_scores" not in s


def test_compute_stats_excludes_invalid(tmp_path):
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_x.json", [
        _item(1, 4), _item(2, None), _item(3, 2, mr_status="error"),
    ])
    s = compute_stats([p])
    assert s["total"] == 3 and s["answered"] == 1
    assert s["parse_errors"] == 1 and s["answered_errors"] == 1
    assert s["avg"] == 4.0
    assert s["passed"] == 0 and s["failed_count"] == 1
    assert [c["id"] for c in s["failed_cases"]] == [1]  # 仅 id=1(score 4)计入,id=2 无评分、id=3 作答失败


def test_compute_stats_failed_cases_sorted(tmp_path):
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_x.json", [
        _item(1, 2), _item(7, 3), _item(2, 3), _item(3, 5), _item(4, 4),
    ])
    s = compute_stats([p])
    assert [c["id"] for c in s["failed_cases"]] == [1, 2, 7, 4]  # 得分升序,同分按 id
    c = s["failed_cases"][0]
    assert c["question"] == "q1" and c["score"] == 2
    assert c["difficulty"] == "中" and c["protocol_layer"] == "IP层"
    assert c["missed"] == [{"point": "要点B", "comment": "B的评语"}]


def _stats_fixture():
    return {"total": 2, "answered": 2, "answered_errors": 0, "parse_errors": 0,
            "passed": 1, "failed_count": 1, "avg": 4.0,
            "distribution": {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1},
            "dims": {"difficulty": {"中": {"count": 2, "avg": 4.5,
                                          "dist": {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1}}}},
            "gaps": [("要点B", 0, 2, [{"id": 2, "difficulty": "中",
                                       "protocol_layer": "IP层"}])],
            "failed_cases": [{"id": 2, "question": "q2", "score": 4,
                              "difficulty": "中", "protocol_layer": "IP层",
                              "missed": [{"point": "要点B", "comment": "B的评语"}]}]}


def test_render_summary_md_section_order():
    md = render_summary_md(
        {"judge_model": "J", "model": "m", "thinking": "enabled"},
        {"dataset_x": _stats_fixture()}, "结论文字")
    i_overview = md.index("## 总体评价")
    i_gaps = md.index("### 不满足项总体说明")
    i_conclusion = md.index("## 分析结论")
    i_dataset = md.index("## dataset_x")
    assert i_overview < i_gaps < i_conclusion < i_dataset
    for absent in ("全部数据集合并", "评分点命中率", "知识缺口清单", "低分题清单"):
        assert absent not in md


def test_render_summary_md_overview_no_merging():
    a = _stats_fixture()
    b = _stats_fixture()
    md = render_summary_md(
        {"judge_model": "J", "model": "m", "thinking": "enabled"},
        {"dataset_a": a, "dataset_b": b}, "结论文字")
    assert "- dataset_a:总数 2,完全通过(5分) 1,不通过(≠5分) 1,综合评分 4.00" in md
    assert "- dataset_b:总数 2,完全通过(5分) 1,不通过(≠5分) 1,综合评分 4.00" in md
    assert "总数 4" not in md  # 不得出现跨数据集合并数字


def test_render_summary_md_overview_gap_lines():
    md = render_summary_md(
        {"judge_model": "J", "model": "m", "thinking": "enabled"},
        {"dataset_x": _stats_fixture()}, "结论文字")
    assert "- dataset_x(命中率<50% 评分点 1 个):" in md
    assert "要点B(命中 0/2" in md


def test_render_dim_table():
    md = render_summary_md(
        {"judge_model": "J", "model": "m", "thinking": "enabled"},
        {"dataset_x": _stats_fixture()}, "结论文字")
    header = "| 维度 | 总数 | 5分 | 4分 | 3分 | 2分 | 1分 | 0分 | 评分 |"
    assert header in md
    assert "| 难度-中 | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 4.50 |" in md


def test_render_failed_detail():
    md = render_summary_md(
        {"judge_model": "J", "model": "m", "thinking": "enabled"},
        {"dataset_x": _stats_fixture()}, "结论文字")
    assert "### 不通过详情(按得分升序)" in md
    assert "#### id=2 得分 4(中/IP层)" in md
    assert "**问题**:q2" in md
    assert "- 要点B — B的评语" in md


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
    text = out.read_text(encoding="utf-8")
    assert "这是分析结论。" in text
    assert "## 分析结论" in text
    prompt = client.calls[0][0]["content"]
    assert "dataset_x" in prompt  # 结论输入为各数据集统计


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
