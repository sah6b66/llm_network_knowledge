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
