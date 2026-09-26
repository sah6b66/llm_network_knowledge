# LLM 网络知识掌握度评估

评估各大 LLM 对 IP 网络知识的掌握程度:被评测 LLM 逐题作答,裁判 LLM 按评分点判定并给 1-5 总分,产出结构化报告(逐题评分 + 按维度统计 + 知识缺口归因)。

## 测试集构成

共 4 个数据集、400 题,每题均为**开放问答**,包含题目、参考答案与评分要点(平均每题约 5 个评分点)。

### 1. 通用网络知识(dataset_common_basic / dataset_common_detail)

覆盖 IP 网络通用知识体系,同一批 100 个主题出两套题:**basic** 侧重概念原理与机制理解,**detail** 侧重参数级细节、数值与深度推演(题干更长、评分点更多)。

知识来源:IETF RFC、IEEE 以太网标准等公开协议规范,TCP/IP 技术体系,以及主流厂商(Cisco IOS、华为 VRP)的通用实现约定;高频主题包括以太网与光模块、路由协议(BGP/OSPF 等)、TCP、WLAN、防火墙、光传输等。

每题按六个维度标注分类,便于按维度统计得分分布:

| 维度 | 取值与题量分布 |
|---|---|
| 难度 | 简单 20 / 中 50 / 难 30 |
| 协议层 | 物理层 10 / 链路层 20 / IP 层 30 / 传输层 15 / 其他(安全、管理、无线等)25 |
| 知识范围 | 网络原理 50 / 设备实现 45 / 其他 5 |
| 生命周期 | 规划 20 / 建设 20 / 维护 35 / 优化 15 / 其他 10 |
| 网络场景 | 园区 25 / 数据中心 25 / 宽带城域 15 / Internet 10 / 通用 25 |
| 设备类型 | 交换机 20 / 路由器 20 / 防火墙 10 / WLAN 10 / 不限定 40 |

### 2. RFC 专项(dataset_rfc)

覆盖 2021-2025 年 50 篇标准-track RFC(每年 10 篇,涵盖路由、传输、安全、IPv6、DNS、VPN、组播、管理等领域),每篇出基本概念(简单)+ 详情(中)两题,共 100 例(简单 50 / 中 50),每题绑定 RFC 编号——用于考察模型对**近年新标准**的掌握与时效性。

### 3. 华为设备专项(dataset_huawei_device)

基于华为官方公开用户手册(CE 数据中心交换机 / S 园区交换机 / NetEngine 与 AR 路由器 / USG 防火墙 / AirEngine WLAN,共 10 个手册、5 个版本),覆盖特性、场景、配置方案、命令行、告警处理、日志六类问题共 100 例(简单 10 / 中 90)。答案事实均出自手册原文——用于考察厂商设备知识的掌握。

## 目录结构

```
├── data/
│   └── benchmark/                # ★ 评测数据集(评测直接使用)
│       ├── dataset_common_basic.json     # 通用·概念原理(100 题)
│       ├── dataset_common_detail.json    # 通用·参数细节(100 题)
│       ├── dataset_rfc.json              # RFC 专项(100 题)
│       └── dataset_huawei_device.json    # 华为设备专项(100 题)
├── report/                       # ★ 评测产出(每个模型一个子目录)
│   └── <模型名>/
│       ├── RECORD_<模型>_<思考模式>_<数据集>.json            # 作答记录(逐题)
│       ├── EVALUATION_<裁判>_<模型>_<思考模式>_<数据集>.json  # 裁判评分(逐题)
│       └── EVALUATION_<裁判>_<模型>_<思考模式>_summary.md     # 总结报告
├── llm_eval/                     # 评测引擎(配置/作答/裁判打分/报告生成,详见其 README)
├── data/ 其余目录、tools/、docs/  # 测试集生成与校验的过程文件和辅助工具
├── LLM网络知识评测基准调研报告.md  # 相关公开评测基准调研
└── LICENSE
```

## 执行评测

### 1. 配置

