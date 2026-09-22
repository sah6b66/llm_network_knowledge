# -*- coding: utf-8 -*-
"""validate.py rfc_* / hw_* 模式的单元测试。"""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "validate", Path(__file__).parent / "validate.py")
assert _spec and _spec.loader
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)

RFC_YEARS = ["2021", "2022", "2023", "2024", "2025"]


def topic(i, year=None, rfc=None, protocol_layer="IP层", scenario="其他",
          device_type="其他", scope="其他", lifecycle="其他", tags=None,
          text="某 RFC 主题"):
    year = 2021 + (i - 1) // 10 if year is None else year
    rfc = 9000 + i if rfc is None else rfc
    tags = [f"RFC-{year}", f"RFC{rfc}", "关键词A", "关键词B"] if tags is None else tags
    return {"id": i, "rfc": rfc,
            "category": {"scope": scope, "protocol_layer": protocol_layer,
                         "lifecycle": lifecycle},
            "scenario": scenario, "device_type": device_type,
            "topic": text, "tags": tags}


def case(i, difficulty="简单", year=None, rfc=None, protocol_layer="IP层",
         tags=None, question=None, answer=None, scoring_points=None):
    year = 2021 + (i - 1) // 10 if year is None else year
    rfc = 9000 + i if rfc is None else rfc
    tags = [f"RFC-{year}", f"RFC{rfc}", "关键词A", "关键词B"] if tags is None else tags
    return {"id": i, "difficulty": difficulty,
            "category": {"scope": "其他", "protocol_layer": protocol_layer,
                         "lifecycle": "其他"},
            "scenario": "其他", "device_type": "其他",
            "question": question or f"问题{i}", "answer": answer or f"答案{i}",
            "scoring_points": scoring_points or ["要点1", "要点2", "要点3"],
            "tags": tags}


def topics_50():
    return [topic(i) for i in range(1, 51)]


def cases_50(difficulty="简单"):
    return [case(i, difficulty=difficulty) for i in range(1, 51)]


# ---------- rfc_topics ----------

def test_rfc_topics_valid():
    errors = []
    validate.check_rfc_topics(topics_50(), errors)
    assert errors == []


def test_rfc_topics_count_must_be_50():
    errors = []
    validate.check_rfc_topics(topics_50()[:49], errors)
    assert any("50" in e for e in errors)


def test_rfc_topics_ids_must_be_1_to_50():
    items = topics_50()
    items[9]["id"] = 51
    errors = []
    validate.check_rfc_topics(items, errors)
    assert any("1-50" in e for e in errors)


def test_rfc_topics_ten_per_year():
    items = topics_50()
    items[10] = topic(11, year=2021)  # 2022 少一篇、2021 多一篇
    errors = []
    validate.check_rfc_topics(items, errors)
    assert any("每年" in e for e in errors)


def test_rfc_topics_unique_rfc_numbers():
    items = topics_50()
    items[1]["rfc"] = items[0]["rfc"]
    items[1]["tags"] = [t for t in items[1]["tags"] if not t.startswith("RFC9")]
    items[1]["tags"][1:1] = [f"RFC{items[0]['rfc']}"]
    errors = []
    validate.check_rfc_topics(items, errors)
    assert any("重复" in e for e in errors)


def test_rfc_topics_require_year_and_number_tags():
    errors = []
    validate.check_rfc_topics(
        [topic(1, tags=["关键词A"])], errors)
    assert any("RFC-年份" in e for e in errors)
    assert any("RFC 编号" in e for e in errors)


def test_rfc_topics_tag_must_match_rfc_field():
    errors = []
    validate.check_rfc_topics([topic(1, tags=["RFC-2021", "RFC9999", "A", "B"])], errors)
    assert any("不一致" in e for e in errors)


def test_rfc_topics_fixed_dims():
    items = topics_50()
    items[0].update(scenario="园区", device_type="路由器")
    items[0]["category"].update(scope="网络", lifecycle="规划")
    errors = []
    validate.check_rfc_topics(items, errors)
    assert sum("scenario" in e for e in errors) >= 1
    assert sum("device_type" in e for e in errors) >= 1
    assert sum("scope" in e for e in errors) >= 1
    assert sum("lifecycle" in e for e in errors) >= 1


