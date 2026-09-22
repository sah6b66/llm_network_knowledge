import json
from pathlib import Path

from evaluator.report import compute_stats, render_summary_md, run_summaries


def _item(i, score, cat=("网络", "IP层", "维护"), diff="中", scen="园区",
           dev="路由器", hit=True, mr_status="ok", tags=None):
    return {
        "id": i, "difficulty": diff,
        "category": {"scope": cat[0], "protocol_layer": cat[1], "lifecycle": cat[2]},
        "scenario": scen, "device_type": dev,
        "question": f"q{i}", "answer": "a",
        "scoring_points": ["要点A", "要点B"],
        "tags": [] if tags is None else tags,
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


def test_compute_stats_dim_value_order(tmp_path):
    items = [
        _item(1, 5, diff="简单", cat=("网络", "其他", "规划"), scen="通用", dev="不限定"),
        _item(2, 4, diff="中", cat=("设备", "物理层", "建设"), scen="Internet", dev="WLAN"),
        _item(3, 3, diff="难", cat=("其他", "链路层", "维护"), scen="园区", dev="防火墙"),
        _item(4, 5, diff="中", cat=("网络", "IP层", "优化"), scen="数据中心", dev="路由器"),
        _item(5, 4, diff="中", cat=("网络", "传输层", "其他"), scen="宽带城域", dev="交换机"),
        _item(6, 5, diff="中", cat=("网络", "IP层", "规划"), scen="未知场景", dev="不限定"),
    ]
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_x.json", items)
    s = compute_stats([p])
    assert list(s["dims"]["difficulty"]) == ["难", "中", "简单"]
    assert list(s["dims"]["scope"]) == ["网络", "设备", "其他"]
    assert list(s["dims"]["protocol_layer"]) == ["传输层", "IP层", "链路层", "物理层", "其他"]
    assert list(s["dims"]["lifecycle"]) == ["规划", "建设", "维护", "优化", "其他"]
    assert list(s["dims"]["scenario"]) == ["园区", "宽带城域", "数据中心", "Internet", "通用", "未知场景"]
    assert list(s["dims"]["device_type"]) == ["交换机", "路由器", "防火墙", "WLAN", "不限定"]


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
    i_conclusion = md.index("## 分析结论")
    i_dataset = md.index("## dataset_x")
    assert i_overview < i_conclusion < i_dataset
    for absent in ("全部数据集合并", "评分点命中率", "知识缺口清单", "低分题清单",
                   "不满足项总体说明"):
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


def test_compute_stats_rfc_year_dimension(tmp_path):
    items = [
        _item(1, 5, diff="简单", tags=["RFC-2021", "RFC9001", "QUIC"]),
        _item(2, 3, diff="简单", tags=["RFC-2021", "RFC9002", "TLS"]),
        _item(3, 5, diff="中", tags=["RFC-2023", "RFC9003", "BGP"]),
    ]
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_rfc.json", items)
    s = compute_stats([p])
    assert list(s["dims"]) == ["year", "difficulty"]  # RFC 数据集:年份 + 难度两维
    assert list(s["dims"]["year"]) == ["2021", "2023"]  # 升序
    assert s["dims"]["year"]["2021"]["count"] == 2
    assert s["dims"]["year"]["2021"]["avg"] == 4.0
    assert s["dims"]["year"]["2021"]["dist"][5] == 1
    assert s["dims"]["difficulty"]["简单"]["count"] == 2
    assert s["dims"]["difficulty"]["简单"]["avg"] == 4.0
    assert s["dims"]["difficulty"]["中"]["count"] == 1
    assert s["dims"]["difficulty"]["中"]["avg"] == 5.0


def test_compute_stats_rfc_year_order_covers_2021_2025(tmp_path):
    items = [
        _item(1, 5, tags=["RFC-2025", "RFC9800"]),
        _item(2, 4, tags=["RFC-2022", "RFC9114"]),
        _item(3, 4, tags=["RFC-2019", "RFC8555"]),
    ]
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_rfc_x.json", items)
    s = compute_stats([p])
    assert list(s["dims"]["year"]) == ["2022", "2025", "2019"]  # 预定义序在前,表外年份排末尾


def test_compute_stats_partial_rfc_tags_keep_six_dims(tmp_path):
    items = [
        _item(1, 5, tags=["RFC-2021", "RFC9001"]),
        _item(2, 4),  # 无 RFC 年份标签 → 非纯 RFC 数据集,维持六维
    ]
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_x.json", items)
    s = compute_stats([p])
    assert list(s["dims"]) == ["difficulty", "scope", "protocol_layer",
                               "lifecycle", "scenario", "device_type"]


def test_compute_stats_hw_device_dims(tmp_path):
    items = [
        _item(1, 5, tags=["CE6800", "V200R025C00", "特性", "M-LAG"]),
        _item(2, 3, tags=["CE6800", "V200R025C00", "命令行", "VLAN"]),
        _item(3, 4, tags=["NetEngine8000", "V800R025C10", "命令行", "BGP"]),
        _item(4, 5, tags=["USG6305E", "V600R007C20", "日志", "NAT"]),
    ]
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_huawei_device.json",
                   items)
    s = compute_stats([p])
    assert list(s["dims"]) == ["hw_family", "hw_qtype"]  # 华为数据集:设备类别 + 问题类型
    assert list(s["dims"]["hw_family"]) == ["CE交换机", "路由器", "防火墙"]  # 预定义序
    assert s["dims"]["hw_family"]["CE交换机"]["count"] == 2
    assert s["dims"]["hw_family"]["CE交换机"]["avg"] == 4.0
    assert list(s["dims"]["hw_qtype"]) == ["特性", "命令行", "日志"]
    assert s["dims"]["hw_qtype"]["命令行"]["count"] == 2
    assert s["dims"]["hw_qtype"]["命令行"]["avg"] == 3.5


