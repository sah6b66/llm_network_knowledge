import json
import os
from pathlib import Path

import pytest

import evaluator.fileio as fileio
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


def test_atomic_write_json_retries_transient_replace_error(
        tmp_path: Path, monkeypatch):
    calls = {"n": 0}
    real_replace = os.replace

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(5, "拒绝访问")
        real_replace(src, dst)

    monkeypatch.setattr(fileio.os, "replace", flaky_replace)
    target = tmp_path / "out.json"
    atomic_write_json(target, {"v": 1})
    assert calls["n"] == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 1}


def test_atomic_write_json_replace_error_cleans_tmp(
        tmp_path: Path, monkeypatch):
    def always_fail(src, dst):
        raise PermissionError(5, "拒绝访问")

    monkeypatch.setattr(fileio.os, "replace", always_fail)
    monkeypatch.setattr(fileio.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        atomic_write_json(tmp_path / "out.json", {"v": 1})
    assert list(tmp_path.iterdir()) == []