def test_rfc_topics_protocol_layer_enum():
    errors = []
    validate.check_rfc_topics([topic(1, protocol_layer="应用层")], errors)
    assert any("protocol_layer" in e for e in errors)


def test_rfc_topics_topic_text_required():
    errors = []
    validate.check_rfc_topics([topic(1, text=" ")], errors)
    assert any("topic" in e for e in errors)


def test_rfc_topics_rfc_field_required():
    errors = []
    t = topic(1)
    del t["rfc"]
    validate.check_rfc_topics([t], errors)
    assert any("rfc" in e for e in errors)


# ---------- rfc_cases(年度批次) ----------

def test_rfc_cases_valid_batch():
    errors = []
    validate.check_rfc_cases(
        [case(i, year=2021) for i in range(1, 11)], errors)
    assert errors == []


def test_rfc_cases_uniform_difficulty():
    items = [case(i, year=2021) for i in range(1, 11)]
    items[3]["difficulty"] = "中"
    errors = []
    validate.check_rfc_cases(items, errors)
    assert any("难度" in e for e in errors)


def test_rfc_cases_difficulty_only_simple_or_medium():
    errors = []
    validate.check_rfc_cases(
        [case(1, year=2021, difficulty="难")], errors)
    assert any("难度" in e for e in errors)


def test_rfc_cases_single_year_per_file():
    items = [case(i, year=2021) for i in range(1, 11)]
    items[9]["tags"] = ["RFC-2022", "RFC9009", "A", "B"]
    errors = []
    validate.check_rfc_cases(items, errors)
    assert any("同一年份" in e for e in errors)


def test_rfc_cases_content_checks():
    errors = []
    validate.check_rfc_cases(
        [case(1, year=2021, question=" ", scoring_points=["只有两条", "不合规"])],
        errors)
    assert any("question" in e for e in errors)
    assert any("scoring_points" in e for e in errors)


def test_rfc_cases_id_within_1_50():
    errors = []
    validate.check_rfc_cases([case(51, year=2021)], errors)
    assert any("1-50" in e for e in errors)


# ---------- rfc_full(合并数据集: 简单 1-50 + 中 51-100) ----------

def cases_100_merged():
    out = []
    for i in range(1, 51):
        out.append(case(i, difficulty="简单"))
        d = case(i, difficulty="中")
        d["id"] = i + 50
        out.append(d)
    return out


def test_rfc_full_valid():
    errors = []
    validate.check_rfc_full(cases_100_merged(), errors)
    assert errors == []


def test_rfc_full_count_and_ids():
    errors = []
    validate.check_rfc_full(cases_100_merged()[:80], errors)
    assert any("100" in e for e in errors)
    items = cases_100_merged()
    items[99]["id"] = 999
    errors = []
    validate.check_rfc_full(items, errors)
    assert any("1-100" in e for e in errors)


def test_rfc_full_year_and_number_pairing():
    items = cases_100_merged()
    items[1]["tags"] = ["RFC-2022", "RFC9001", "A", "B"]  # 2021 少 1 篇、2022 多 1 篇
    errors = []
    validate.check_rfc_full(items, errors)
    assert any("每年" in e for e in errors)
    items = cases_100_merged()
    items[1]["tags"] = ["RFC-2021", "RFC9501", "A", "B"]  # RFC9001 仅 1 次
    errors = []
    validate.check_rfc_full(items, errors)
    assert any("编号" in e for e in errors)
    items = cases_100_merged()
    items[1]["difficulty"] = "简单"  # RFC9001 两条均为简单,破坏 简单+中 配对
    errors = []
    validate.check_rfc_full(items, errors)
    assert any("编号" in e for e in errors)


# ---------- CLI 接线 ----------

def _run_main(tmp_path, items, mode, monkeypatch, capsys):
    f = tmp_path / "x.json"
    import json
    f.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["validate.py", str(f), "--mode", mode])
    validate.main()
    return capsys.readouterr().out


