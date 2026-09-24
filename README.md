# LLM 网络知识掌握度评估

评估各大 LLM 对 IP 网络知识的掌握程度:从 100 个主题清单生成 basic / detail 两种模式各 100 题的测试集,由被评测 LLM 作答、裁判 LLM 按评分点打分(1-5),产出结构化报告。

另有 **RFC 专项测试集**:覆盖 2021-2025 年 50 篇标准-track RFC(每年 10 篇,涵盖路由、传输、安全、IPv6、DNS、VPN、组播、管理等领域),每篇出基本概念(简单)+ 详情(中)两题,共 100 例。

另有 **华为设备专项测试集**:基于华为官方 CHM 用户手册(CE 数据中心交换机 / S 园区交换机 / NetEngine 与 AR 路由器 / USG 防火墙 / AirEngine WLAN,共 10 个手册、5 个版本),覆盖特性、场景、配置方案、命令行、告警处理、日志六类问题共 100 例,每题绑定具体设备型号与软件版本,答案事实均出自手册原文。

## 目录结构

```
├── requirements.md        # 测试集生成规格(题目 schema 与质量要求)
├── data/
│   ├── topics.json        # 100 题主题清单(唯一源)
│   ├── topics_rfc.json    # RFC 专项主题清单(50 篇 RFC)
│   ├── topics_hw.json     # 华为设备专项主题清单(100 题,含型号/版本/分类配额)
│   ├── topics_slices/     # slice.py 生成的按层切片(可再生,不入库)
│   ├── cases/
│   │   ├── basic/         # basic 模式用例(100 题)
│   │   ├── detail/        # detail 模式用例(100 题)
│   │   ├── rfc_basic/     # RFC 专项·基本概念题(50 例,按年分文件)
│   │   ├── rfc_detail/    # RFC 专项·详情题(50 例,按年分文件)
│   │   └── hw/            # 华为设备专项用例(100 例,按产品族分文件)
│   └── benchmark/         # 合并后的最终数据集 dataset_*.json
├── tools/
│   ├── slice.py           # 按协议层把 topics.json 切成批次
│   ├── validate.py        # 校验工具(通用 / RFC 专项 / 华为专项三类模式)
│   ├── extract_hw_manual.py     # 华为 CHM 手册统一提取器(目录树+四卷纯文本)
│   ├── test_validate.py         # validate.py 的单元测试
│   ├── test_extract_hw_manual.py # extract_hw_manual.py 的单元测试
│   └── fixtures/          # validate.py 的测试夹具
├── llm_eval/              # 评测引擎(作答 + 裁判打分,详见其 README)
├── report/                # 评测产出(每个模型一个子目录,含 RECORD / EVALUATION / summary)
└── docs/                  # 历史规格与计划文档
```

## 使用流程

### 1. 生成测试集

```bash
python tools/slice.py                                    # 切片到 data/topics_slices/
python tools/validate.py data/topics.json --mode topics  # 校验主题清单
# 按 requirements.md 逐批产出用例后:
python tools/validate.py data/cases/basic/batch1_physical.json --mode cases
# 合并各批用例为 data/benchmark/dataset_common_<mode>.json 后:
python tools/validate.py data/benchmark/dataset_common_basic.json --mode full

# RFC 专项测试集:
python tools/validate.py data/topics_rfc.json --mode rfc_topics
python tools/validate.py data/cases/rfc_basic/rfc_2021.json --mode rfc_cases
# 合并基本概念(简单,id 1-50)+ 详情(中,id 51-100)为 data/benchmark/dataset_rfc.json 后:
python tools/validate.py data/benchmark/dataset_rfc.json --mode rfc_full

# 华为设备专项测试集(先从 CHM 手册提取语料到 d:/tmp/hw_extract/):
python tools/extract_hw_manual.py --src <手册tmp目录> --out d:/tmp/hw_extract
python tools/validate.py data/topics_hw.json --mode hw_topics
python tools/validate.py data/cases/hw/batch_s.json --mode hw_cases
# 合并各产品族为 data/benchmark/dataset_huawei_device.json 后:
python tools/validate.py data/benchmark/dataset_huawei_device.json --mode hw_full
```

### 2. 执行评测

```bash
cd llm_eval
cp config.example.json config.json   # 填入被评测/裁判 LLM 的连接信息
python main.py --config config.json  # mode=execute 作答;mode=evaluate 裁判打分
```

支持并发与断点续跑,详见 [llm_eval/README.md](llm_eval/README.md)。

### 3. 查看报告

产出在 `report/<模型>/` 下:`RECORD_<模型>_<思考模式>_<数据集>.json`(作答记录)、
`EVALUATION_<裁判>_<模型>_<思考模式>_<数据集>.json`(逐题评分)与
`EVALUATION_<裁判>_<模型>_<思考模式>_summary.md`(总结报告,按数据集分别统计,不做跨数据集合并)。

已完成评测(裁判 glm-5.3,思考模式 disabled,综合评分 / 5;按模型发布时间排序,
发布时间 / 参数规模 / 上下文窗口信息来自各官方模型卡与公开报道):

| 被评测模型 | 发布时间 | 参数规模 | 上下文 | common_basic | common_detail | huawei_device | rfc |
|---|---|---|---|---|---|---|---|
| Qwen2.5-32B-Instruct | 2024-09 | 32.5B(稠密) | 128K | 3.18 | 2.96 | 1.83 | 1.57 |
| DeepSeek-V3 | 2024-12 | 671B/37B 激活(MoE) | 128K | 3.81 | 3.66 | 2.20 | 2.13 |
| glm-4.7 | 2025-12 | 355B/32B 激活(MoE) | 200K | 4.57 | 4.18 | 2.78 | 2.77 |
| DeepSeek-V4-Flash | 2026-04 | 284B/13B 激活(MoE) | 1M | 4.15 | 4.01 | 2.47 | 2.35 |
| DeepSeek-V4-Pro | 2026-04 | 1.6T/49B 激活(MoE) | 1M | 4.24 | 4.13 | 2.55 | 2.43 |
| Kimi-K2.7-Code | 2026-06 | 1T/32B 激活(MoE) | 256K | 4.53 | 4.36 | 2.64 | 2.69 |
| Qwen3.8-27B | 2026-08 | 27B(稠密) | 262K | 3.63 | 3.14 | 1.99 | 1.65 |