def test_compute_stats_hw_family_order_covers_all(tmp_path):
    items = [
        _item(1, 5, tags=["AR6120", "V600R025C10", "配置方案", "NAT"]),
        _item(2, 4, tags=["S5735", "V600R025C00", "场景", "VXLAN"]),
        _item(3, 4, tags=["AirEngine5700", "V600R025C10", "告警处理", "PoE"]),
    ]
    p = _eval_file(tmp_path, "EVALUATION_J_m_enabled_dataset_huawei_device.json",
                   items)
    s = compute_stats([p])
    assert list(s["dims"]["hw_family"]) == ["S交换机", "AR路由", "WLAN"]


def _rfc_stats_fixture():
    return {"total": 2, "answered": 2, "answered_errors": 0, "parse_errors": 0,
            "passed": 1, "failed_count": 1, "avg": 4.0,
            "distribution": {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1},
            "dims": {"year": {"2021": {"count": 2, "avg": 4.0,
                                       "dist": {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1}},
                              "2022": {"count": 1, "avg": 5.0,
                                       "dist": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 1}}},
                     "difficulty": {"简单": {"count": 2, "avg": 4.0,
                                             "dist": {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1}},
                                    "中": {"count": 1, "avg": 5.0,
                                          "dist": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 1}}}},
            "gaps": [],
            "failed_cases": [{"id": 2, "question": "q2", "score": 4,
                              "difficulty": "简单", "protocol_layer": "IP层",
                              "missed": [{"point": "要点B", "comment": "B的评语"}]}]}


def test_render_rfc_year_dim_table():
    md = render_summary_md(
        {"judge_model": "J", "model": "m", "thinking": "enabled"},
        {"dataset_rfc": _rfc_stats_fixture()}, "结论文字")
    assert "| 年份-2021 | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 4.00 |" in md
    assert "| 年份-2022 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 5.00 |" in md
    assert "| 难度-简单 | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 4.00 |" in md
    assert "| 难度-中 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 5.00 |" in md
    assert "| 场景-" not in md and "| 协议层-" not in md  # 其余四维仍不输出
    assert "## dataset_rfc" in md


def test_render_rfc_and_normal_datasets_coexist():
    md = render_summary_md(
        {"judge_model": "J", "model": "m", "thinking": "enabled"},
        {"dataset_basic": _stats_fixture(),
         "dataset_rfc_basic": _rfc_stats_fixture()}, "结论文字")
    assert "## dataset_basic" in md and "## dataset_rfc_basic" in md
    assert "| 难度-中 |" in md  # 普通数据集六维保留
    assert md.index("## dataset_basic") < md.index("## dataset_rfc_basic")


def _hw_stats_fixture():
    return {"total": 2, "answered": 2, "answered_errors": 0, "parse_errors": 0,
            "passed": 1, "failed_count": 1, "avg": 4.0,
            "distribution": {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1},
            "dims": {"hw_family": {"CE交换机": {"count": 2, "avg": 4.0,
                                                "dist": {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1}},
                                   "WLAN": {"count": 1, "avg": 5.0,
                                            "dist": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 1}}},
                     "hw_qtype": {"命令行": {"count": 2, "avg": 4.0,
                                           "dist": {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1}},
                                  "日志": {"count": 1, "avg": 5.0,
                                          "dist": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 1}}}},
            "gaps": [],
            "failed_cases": [{"id": 2, "question": "q2", "score": 4,
                              "difficulty": "中", "protocol_layer": "其他",
                              "missed": [{"point": "要点B", "comment": "B的评语"}]}]}


def test_render_hw_dim_table():
    md = render_summary_md(
        {"judge_model": "J", "model": "m", "thinking": "enabled"},
        {"dataset_huawei_device": _hw_stats_fixture()}, "结论文字")
    assert "| 设备类别-CE交换机 | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 4.00 |" in md
    assert "| 设备类别-WLAN | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 5.00 |" in md
    assert "| 问题类型-命令行 | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 4.00 |" in md
    assert "| 问题类型-日志 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 5.00 |" in md
    assert "| 难度-" not in md  # 华为数据集不输出六维行
    assert "## dataset_huawei_device" in md


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
