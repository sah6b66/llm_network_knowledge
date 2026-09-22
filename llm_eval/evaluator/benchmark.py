"""benchmark 数据集发现与格式校验。"""
from __future__ import annotations

import json
from pathlib import Path

_STR_FIELDS = ("difficulty", "scenario", "device_type", "answer")
_CATEGORY_KEYS = ("scope", "protocol_layer", "lifecycle")


def discover_datasets(benchmark_dir: Path) -> list[Path]:
    if not benchmark_dir.is_dir():
        raise FileNotFoundError(f"benchmark 目录不存在:{benchmark_dir}")
    return sorted(p for p in benchmark_dir.glob("dataset*.json") if p.suffix == ".json")


def _check_str_fields(item: dict, idx: int, errors: list[str]) -> None:
    for f in _STR_FIELDS:
        if not isinstance(item.get(f), str):
            errors.append(f"第 {idx} 条字段 {f} 缺失或不是字符串")
    q = item.get("question")
    if not (isinstance(q, str) and q.strip()):
        errors.append(f"第 {idx} 条字段 question 缺失或为空")
    sp = item.get("scoring_points")
    if not (isinstance(sp, list) and sp
            and all(isinstance(x, str) for x in sp)):
        errors.append(f"第 {idx} 条字段 scoring_points 必须为非空字符串数组")
    tags = item.get("tags")
    if not (isinstance(tags, list) and all(isinstance(x, str) for x in tags)):
        errors.append(f"第 {idx} 条字段 tags 必须为字符串数组")
    cat = item.get("category")
    if not isinstance(cat, dict):
        errors.append(f"第 {idx} 条字段 category 缺失或不是对象")
    else:
        for k in _CATEGORY_KEYS:
            if not isinstance(cat.get(k), str):
                errors.append(f"第 {idx} 条 category.{k} 缺失或不是字符串")


def validate_dataset(path: Path) -> tuple[list[dict] | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, [f"{path.name}: JSON 解析失败({e})"]
    if not isinstance(data, list):
        return None, [f"{path.name}: 顶层必须是数组"]
    if not data:
        return None, [f"{path.name}: 数组为空"]

    errors: list[str] = []
    seen_ids: set[int] = set()
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            errors.append(f"第 {idx} 条不是对象")
            continue
        i = item.get("id")
        if not isinstance(i, int) or isinstance(i, bool):
            errors.append(f"第 {idx} 条字段 id 缺失或不是整数")
        elif i in seen_ids:
            errors.append(f"第 {idx} 条 id={i} 重复,id 必须唯一")
        else:
            seen_ids.add(i)
        _check_str_fields(item, idx, errors)

    if errors:
        return None, errors
    return data, []


def load_benchmark(benchmark_dir: Path) -> list[tuple[Path, list[dict]]]:
    loaded: list[tuple[Path, list[dict]]] = []
    for path in discover_datasets(benchmark_dir):
        cases, errors = validate_dataset(path)
        if cases is None:
            print(f"[跳过] {path.name} 格式不正确:{';'.join(errors[:5])}"
                  + ("..." if len(errors) > 5 else "") + " 已跳过")
            continue
        loaded.append((path, cases))
    if not loaded:
        raise RuntimeError(f"{benchmark_dir} 下没有格式合法的 dataset*.json 文件")
    return loaded
