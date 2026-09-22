# IP 网络知识测试集生成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `requirements.md` 规格生成 100 条 IP 网络知识评估测试集，产出通过全部验收检查的 `dataset.json`。

**Architecture:** 先构建机器可校验的验证工具（validate.py，TDD），再"规划先行"产出满足全部维度配额的 100 条题目清单（topics.json），然后按协议层分 6 批撰写用例正文，每批经结构校验与质量自检，最后合并为 `dataset.json` 并执行完整验收（配额、交叉约束、RFC/CLI 真实性复核）。

**Tech Stack:** Python 3（标准库 json/argparse/glob，无第三方依赖）、WebFetch/WebSearch（RFC 真实性复核）。

**Spec:** `d:\network_knowledge_set\requirements.md`（本计划从该规格推导，执行者必须同时阅读规格原文，尤其是第 4~6 章与附录示例）。

## Global Constraints

- **项目非 git 仓库**：所有任务不含 commit 步骤，以"验证器 PASS"作为每个任务的完成检查点。
- **总量与格式**：100 条用例；`dataset.json` 为 UTF-8 无 BOM、2 空格缩进的 JSON 数组。
- **语言**：中文；协议名、技术术语、CLI 命令、RFC 名称保留英文。
- **枚举值**（闭合集合，禁止自造）：
  - `difficulty`: 简单 / 中 / 难
  - `category.scope`: 网络 / 设备 / 其他
  - `category.protocol_layer`: 物理层 / 链路层 / IP层 / 传输层 / 其他
  - `category.lifecycle`: 规划 / 建设 / 维护 / 优化 / 其他
  - `scenario`: 数据中心 / 园区 / 宽带城域 / Internet / 通用
  - `device_type`: 交换机 / 路由器 / 防火墙 / WLAN / 不限定
- **维度配额**（必须精确满足，执行时以 validate.py 核对）：
  - 难度：简单 20 / 中 50 / 难 30（简单不得超过 20）
  - 协议层：物理层 10 / 链路层 20 / IP层 30 / 传输层 15 / 其他 25
  - 生命周期：规划 20 / 建设 20 / 维护 35 / 优化 15 / 其他 10
  - 范围：网络 50 / 设备 45 / 其他 5
  - 场景：数据中心 25 / 园区 25 / 宽带城域 15 / Internet 10 / 通用 25
  - 设备类型：交换机 20 / 路由器 20 / 防火墙 10 / WLAN 10 / 不限定 40
- **交叉硬约束**：
  1. 近 4 年（2022/2023/2024/2025/2026 年发布）RFC 题不少于 15 条，每个自然年份至少 2 条。
  2. CLI 题不少于 20 条：华为不少于 10 条（其中 VRPv5 不少于 3 条、VRPv8 不少于 4 条；云杉版本资料不可核实时不得编造）；Cisco 不少于 8 条且至少覆盖 IOS / IOS-XE / IOS-XR / NX-OS 中两个平台；版本差异对比题不少于 5 条。
  3. 任意两条用例不得考察同一知识点；**不得使用 requirements.md 附录 A.1/A.2/A.3 已占用的三个知识点**（VRPv8 commit 两阶段配置、OSPF ExStart/Exchange 邻居停滞、EVPN VXLAN 热迁移后 MAC/ARP 收敛）。
- **标签约定**（validate.py 据此核对，执行者必须遵守）：
  - 涉及 RFC 的用例：tags 同时包含 `"RFC"`、`"RFC<编号>"`（如 `"RFC5440"`）、`"RFC-<发布年份>"`（如 `"RFC-2023"`）。
  - CLI 用例：tags 包含 `"CLI"`、厂商（`"华为"` 或 `"Cisco"`）、平台（华为：`"VRPv5"`/`"VRPv8"`/`"云杉"`；Cisco：`"IOS"`/`"IOS-XE"`/`"IOS-XR"`/`"NX-OS"`）。
  - 版本/平台差异对比题：tags 包含 `"版本差异"`。
- **防幻觉规则**（来自规格第 6 章）：RFC 编号与内容、CLI 语法必须真实准确且与所标注平台/版本一致；无法核实的内容宁可换题，不得编造。所有 RFC 编号在 Task 9 统一在线复核。
- **用例 JSON 骨架**（每条必须完整包含以下字段）：