```bash
cd llm_eval
cp config.example.json config.json
```

在 `config.json` 中填写两个 LLM 的连接信息:

- `evaluatee_llm`:被评测模型(provider / api_url / api_key / model / thinking.mode 等)
- `judge_llm`:裁判模型(建议选用能力较强的模型)
- `concurrency`(并发数)、`max_retries`、`temperature` 等运行参数

### 2. 作答(mode=execute)

```bash
# config.json 中 "mode": "execute"
python main.py --config config.json
```

逐题调用被评测模型作答,产出 `report/<模型>/RECORD_*.json`。支持并发执行与**断点续跑**:中断后重跑会自动跳过已完成题目,仅重答失败或未完成的题。

### 3. 裁判打分(mode=evaluate)

```bash
# config.json 中 "mode": "evaluate"
python main.py --config config.json
```

裁判模型对每题按评分要点逐条判定命中情况并给 1-5 总分,产出 `EVALUATION_*.json`;随后自动生成 summary 总结报告。同样支持断点续跑,作答或评分失败的题重跑对应模式会自动补齐。

### 4. 查看报告

以被评测模型 DeepSeek-V4-Flash(裁判 glm-5.3)为例,产出在 `report/DeepSeek-V4-Flash/` 下:

```
RECORD_DeepSeek-V4-Flash_disabled_dataset_common_basic.json             # 作答记录
EVALUATION_glm-5.3_DeepSeek-V4-Flash_disabled_dataset_common_basic.json # 逐题评分
EVALUATION_glm-5.3_DeepSeek-V4-Flash_disabled_summary.md                # 总结报告
```

summary 按数据集分别统计(不做跨数据集合并),每个数据集包含:总体评价(通过率/综合评分)、按各分类维度的得分分布表、知识缺口(命中率低于 50% 的评分要点)、不通过题目详情与归因分析。

已完成评测(裁判 glm-5.3,综合评分 / 5;按模型发布时间排序,发布时间 / 参数规模 / 上下文窗口信息来自各官方模型卡与公开报道):

| 被评测模型 | 发布时间 | 参数规模 | 上下文 | common_basic | common_detail | huawei_device | rfc |
|---|---|---|---|---|---|---|---|
| Qwen2.5-32B-Instruct | 2024-09 | 32.5B(稠密) | 128K | 3.18 | 2.96 | 1.83 | 1.57 |
| DeepSeek-V3 | 2024-12 | 671B/37B 激活(MoE) | 128K | 3.81 | 3.66 | 2.20 | 2.13 |
| glm-4.7 | 2025-12 | 355B/32B 激活(MoE) | 200K | 4.57 | 4.18 | 2.78 | 2.77 |
| Qwen3.5-122B-A10B | 2026-02 | 122B/10B 激活(MoE) | 256K | 3.80 | 3.67 | 2.23 | 2.07 |
| DeepSeek-V4-Flash | 2026-04 | 284B/13B 激活(MoE) | 1M | 4.15 | 4.01 | 2.47 | 2.35 |
| DeepSeek-V4-Pro | 2026-04 | 1.6T/49B 激活(MoE) | 1M | 4.24 | 4.13 | 2.55 | 2.43 |
| Kimi-K2.7-Code | 2026-06 | 1T/32B 激活(MoE) | 256K | 4.53 | 4.36 | 2.64 | 2.69 |
| Qwen3.8-27B | 2026-08 | 27B(稠密) | 262K | 3.63 | 3.14 | 1.99 | 1.65 |
| glm-5.3* | 2026-08 | 753B/40B 激活(MoE) | 1M | 4.71 | 4.52 | 2.92 | 3.17 |
| Xing4.0-29B | 2026-09 | 29B/4B 激活(MoE) | 256K | 2.84 | 2.42 | 1.71 | 1.35 |

\* glm-5.3 官方不支持禁用思考(thinking.type 仅 enabled),该行以思考模式 enabled(默认 max 档)
评测,与其余模型(思考模式 disabled)不完全可比。
