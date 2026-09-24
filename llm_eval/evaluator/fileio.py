"""原子 JSON 写出:临时文件 + os.replace,中断不损坏目标文件。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

_REPLACE_ATTEMPTS = 5


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Windows 下目标文件可能被杀毒/索引或并发读取方瞬时占用,
    # os.replace 报 PermissionError(WinError 5),短暂重试后仍失败才放弃
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.2 * (attempt + 1))
