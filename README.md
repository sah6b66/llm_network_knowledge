# LLM 网络知识掌握度评估

评估各大 LLM 对 IP 网络知识的掌握程度:从 100 个主题清单生成 basic / detail 两种模式各 100 题的测试集,由被评测 LLM 作答、裁判 LLM 按评分点打分(1-5),产出结构化报告。

## 目录结构

```
├── requirements.md        # 测试集生成规格(题目 schema 与质量要求)
├── data/
│   ├── topics.json        # 100 题主题清单(唯一源)
│   ├── topics_slices/     # slice.py 生成的按层切片(可再生,不入库)
│   ├── cases/
│   │   ├── basic/         # basic 模式用例(100 题)
│   │   └── detail/        # detail 模式用例(100 题)
│   └── benchmark/         # 合并后的最终数据集 dataset_*.json
├── tools/
│   ├── slice.py           # 按协议层把 topics.json 切成批次
│   ├── validate.py        # 校验 topics / cases / dataset 三种模式
│   └── fixtures/          # validate.py 的测试夹具
├── llm_eval/              # 评测引擎(作答 + 裁判打分,详见其 README)
├── report/                # 评测产出(summary.md 为结果总览)
└── docs/                  # 历史规格与计划文档
```

## 使用流程

### 1. 生成测试集

```bash
python tools/slice.py                                    # 切片到 data/topics_slices/
python tools/validate.py data/topics.json --mode topics  # 校验主题清单
# 按 requirements.md 逐批产出用例后:
python tools/validate.py data/cases/basic/batch1_physical.json --mode cases
# 合并各批用例为 data/benchmark/dataset_<mode>.json 后:
python tools/validate.py data/benchmark/dataset_basic.json --mode full
```

### 2. 执行评测

```bash
cd llm_eval
cp config.example.json config.json   # 填入被评测/裁判 LLM 的连接信息
python main.py --config config.json  # mode=execute 作答;mode=evaluate 裁判打分
```

支持并发与断点续跑,详见 [llm_eval/README.md](llm_eval/README.md)。

### 3. 查看报告

产出在 `report/<模型>/` 下;跨模型结果总览见 [report/summary.md](report/summary.md)。

首次全量评测:glm-4.7(非思考)× 裁判 glm-5.3,200 题平均 **4.42 / 5**(basic 4.55,detail 4.30)。
