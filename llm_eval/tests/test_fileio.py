import json
from pathlib import Path

from evaluator.fileio import atomic_write_json


def test_atomic_write_json_roundtrip(tmp_path: Path):
    target = tmp_path / "out.json"
    atomic_write_json(target, [{"id": 1, "text": "中文「引号」"}])
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # 无 BOM
    assert json.loads(raw.decode("utf-8")) == [{"id": 1, "text": "中文「引号」"}]


def test_atomic_write_json_no_tmp_left(tmp_path: Path):
    atomic_write_json(tmp_path / "out.json", {"a": 1})
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_atomic_write_json_overwrite(tmp_path: Path):
    target = tmp_path / "out.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 2}