def test_main_rfc_topics_pass(tmp_path, monkeypatch, capsys):
    out = _run_main(tmp_path, topics_50(), "rfc_topics", monkeypatch, capsys)
    assert "PASS" in out


def test_main_rfc_topics_fail_exit_code(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as ei:
        _run_main(tmp_path, topics_50()[:3], "rfc_topics", monkeypatch, capsys)
    assert ei.value.code == 1


def test_main_rfc_full_pass(tmp_path, monkeypatch, capsys):
    out = _run_main(tmp_path, cases_100_merged(), "rfc_full", monkeypatch, capsys)
    assert "PASS" in out


# ---------- hw_* 模式 fixture ----------

HW_META = {"CE交换机": ("交换机", "数据中心"), "S交换机": ("交换机", "园区"),
           "路由器NE": ("路由器", "通用"), "AR路由": ("路由器", "通用"),
           "防火墙": ("防火墙", "通用"), "WLAN": ("WLAN", "园区")}

HW_PLAN = [
    ("CE交换机", "CE6800", "V200R025C00",
     {"特性": 2, "场景": 1, "配置方案": 4, "命令行": 9, "告警处理": 4, "日志": 5}),
    ("S交换机", "S5735", "V600R025C00",
     {"特性": 1, "场景": 0, "配置方案": 1, "命令行": 3, "告警处理": 3, "日志": 2}),
    ("路由器NE", "NetEngine8000", "V800R025C10",
     {"特性": 2, "场景": 0, "配置方案": 3, "命令行": 7, "告警处理": 4, "日志": 4}),
    ("AR路由", "AR6120", "V600R025C10",
     {"特性": 1, "场景": 0, "配置方案": 3, "命令行": 5, "告警处理": 3, "日志": 3}),
    ("防火墙", "USG6305E", "V600R007C20",
     {"特性": 2, "场景": 0, "配置方案": 2, "命令行": 5, "告警处理": 3, "日志": 3}),
    ("WLAN", "AirEngine5760", "V600R025C10",
     {"特性": 1, "场景": 0, "配置方案": 2, "命令行": 6, "告警处理": 3, "日志": 3}),
]


def _hw_plan_entries():
    out = []
    i = 1
    for product, model, ver, cats in HW_PLAN:
        for cat, n in cats.items():
            for _ in range(n):
                out.append((i, product, model, ver, cat))
                i += 1
    return out


def hw_item(i, product, model, ver, cat, with_content=True):
    dtype, scen = HW_META[product]
    it = {"id": i,
          "difficulty": "简单" if cat in ("场景", "特性") else "中",
          "category": {"scope": "设备", "protocol_layer": "其他", "lifecycle": "其他"},
          "scenario": scen, "device_type": dtype,
          "tags": [model, ver, cat, "关键词"]}
    if with_content:
        it["topic"] = f"主题{i}"
        it["question"] = f"在{model}({ver})上,{cat}类问题{i}"
        it["answer"] = f"答案{i}"
        it["scoring_points"] = ["要点1", "要点2", "要点3"]
    else:
        it["topic"] = f"主题{i}"
    return it


def hw_topics_100():
    return [hw_item(*e, with_content=False) for e in _hw_plan_entries()]


def hw_cases_100():
    return [hw_item(*e) for e in _hw_plan_entries()]


# ---------- hw_topics ----------

def test_hw_topics_valid():
    errors = []
    validate.check_hw_topics(hw_topics_100(), errors)
    assert errors == []


def test_hw_topics_count_and_ids():
    errors = []
    validate.check_hw_topics(hw_topics_100()[:99], errors)
    assert any("100" in e for e in errors)
    items = hw_topics_100()
    items[99]["id"] = 101
    errors = []
    validate.check_hw_topics(items, errors)
    assert any("1-100" in e for e in errors)


def test_hw_topics_quota():
    items = hw_topics_100()
    items[2]["tags"][2] = "日志"  # CE 场景 1→0,日志 5→6
    errors = []
    validate.check_hw_topics(items, errors)
    assert any("配额" in e for e in errors)


def test_hw_topics_id_block_mismatch():
    items = hw_topics_100()
    items[0]["tags"][0] = "AirEngine9700"  # id=1 应属 CE 块
    items[0]["tags"][2] = "特性"
    items[0]["scenario"] = "园区"
    items[0]["device_type"] = "WLAN"
    errors = []
    validate.check_hw_topics(items, errors)
    assert any("id 块" in e for e in errors)


def test_hw_topics_difficulty_rule():
    items = hw_topics_100()
    items[0]["difficulty"] = "中"  # 特性 → 应为 简单
    errors = []
    validate.check_hw_topics(items, errors)
    assert any("难度" in e for e in errors)


def test_hw_topics_fixed_dims():
    items = hw_topics_100()
    items[0]["category"]["scope"] = "网络"
    items[0]["category"]["protocol_layer"] = "IP层"
    items[0]["category"]["lifecycle"] = "维护"
    items[0]["scenario"] = "园区"
    items[0]["device_type"] = "路由器"
    errors = []
    validate.check_hw_topics(items, errors)
    for key in ("scope", "protocol_layer", "lifecycle", "scenario", "device_type"):
        assert any(key in e for e in errors)


def test_hw_topics_unrecognized_model():
    items = hw_topics_100()
    items[0]["tags"][0] = "Unknown9000"
    errors = []
    validate.check_hw_topics(items, errors)
    assert any("产品族" in e for e in errors)


def test_hw_topics_bad_version_tag():
    items = hw_topics_100()
    items[0]["tags"][1] = "200R025C00"
    errors = []
    validate.check_hw_topics(items, errors)
    assert any("版本" in e for e in errors)


# ---------- hw_cases(单产品批次) ----------

def test_hw_cases_valid_batch():
    errors = []
    validate.check_hw_cases(hw_cases_100()[85:], errors)  # WLAN 块
    assert errors == []


def test_hw_cases_mixed_product():
    items = hw_cases_100()[85:]
    items[0]["question"] = "在CE6800(V200R025C00)上,命令行类问题"
    items[0]["tags"] = ["CE6800", "V200R025C00", "命令行", "关键词"]
    items[0]["category"]["scope"] = "设备"
    items[0]["difficulty"] = "中"
    items[0]["scenario"] = "数据中心"
    items[0]["device_type"] = "交换机"
    errors = []
    validate.check_hw_cases(items, errors)
    assert any("同一产品" in e for e in errors)


def test_hw_cases_question_must_name_model_and_version():
    items = hw_cases_100()[85:]
    items[0]["question"] = "通用问题,不含型号与版本"
    errors = []
    validate.check_hw_cases(items, errors)
    assert any("型号" in e for e in errors)
    assert any("版本" in e for e in errors)


# ---------- hw_full(合并数据集) ----------

def test_hw_full_valid():
    errors = []
    validate.check_hw_full(hw_cases_100(), errors)
    assert errors == []


def test_hw_full_count_ids_quota():
    errors = []
    validate.check_hw_full(hw_cases_100()[:99], errors)
    assert any("100" in e for e in errors)
    items = hw_cases_100()
    items[7]["tags"][2] = "日志"  # CE 命令行 9→8,日志 5→6
    errors = []
    validate.check_hw_full(items, errors)
    assert any("配额" in e for e in errors)


def test_hw_full_duplicate_questions():
    items = hw_cases_100()
    items[7]["question"] = items[8]["question"]
    errors = []
    validate.check_hw_full(items, errors)
    assert any("重复" in e for e in errors)


# ---------- CLI 接线(hw) ----------

def test_main_hw_topics_pass(tmp_path, monkeypatch, capsys):
    out = _run_main(tmp_path, hw_topics_100(), "hw_topics", monkeypatch, capsys)
    assert "PASS" in out


def test_main_hw_full_fail_exit_code(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as ei:
        _run_main(tmp_path, hw_cases_100()[:50], "hw_full", monkeypatch, capsys)
    assert ei.value.code == 1
