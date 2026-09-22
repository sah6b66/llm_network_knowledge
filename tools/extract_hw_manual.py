#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""华为 CHM 用户手册统一提取器。

从 manual_to_skill/tmp 下 HUAWEI_* 目录的 unzip/(CHM 全量解压产物)提取四个卷
(配置指南 / 命令参考 / 告警处理 / 日志参考)的纯文本,供测试集生成子任务检索。

每个手册目录产出:
  <out>/<手册名>/toc.json        # 全书章节树:name / local / path(祖先/本节名)
  <out>/<手册名>/<卷名>.txt      # 该卷全部页面纯文本,以 "===== [章节路径] (文件名)" 分节

用法:
  python tools/extract_hw_manual.py [--src E:\\...\\tmp] [--out d:\\tmp\\hw_extract]
      [--only 目录1,目录2]
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
from pathlib import Path

VOLUME_KEYS = {"配置指南": "配置指南", "命令参考": "命令参考",
               "命令行参考": "命令参考", "告警处理": "告警处理",
               "日志参考": "日志参考"}
VOLUME_ORDER = ("配置指南", "命令参考", "告警处理", "日志参考")

_PARAM_RE = re.compile(
    r'<UL>|</UL>|<LI>|param name="(Name|Local)" value="([^"]*)"', re.I)


def parse_hhc(text: str) -> list[dict]:
    """解析 .hhc 目录文件,返回扁平节点列表(含祖先链组成的 path)。"""
    items: list[dict] = []
    name_stack: list[str] = []
    pending_name: str | None = None
    for m in _PARAM_RE.finditer(text):
        tok = m.group(0)
        if tok == "<UL>":
            if pending_name is not None:
                name_stack.append(pending_name)
                pending_name = None
        elif tok == "</UL>":
            if name_stack:
                name_stack.pop()
        elif tok == "<LI>":
            pending_name = None
        else:
            kind, value = m.group(1), m.group(2)
            if kind == "Name":
                pending_name = value
            else:
                name = pending_name or ""
                items.append({"name": name, "local": value,
                              "path": "/".join(name_stack + [name])})
    return items


def html_to_text(html: str) -> str:
    """HTML 转可读纯文本:去脚本样式,表格单元格用 ' | ' 分隔,保留换行。"""
    html = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|table|ul|ol|pre|dt|dd)>", "\n", html)
    html = re.sub(r"(?i)</(td|th)>", " | ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    text = html_mod.unescape(html)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\| ?\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def find_volumes(items: list[dict]) -> dict[str, list[dict]]:
    """按章节路径中最早出现的卷关键词段,把节点归入四个卷。"""
    vols = {k: [] for k in VOLUME_ORDER}
    for it in items:
        for seg in it["path"].split("/"):
            vol = VOLUME_KEYS.get(seg)
            if vol is None:
                vol = next((v for k, v in VOLUME_KEYS.items() if k in seg), None)
            if vol:
                vols[vol].append(it)
                break
    return vols


def decode_html_bytes(raw: bytes) -> str:
    """按 meta charset 声明解码,否则依次尝试 utf-8/gbk/gb18030。"""
    encodings: list[str] = []
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:4000], re.I)
    if m:
        encodings.append(m.group(1).decode("ascii", "ignore"))
    encodings += ["utf-8", "gbk", "gb18030"]
    for enc in encodings:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("gb18030", errors="ignore")


def _locate(unzip: Path, local: str) -> Path | None:
    """按 hhc 的 Local 定位 HTML 文件:先按相对路径,再按 basename 兜底。"""
    rel = local.replace("\\", "/").lstrip("./")
    for cand in (unzip / rel, unzip / rel.split("/")[-1]):
        if cand.exists():
            return cand
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=r"E:\dev_cli_skill-main\GLM\manual_to_skill\tmp")
    ap.add_argument("--out", default=r"d:\tmp\hw_extract")
    ap.add_argument("--only", help="只处理指定手册目录名(逗号分隔)")
    args = ap.parse_args()
    src, out_root = Path(args.src), Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    dirs = sorted(d for d in src.iterdir()
                  if d.is_dir() and d.name.startswith("HUAWEI_"))
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        dirs = [d for d in dirs if d.name in want]
    for d in dirs:
        out_dir = out_root / d.name
        out_dir.mkdir(parents=True, exist_ok=True)
        unzip = d / "unzip"
        hhcs = sorted(unzip.glob("*.hhc"))
        if not hhcs:
            print(f"[skip] {d.name}: unzip 下无 .hhc")
            continue
        items = parse_hhc(hhcs[0].read_text(encoding="utf-8", errors="ignore"))
        (out_dir / "toc.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        vols = find_volumes(items)
        for vol in VOLUME_ORDER:
            parts, missing = [], 0
            for it in vols[vol]:
                f = _locate(unzip, it["local"])
                if f is None:
                    missing += 1
                    continue
                fname = f.relative_to(unzip).as_posix()
                parts.append(f"===== [{it['path']}] ({fname})\n\n"
                             + html_to_text(decode_html_bytes(f.read_bytes())))
            (out_dir / f"{vol}.txt").write_text("\n\n".join(parts), encoding="utf-8")
            print(f"[{d.name}] {vol}: {len(vols[vol])} 节, 缺文件 {missing}, "
                  f"{sum(len(p) for p in parts)} 字符")
        print(f"[{d.name}] toc: {len(items)} 节点")


if __name__ == "__main__":
    main()