```json
{
  "id": 1,
  "difficulty": "简单",
  "category": { "scope": "设备", "protocol_layer": "其他", "lifecycle": "建设" },
  "scenario": "通用",
  "device_type": "交换机",
  "question": "中文问题（术语/协议名/CLI 保留英文）",
  "answer": "标准参考答案",
  "scoring_points": ["要点1", "要点2", "要点3"],
  "tags": ["CLI", "华为", "VRPv8"]
}
```

- **内容质量标准**（每批撰写后逐条自检，来自规格第 5/6 章）：
  1. 无歧义：问题单一解读，答案确定或被 scoring_points 完全覆盖。
  2. 准确：RFC/CLI 内容真实准确。
  3. 无争议：不出随实现而异的无定解题。
  4. 区分度：简单题必须落在易错细节（CLI 语法细节、RFC 字段/编号/默认值），禁止"什么是 TCP"类送分题。
  5. 中文表述，术语保留英文，问题自包含。
  6. scoring_points 3–8 条，每条独立可判断，覆盖参考答案全部关键点。
  7. 篇幅指引：简单题答案 50–150 字；中等题 150–400 字；难题 300–800 字。

**工作目录**：所有命令均在 `d:\network_knowledge_set\` 下执行。

---

### Task 1: 校验工具 validate.py（TDD）

**Files:**
- Create: `tools/validate.py`
- Create: `fixtures/valid_cases.json`
- Create: `fixtures/invalid_cases.json`
- Create: `fixtures/partial_topics.json`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: CLI `python tools/validate.py <file.json> --mode topics|cases|full`
  - `topics`：校验题目清单——结构、topic 字段、100 条、全部维度配额、交叉约束（基于 tags）
  - `cases`：校验批次用例文件——结构、枚举、question/answer/scoring_points（3–8 条）、id 唯一
  - `full`：校验完整 dataset.json——cases 的全部检查 + 数量 100 + id 1–100 连续 + 配额 + 交叉约束
  - 退出码：0 = PASS；1 = FAIL（打印全部错误项）

- [ ] **Step 1: 编写测试夹具（先于实现）**

创建 `fixtures/valid_cases.json`（2 条合法用例，cases 模式必须 PASS）：

```json
[
  {
    "id": 1,
    "difficulty": "简单",
    "category": { "scope": "设备", "protocol_layer": "其他", "lifecycle": "建设" },
    "scenario": "通用",
    "device_type": "交换机",
    "question": "在华为 VRPv8 平台（例如 CloudEngine 系列交换机）上，通过命令行完成一段配置修改后，必须再执行哪条命令配置才会生效？这一行为与 VRPv5 平台（例如 S 系列交换机）有何本质区别？",
    "answer": "必须执行 commit 命令。VRPv8 采用两阶段配置模式：命令输入后先进入候选配置（candidate configuration），并不立即生效；执行 commit 后配置经校验生效，成为运行配置。而 VRPv5 采用一阶段配置模式，命令输入并回车后立即生效，无需额外提交动作。",
    "scoring_points": [
      "明确指出需执行 commit 命令",
      "说明 VRPv8 为两阶段配置：命令先进入候选配置，提交后才生效",
      "说明 VRPv5 为一阶段配置：命令立即生效"
    ],
    "tags": ["CLI", "华为", "VRPv8", "VRPv5", "版本差异"]
  },
  {
    "id": 2,
    "difficulty": "简单",
    "category": { "scope": "设备", "protocol_layer": "其他", "lifecycle": "建设" },
    "scenario": "通用",
    "device_type": "路由器",
    "question": "在 Cisco IOS 中，将当前运行配置保存为启动配置的常用命令是什么？请写出至少两种等价写法，并说明它们写入的目标位置。",
    "answer": "copy running-config startup-config，以及等价写法 write memory（可简写为 write mem）。两者均将 RAM 中的 running-config 写入 NVRAM 作为启动配置 startup-config。",
    "scoring_points": [
      "写出 copy running-config startup-config",
      "写出等价命令 write memory 或其简写",
      "说明作用是把 running-config 从 RAM 保存到 NVRAM 的 startup-config"
    ],
    "tags": ["CLI", "Cisco", "IOS"]
  }
]
```

创建 `fixtures/invalid_cases.json`（cases 模式必须 FAIL，含 5 处违规：difficulty 非法、scoring_points 仅 2 条、scenario 非法、缺 category.lifecycle、id 重复）：

```json
[
  {
    "id": 1,
    "difficulty": "容易",
    "category": { "scope": "设备", "protocol_layer": "其他" },
    "scenario": "城域",
    "device_type": "交换机",
    "question": "示例问题？",
    "answer": "示例答案。",
    "scoring_points": ["要点1", "要点2"],
    "tags": ["CLI", "华为"]
  },
  {
    "id": 1,
    "difficulty": "简单",
    "category": { "scope": "设备", "protocol_layer": "其他", "lifecycle": "建设" },
    "scenario": "通用",
    "device_type": "交换机",
    "question": "另一个问题？",
    "answer": "另一个答案。",
    "scoring_points": ["要点1", "要点2", "要点3"],
    "tags": ["CLI", "华为"]
  }
]
```

创建 `fixtures/partial_topics.json`（3 条题目清单，topics 模式必须 FAIL 并列出数量与配额差异——用于验证配额统计逻辑本身正确）：

```json
[
  { "id": 1, "difficulty": "简单", "category": { "scope": "设备", "protocol_layer": "物理层", "lifecycle": "建设" }, "scenario": "通用", "device_type": "交换机", "topic": "光模块规格与单模/多模判别", "tags": [] },
  { "id": 2, "difficulty": "中", "category": { "scope": "网络", "protocol_layer": "链路层", "lifecycle": "维护" }, "scenario": "园区", "device_type": "交换机", "topic": "MSTP 实例与 VLAN 映射错误导致的环路", "tags": [] },
  { "id": 3, "difficulty": "难", "category": { "scope": "网络", "protocol_layer": "IP层", "lifecycle": "优化" }, "scenario": "数据中心", "device_type": "不限定", "topic": "大规模 BGP 组网的 RR 分层与路由收敛优化", "tags": [] }
]
```

- [ ] **Step 2: 运行验证器确认其不存在（失败）**

Run: `python tools/validate.py fixtures/valid_cases.json --mode cases`
Expected: FAIL（`can't open file ... No such file or directory`）

