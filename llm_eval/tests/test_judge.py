import json

from evaluator.judge import (
    build_judge_prompt, parse_judge_json, parse_record_filename)

CASE = {"id": 7, "question": "问?", "answer": "参考答案",
        "scoring_points": ["要点A", "要点B"],
        "model_response": {"answer": "模型回答", "status": "ok"}}


def test_parse_record_filename():
    assert parse_record_filename("RECORD_glm-4.6_enabled_dataset_detail.json") == \
        ("glm-4.6", "enabled", "dataset_detail")
    assert parse_record_filename("RECORD_my_model_disabled_dataset_basic.json") == \
        ("my_model", "disabled", "dataset_basic")
    assert parse_record_filename("RECORD_m_enabled_dataset.json") == \
        ("m", "enabled", "dataset")
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