- [ ] **Step 3: 实现 tools/validate.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 requirements.md 校验测试集。

用法:
  python tools/validate.py <file.json> --mode topics   # 题目清单: 结构+topic+配额+交叉
  python tools/validate.py <file.json> --mode cases    # 批次用例: 结构+内容+id唯一
  python tools/validate.py <file.json> --mode full     # 完整数据集: 全部检查
"""
import argparse
import json
import sys

ENUMS = {
    "difficulty": ["简单", "中", "难"],
    "scope": ["网络", "设备", "其他"],
    "protocol_layer": ["物理层", "链路层", "IP层", "传输层", "其他"],
    "lifecycle": ["规划", "建设", "维护", "优化", "其他"],
    "scenario": ["数据中心", "园区", "宽带城域", "Internet", "通用"],
    "device_type": ["交换机", "路由器", "防火墙", "WLAN", "不限定"],
}

QUOTAS = {
    "difficulty": {"简单": 20, "中": 50, "难": 30},
    "protocol_layer": {"物理层": 10, "链路层": 20, "IP层": 30, "传输层": 15, "其他": 25},
    "lifecycle": {"规划": 20, "建设": 20, "维护": 35, "优化": 15, "其他": 10},
    "scope": {"网络": 50, "设备": 45, "其他": 5},
    "scenario": {"数据中心": 25, "园区": 25, "宽带城域": 15, "Internet": 10, "通用": 25},
    "device_type": {"交换机": 20, "路由器": 20, "防火墙": 10, "WLAN": 10, "不限定": 40},
}

CISCO_PLATFORMS = ["IOS", "IOS-XE", "IOS-XR", "NX-OS"]
RECENT_YEARS = ["2022", "2023", "2024", "2025", "2026"]


def get_tags(c):
    t = c.get("tags")
    return t if isinstance(t, list) else []


def check_structure(cases, need_content, errors):
    for i, c in enumerate(cases):
        p = f"用例[{i}] id={c.get('id')}"
        if not isinstance(c, dict):
            errors.append(f"{p} 必须是对象")
            continue
        if not isinstance(c.get("id"), int):
            errors.append(f"{p} id 缺失或非整数")
        if c.get("difficulty") not in ENUMS["difficulty"]:
            errors.append(f"{p} difficulty 非法: {c.get('difficulty')}")
        cat = c.get("category")
        if not isinstance(cat, dict):
            errors.append(f"{p} 缺少 category")
        else:
            for k in ("scope", "protocol_layer", "lifecycle"):
                if cat.get(k) not in ENUMS[k]:
                    errors.append(f"{p} category.{k} 非法: {cat.get(k)}")
        for k in ("scenario", "device_type"):
            if c.get(k) not in ENUMS[k]:
                errors.append(f"{p} {k} 非法: {c.get(k)}")
        tags = c.get("tags")
        if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
            errors.append(f"{p} tags 必须为非空字符串数组")
        has_num = any(t.startswith("RFC") and t[3:].isdigit() for t in get_tags(c))
        has_year = any(t.startswith("RFC-") and t[4:] in RECENT_YEARS for t in get_tags(c))
        if has_year and not has_num:
            errors.append(f"{p} 含 RFC-年份 标签但缺少 RFC 编号标签")
        if need_content:
            for k in ("question", "answer"):
                v = c.get(k)
                if not isinstance(v, str) or not v.strip():
                    errors.append(f"{p} {k} 缺失或为空")
            sp = c.get("scoring_points")
            ok = isinstance(sp, list) and 3 <= len(sp) <= 8 and all(
                isinstance(s, str) and s.strip() for s in sp)
            if not ok:
                errors.append(f"{p} scoring_points 必须为 3-8 条非空字符串")
    ids = [c.get("id") for c in cases
           if isinstance(c, dict) and isinstance(c.get("id"), int)]
    if len(ids) != len(set(ids)):
        errors.append("存在重复 id")
    return ids


def check_quotas(cases, errors):
    getters = {
        "difficulty": lambda c: c.get("difficulty"),
        "scope": lambda c: (c.get("category") or {}).get("scope"),
        "protocol_layer": lambda c: (c.get("category") or {}).get("protocol_layer"),
        "lifecycle": lambda c: (c.get("category") or {}).get("lifecycle"),
        "scenario": lambda c: c.get("scenario"),
        "device_type": lambda c: c.get("device_type"),
    }
    for dim, table in QUOTAS.items():
        actual = {}
        for c in cases:
            v = getters[dim](c)
            actual[v] = actual.get(v, 0) + 1
        for k, want in table.items():
            got = actual.get(k, 0)
            if got != want:
                errors.append(f"配额不符 [{dim}] {k}: 实际 {got}, 要求 {want}")


def check_cross(cases, errors):
    cli = [c for c in cases if "CLI" in get_tags(c)]
    if len(cli) < 20:
        errors.append(f"CLI 题不足: {len(cli)} < 20")
    hw = [c for c in cli if "华为" in get_tags(c)]
    if len(hw) < 10:
        errors.append(f"华为 CLI 题不足: {len(hw)} < 10")
    for plat, minimum in (("VRPv5", 3), ("VRPv8", 4)):
        n = sum(1 for c in hw if plat in get_tags(c))
        if n < minimum:
            errors.append(f"华为 {plat} 题不足: {n} < {minimum}")
    cs = [c for c in cli if "Cisco" in get_tags(c)]
    if len(cs) < 8:
        errors.append(f"Cisco CLI 题不足: {len(cs)} < 8")
    covered = [p for p in CISCO_PLATFORMS if any(p in get_tags(c) for c in cs)]
    if len(covered) < 2:
        errors.append(f"Cisco 平台覆盖不足 2 个: 当前 {covered}")
    diff = [c for c in cases if "版本差异" in get_tags(c)]
    if len(diff) < 5:
        errors.append(f"版本差异对比题不足: {len(diff)} < 5")
    recent = {}
    for c in cases:
        for t in get_tags(c):
            if t.startswith("RFC-") and t[4:] in RECENT_YEARS:
                recent[t[4:]] = recent.get(t[4:], 0) + 1
    total = sum(recent.values())
    if total < 15:
        errors.append(f"近4年 RFC 题不足: {total} < 15")
    for y in RECENT_YEARS:
        if recent.get(y, 0) < 2:
            errors.append(f"RFC-{y} 题不足: {recent.get(y, 0)} < 2")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--mode", required=True, choices=["topics", "cases", "full"])
    args = ap.parse_args()
    errors = []
    raw = open(args.file, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("文件含 BOM")
    try:
        cases = json.loads(raw.decode("utf-8-sig"))
    except Exception as e:
        print(f"FAIL: JSON 解析失败: {e}")
        sys.exit(1)
    if not isinstance(cases, list):
        print("FAIL: 顶层必须是数组")
        sys.exit(1)
    need_content = args.mode in ("cases", "full")
    ids = check_structure(cases, need_content, errors)
    if args.mode == "topics":
        if len(cases) != 100:
            errors.append(f"题目数 {len(cases)} != 100")
        for i, c in enumerate(cases):
            t = c.get("topic")
            if not isinstance(t, str) or not t.strip():
                errors.append(f"用例[{i}] id={c.get('id')} topic 缺失或为空")
        check_quotas(cases, errors)
        check_cross(cases, errors)
    elif args.mode == "full":
        if len(cases) != 100:
            errors.append(f"用例数 {len(cases)} != 100")
        if sorted(ids) != list(range(1, 101)):
            errors.append("id 必须为 1-100 连续唯一")
        check_quotas(cases, errors)
        check_cross(cases, errors)
    if errors:
        print(f"FAIL ({len(errors)} 项):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print(f"PASS: {len(cases)} 条, 模式 {args.mode}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行三个夹具验证行为**

Run: `python tools/validate.py fixtures/valid_cases.json --mode cases`
Expected: `PASS: 2 条, 模式 cases`

Run: `python tools/validate.py fixtures/invalid_cases.json --mode cases`
Expected: FAIL，至少包含：difficulty 非法"容易"、category.lifecycle 非法 None、scenario 非法"城域"、scoring_points 2 条违规、重复 id

Run: `python tools/validate.py fixtures/partial_topics.json --mode topics`
Expected: FAIL，包含 `题目数 3 != 100`，以及各维度配额差异（如 `配额不符 [difficulty] 简单: 实际 1, 要求 20`）、`CLI 题不足: 0 < 20`、`近4年 RFC 题不足: 0 < 15`——确认统计逻辑输出正确

---

### Task 2: 题目清单 topics.json（规划先行）

**Files:**
- Create: `topics.json`
- Create: `tools/slice.py`

**Interfaces:**
- Consumes: `python tools/validate.py ... --mode topics`（Task 1）
- Produces: `topics.json`——100 个对象的数组，每个对象含 `id`、`difficulty`、`category{scope,protocol_layer,lifecycle}`、`scenario`、`device_type`、`topic`（一句话中文考点）、`tags`（遵守 Global Constraints 标签约定）；后续所有批次任务从该文件切片取题

- [ ] **Step 1: 起草 100 条题目清单**

要求：
1. 每条按 Global Constraints 的配额表分配六个维度，先用一张草稿矩阵规划（可先在本地推算），确保每个维度的精确配额。
2. 覆盖面要求：近 4 年 RFC 题 15+ 条（2022–2026 每年 ≥2，tags 按 RFC/RFC<编号>/RFC-<年份> 约定）；CLI 题 20+ 条（华为 VRPv5≥3、VRPv8≥4、Cisco≥8 且 ≥2 平台、版本差异对比 ≥5）；知识点覆盖：以太网/光传输（物理层）、VLAN/STP/链路聚合/MACSec/ARP（链路层）、OSPF/IS-IS/BGP/VRF/组播/QoS/VXLAN EVPN（IP层及其他）、TCP/UDP/QUIC/负载均衡（传输层）、防火墙/WLAN/安全/网络管理/NTP/DHCP/DNS（其他）；难度按 20/50/30 且简单题考点必须是易错细节（CLI 语法、RFC 字段/编号/默认值），禁止送分考点。
3. **拟用的每个 RFC 编号先用 WebSearch/WebFetch 在 ietf.org 或 datatracker 上核实标题与发布年份**，禁止凭记忆写编号；核实不了就换考点。
4. 禁止与 requirements.md 附录 A.1/A.2/A.3 及 Global Constraints 列出的三个已占用知识点重复；100 条之间不得重复知识点。

- [ ] **Step 2: 写入 topics.json 并校验**

Run: `python tools/validate.py topics.json --mode topics`
Expected: `PASS: 100 条, 模式 topics`（配额或交叉约束不符时按输出逐项修正后重跑）

- [ ] **Step 3: 人工通读去重复核**

逐条通读 100 个 `topic` 字段，确认无同一知识点的不同表述（如"OSPF LSA 类型"与"OSPF Type-5 LSA 细节"视为重复）；发现重复即替换考点并重跑 Step 2 校验。

- [ ] **Step 4: 生成批次切片**

创建 `tools/slice.py`：

```python
import json
import os

os.makedirs("batches", exist_ok=True)
ts = json.load(open("topics.json", encoding="utf-8"))

def by_layer(layer, offset=0, limit=None):
    sel = [t for t in ts if t["category"]["protocol_layer"] == layer]
    sel = sel[offset:]
    if limit:
        sel = sel[:limit]
    return sel

out = {
    "batches/topics_1_physical.json": by_layer("物理层"),
    "batches/topics_2_link.json": by_layer("链路层"),
    "batches/topics_3a_ip.json": by_layer("IP层", 0, 15),
    "batches/topics_3b_ip.json": by_layer("IP层", 15),
    "batches/topics_4_transport.json": by_layer("传输层"),
    "batches/topics_5_other.json": by_layer("其他"),
}
for f, sel in out.items():
    json.dump(sel, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f, len(sel))
```

Run: `python tools/slice.py`
Expected: 输出 6 行，条数分别为 10 / 20 / 15 / 15 / 15 / 25（合计 100）

---

### Task 3: 批次 1 — 物理层 10 条

**Files:**
- Create: `batches/batch1_physical.json`

**Interfaces:**
- Consumes: `batches/topics_1_physical.json`（10 条题目定义，字段同 Task 2 Produces）
- Produces: `batches/batch1_physical.json`——10 个完整用例（Global Constraints 的 JSON 骨架全部字段），id 与切片一致

- [ ] **Step 1: 阅读切片**

Read: `batches/topics_1_physical.json`（10 条）

- [ ] **Step 2: 撰写 10 条完整用例**

对每条题目撰写 `question`（自包含、无歧义、中文+英文术语）、`answer`（篇幅按难度指引）、`scoring_points`（3–8 条），保留切片的全部维度字段与 tags。涉及 CLI 的每条命令按平台核实；涉及 RFC 的确认编号与内容一致。

- [ ] **Step 3: 结构校验**

Run: `python tools/validate.py batches/batch1_physical.json --mode cases`
Expected: `PASS: 10 条, 模式 cases`

- [ ] **Step 4: 质量自检**

按 Global Constraints 的 7 条内容质量标准逐条自检本批 10 条；不合格的重写后重跑 Step 3。

---

### Task 4: 批次 2 — 链路层 20 条

**Files:**
- Create: `batches/batch2_link.json`

**Interfaces:**
- Consumes: `batches/topics_2_link.json`（20 条题目定义）
- Produces: `batches/batch2_link.json`——20 个完整用例

- [ ] **Step 1: 阅读切片**

Read: `batches/topics_2_link.json`（20 条）

- [ ] **Step 2: 撰写 20 条完整用例**

同 Task 3 Step 2 的撰写要求（question/answer/scoring_points 质量标准见 Global Constraints）。

- [ ] **Step 3: 结构校验**

Run: `python tools/validate.py batches/batch2_link.json --mode cases`
Expected: `PASS: 20 条, 模式 cases`

- [ ] **Step 4: 质量自检**

同 Task 3 Step 4，自检本批 20 条。

---

### Task 5: 批次 3a — IP 层前 15 条

**Files:**
- Create: `batches/batch3a_ip.json`

**Interfaces:**
- Consumes: `batches/topics_3a_ip.json`（15 条题目定义）
- Produces: `batches/batch3a_ip.json`——15 个完整用例

- [ ] **Step 1: 阅读切片**

Read: `batches/topics_3a_ip.json`（15 条）

- [ ] **Step 2: 撰写 15 条完整用例**

同 Task 3 Step 2 的撰写要求（question/answer/scoring_points 质量标准见 Global Constraints）。

- [ ] **Step 3: 结构校验**

Run: `python tools/validate.py batches/batch3a_ip.json --mode cases`
Expected: `PASS: 15 条, 模式 cases`

- [ ] **Step 4: 质量自检**

同 Task 3 Step 4，自检本批 15 条。

---

### Task 6: 批次 3b — IP 层后 15 条

**Files:**
- Create: `batches/batch3b_ip.json`

**Interfaces:**
- Consumes: `batches/topics_3b_ip.json`（15 条题目定义）
- Produces: `batches/batch3b_ip.json`——15 个完整用例

- [ ] **Step 1: 阅读切片**

Read: `batches/topics_3b_ip.json`（15 条）

- [ ] **Step 2: 撰写 15 条完整用例**

同 Task 3 Step 2 的撰写要求（question/answer/scoring_points 质量标准见 Global Constraints）。

- [ ] **Step 3: 结构校验**

Run: `python tools/validate.py batches/batch3b_ip.json --mode cases`
Expected: `PASS: 15 条, 模式 cases`

- [ ] **Step 4: 质量自检**

同 Task 3 Step 4，自检本批 15 条。

---

### Task 7: 批次 4 — 传输层 15 条

**Files:**
- Create: `batches/batch4_transport.json`

**Interfaces:**
- Consumes: `batches/topics_4_transport.json`（15 条题目定义）
- Produces: `batches/batch4_transport.json`——15 个完整用例

- [ ] **Step 1: 阅读切片**

Read: `batches/topics_4_transport.json`（15 条）

- [ ] **Step 2: 撰写 15 条完整用例**

同 Task 3 Step 2 的撰写要求（question/answer/scoring_points 质量标准见 Global Constraints）。

- [ ] **Step 3: 结构校验**

Run: `python tools/validate.py batches/batch4_transport.json --mode cases`
Expected: `PASS: 15 条, 模式 cases`

- [ ] **Step 4: 质量自检**

同 Task 3 Step 4，自检本批 15 条。

---

### Task 8: 批次 5 — 其他层 25 条

**Files:**
- Create: `batches/batch5_other.json`

**Interfaces:**
- Consumes: `batches/topics_5_other.json`（25 条题目定义）
- Produces: `batches/batch5_other.json`——25 个完整用例

- [ ] **Step 1: 阅读切片**

Read: `batches/topics_5_other.json`（25 条）

- [ ] **Step 2: 撰写 25 条完整用例**

同 Task 3 Step 2 的撰写要求（question/answer/scoring_points 质量标准见 Global Constraints）。

- [ ] **Step 3: 结构校验**

Run: `python tools/validate.py batches/batch5_other.json --mode cases`
Expected: `PASS: 25 条, 模式 cases`

- [ ] **Step 4: 质量自检**

同 Task 3 Step 4，自检本批 25 条。

---

### Task 9: 合并与完整验收

**Files:**
- Create: `tools/merge.py`
- Create: `dataset.json`
- Create: `ACCEPTANCE.md`

**Interfaces:**
- Consumes: `batches/batch1_physical.json` … `batches/batch5_other.json`（6 个批次文件，Task 3–8 产出）
- Produces: `dataset.json`（最终交付物）；`ACCEPTANCE.md`（验收声明）

- [ ] **Step 1: 创建 tools/merge.py 并执行合并**

```python
import glob
import json

cases = []
for f in sorted(glob.glob("batches/batch*.json")):
    cases += json.load(open(f, encoding="utf-8"))
cases.sort(key=lambda c: c["id"])
assert len(cases) == 100, f"合并后共 {len(cases)} 条"
with open("dataset.json", "w", encoding="utf-8", newline="\n") as f:
    json.dump(cases, f, ensure_ascii=False, indent=2)
print("merged:", len(cases))
```

Run: `python tools/merge.py`
Expected: `merged: 100`

- [ ] **Step 2: 完整校验**

Run: `python tools/validate.py dataset.json --mode full`
Expected: `PASS: 100 条, 模式 full`（任何配额/交叉约束不符都不得进入下一步）

- [ ] **Step 3: RFC 真实性复核**

提取 dataset.json 中全部 `RFC<编号>` 标签，对每个编号用 WebFetch 访问 `https://www.rfc-editor.org/info/rfc<编号>`（或 WebSearch）核对标题与发布年份是否与题目内容一致。发现不符的用例：替换为已核实的备选知识点，重走该条所在批次的 Step 3 校验与本步，直到全部一致。

- [ ] **Step 4: CLI 语法抽查**

对全部 CLI 题目（tags 含 CLI）逐条核对命令语法与所标注平台/版本一致；不确定的命令用厂商官方文档核实或换题，修改后重跑 Step 2。

- [ ] **Step 5: 全局去重复核 + 撰写验收声明**

通读 100 条 `question`，确认无知识点重复。创建 `ACCEPTANCE.md`，逐项勾选 requirements.md 第 8 章验收清单（9 项），附各维度配额核对统计表（validate.py full 模式 PASS 输出即为佐证）与 RFC/CLI 复核结论。
