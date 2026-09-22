# LLM 网络知识掌握度评估程序 — 设计文档

日期:2026-09-21
状态:已经用户批准的设计,待实现
项目位置:`d:\network_knowledge_set\llm_eval\`(新建)

## 1. 目标与背景

评估各大模型的 IP 网络知识掌握程度。程序分两个模式(由配置文件指定):

- **执行模式(execute)**:读取 `benchmark/` 下以 `dataset` 开头的 JSON 数据集,逐题调用被评测 LLM,保存 RECORD 文件
- **评估模式(evaluate)**:读取 RECORD,通过独立的裁判 LLM 按 scoring_points 逐点判定并给 1-5 总分,生成 EVALUATION 文件与 summary.md

数据集格式统一(100 条用例数组,字段:id/difficulty/category{scope,protocol_layer,lifecycle}/scenario/device_type/question/answer/scoring_points/tags),但不限定具体文件,数量可变。

已确认的关键决策:
- 一次运行评测**单个**(模型×思考模式)组合;评测多个模型则多次运行
- 执行模式**并发+断点续跑**
- 裁判评分粒度:**逐评分点命中判定 + 1-5 总分**

## 2. 架构决策:LLM client 裁剪复制(方案 A)

从 `D:\nl2cli_light\src\external_llm\` 复制裁剪 `providers.py` 与 `thinking_handler.py` 到本程序:

- **保留**:多 provider 支持(GLM/DeepSeek/千问 DashScope 与 OpenAI 兼容/Anthropic 兼容/OpenAI reasoning/MiniMax/vLLM)、各 provider 的思考模式参数注入策略、思考内容提取(`CleanedContent`)、请求重试与指数退避、requests Session 连接池、ssl_verify、`${ENV_VAR}` 形式的 api_key 解析
- **裁剪**:backup_llm / auto_switch 故障转移全部去掉——评测中途切换模型会污染结果,被评测模型失败只能对原模型重试;`adaptive` 思考模式支持去掉,思考模式只有 `enabled` / `disabled` 两值
- **简化**:LLMClient 构造改为直接接收配置 dict(不读 nl2cli_light 的配置文件布局);`chat()` 返回完整结果 dict(content/thinking/usage),由 runner 自行组装

技术栈:Python 3.10+,唯一第三方依赖 `requests`。并发用 `concurrent.futures.ThreadPoolExecutor`(requests 为阻塞 IO,线程池合适)。

## 3. 目录结构与运行形态

```
d:\network_knowledge_set\
├── benchmark\                          # 已有,数据集
├── report\<模型名>\                    # 运行产出,自动创建
│   ├── RECORD_<模型>_<思考模式>_<数据集stem>.json
│   ├── EVALUATION_<裁判模型>_<模型>_<思考模式>_<数据集stem>.json
│   └── EVALUATION_<裁判模型>_<模型>_<思考模式>_summary.md
└── llm_eval\
    ├── main.py                         # 入口
    ├── config.example.json
    ├── evaluator\
    │   ├── __init__.py
    │   ├── config.py                   # 配置加载+校验
    │   ├── llm_client.py               # 裁剪自 nl2cli_light
    │   ├── benchmark.py                # 数据集格式校验+加载
    │   ├── runner.py                   # 执行模式
    │   ├── judge.py                    # 评估模式:裁判调用+结构化解析
    │   └── report.py                   # EVALUATION 写出+summary 统计生成
    └── tests\                          # pytest
```

运行方式:`python llm_eval/main.py --config llm_eval/config.json`(--config 缺省即该值)。模式只在配置文件中指定,不提供命令行覆盖。文件名中的模型名/思考模式若含 Windows 非法字符(`\/:*?"<>|`)统一替换为 `-`。

## 4. 配置文件(config.example.json)

配置中**只有两个 LLM**:`evaluatee_llm`(被评测)与 `judge_llm`(裁判),节点结构完全相同;`mode` 决定本次运行调用哪一个。评估模式的报告目录定位直接取 `evaluatee_llm.model` 的模型名,无需额外字段。

```json
{
  "mode": "execute",
  "benchmark_dir": "../benchmark",
  "report_dir": "../report",
  "evaluatee_llm": {
    "provider": "GLM",
    "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "api_key": "sk-your-key",
    "model": "glm-4.6",
    "timeout": 300,
    "max_tokens": 32768,
    "thinking": {"mode": "enabled"}
  },
  "judge_llm": {
    "provider": "GLM",
    "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "api_key": "sk-your-key",
    "model": "glm-4.6",
    "timeout": 300,
    "max_tokens": 32768,
    "thinking": {"mode": "enabled"}
  },
  "concurrency": 4,
  "max_retries": 2,
  "temperature": 0.1
}
```

- 相对路径相对配置文件所在目录解析
- `thinking.mode` 取值:仅 `enabled` / `disabled`,该值同时用于输出文件名
- 公共参数:`concurrency`(并发,默认 4)、`max_retries`(默认 2)、`temperature`(仅执行模式使用,裁判固定 0)
- 配置校验:mode 合法、两个 LLM 节点齐全;执行模式要求 `evaluatee_llm` 连接信息(api_url/api_key/model)完整,评估模式要求 `judge_llm` 完整且 `evaluatee_llm.model` 非空(仅用于目录定位,不发起调用)。校验失败 → 启动即报错退出,非零退出码

## 5. 执行模式(runner)

### 5.1 数据集发现与校验(benchmark.py)

扫描 `benchmark_dir` 下文件名以 `dataset` 开头且以 `.json` 结尾的文件,逐个校验:

- 顶层为 JSON 数组,非空
- 每个元素为对象,必含字段且类型正确:`id`(int)、`difficulty`(str)、`category`(obj,含 scope/protocol_layer/lifecycle 三个 str)、`scenario`(str)、`device_type`(str)、`question`(非空 str)、`answer`(str)、`scoring_points`(非空 str 数组)、`tags`(str 数组)
- `id` 在文件内唯一

**校验失败的文件跳过执行并打印精确定位**(如 `dataset_xxx.json 第 17 条(从 1 计)缺少字段 scoring_points,已跳过`),不中断其他文件。

### 5.2 逐题调用

- 被评测 prompt:system = `你是一位资深网络技术专家。请准确回答网络技术问题:直接针对问题分条作答,覆盖关键要点,不要展开与问题无关的背景知识,回答控制在 500 字以内。`(2026-09-21 修订:原「准确、完整」措辞实测引发 6~13 倍于参考答案的冗长答复,收紧为要点式短答);user = question 原文(自包含,不附带分类/答案等任何线索)
- ThreadPoolExecutor 并发,每题独立调用 llm_client.chat;内部剥离思考内容以保证 answer 干净,思考文本不持久化
- 单题失败(重试与退避耗尽):记 `status:"error"` 与错误信息,不中断整体

### 5.3 断点续跑与写出

- 目标 RECORD 已存在则载入;仅当某 id **已存在 `status=="ok"` 且 question 原文与当前数据集一致**时跳过,否则重新提问(question 变化视为数据集已修订)
- 每完成一题,全量重写 RECORD 文件;写入采用临时文件 + `os.replace` 原子替换,防止中断损坏
- 结束时打印统计:总题数 / 新作答 / 续跑跳过 / 失败

### 5.4 RECORD 结构

数组,每条 = 原 case 全部字段(保持原字段顺序)+ 末尾追加:

```json
"model_response": {
  "answer": "剥离思考后的正式回答",
  "status": "ok | error",
  "error": null,
  "latency_ms": 12345,
  "usage": {"prompt_tokens": 0, "completion_tokens": 0},
  "model": "glm-4.6",
  "thinking_mode": "enabled"
}
```

文件名:`RECORD_<模型名>_<思考模式>_<数据集文件stem>.json`(如 `RECORD_glm-4.6_enabled_dataset_detail.json`)。

## 6. 评估模式(judge + report)

### 6.1 输入发现

按 `evaluatee_llm.model` 的模型名定位 `report/<模型名>/` 目录,扫描其中 `RECORD_*.json`。文件名解析用正则 `^RECORD_(.+)_(enabled|disabled)_(dataset.*)\.json$`(思考模式取值固定、数据集 stem 必以 `dataset` 开头,两者作为锚点消除模型名含下划线的歧义),解出模型名、思考模式、数据集 stem(stem = 原数据集文件名去掉 `.json` 后缀),逐个文件评估。

### 6.2 裁判调用(每题一次)

输入:题目、参考答案、评分点列表、被评测回答。temperature=0。评分中立性:回答简洁或详细本身不影响评分,判定只看要点是否被正确覆盖(仅提及关键词但表述错误或含糊其辞不算命中);总分与要点命中情况一致:5=全部命中且无错误,4=大部分命中,3=约半数命中,2=掌握较差,1=基本未掌握,含严重概念错误时下调一档。作答失败(status 为 error)的条目不调用裁判,直接记 score:null 与「作答失败,未评分」评语。要求只输出 JSON:

```json
{
  "point_results": [
    {"point": "<评分点原文>", "hit": true, "comment": "一句判定依据"}
  ],
  "score": 4,
  "comment": "总体评价"
}
```

- 结构化解析复用参考实现的多策略提取(直接解析 → ```json 代码块从后往前 → 平衡括号)
- 解析失败或 score 不在 1-5:重试一次,仍失败记 `score: null`、`parse_error` 及原始响应截断,继续后续题目
- 评估同样并发 + 断点:EVALUATION 文件已存在且某 id 已有 `score != null` 且 question 一致则跳过;每题完成原子重写

### 6.3 EVALUATION 结构与文件名

每条 = RECORD 对应条目 + 末尾追加:

```json
"evaluation": {
  "judge_model": "glm-4.6",
  "point_results": [{"point": "...", "hit": true, "comment": "..."}],
  "score": 4,
  "comment": "..."
}
```

文件名:`EVALUATION_<裁判模型>_<被评测模型>_<思考模式>_<数据集stem>.json`(如 `EVALUATION_glm-4.6_glm-4.6_enabled_dataset_detail.json`)。

## 7. summary.md(report.py)

文件:`report/<被评测模型名>/EVALUATION_<裁判模型>_<被评测模型>_<思考模式>_summary.md`。生成方式:评估模式处理完全部 RECORD 后,扫描该目录下由本次裁判模型产出的 `EVALUATION_<裁判模型>_<被评测模型>_*` 文件,按思考模式分组,**每个思考模式生成一份 summary**,内容汇总该模式下的全部 EVALUATION 文件(多数据集合并),结构:

1. **总览**:各数据集题数、平均分、1-5 分分布、作答失败/评分失败计数
2. **六维均分表**:按 difficulty、category.scope、category.protocol_layer、category.lifecycle、scenario、device_type 分组平均分(每个数据集一节 + 全部合并)
3. **评分点命中率**:全部评分点按命中率排序;命中率 < 50% 的列为「知识缺口清单」(附题目 id 与维度)
4. **低分题清单**:score ≤ 2 的题目 id、维度、裁判评语摘要
5. **分析结论**:将上述统计表与低分/缺口清单作为输入,调用裁判 LLM 生成一段结构化结论(优势维度、薄弱维度、知识缺口归因、改进建议),程序拼接写入

统计全部由程序计算(不依赖 LLM),仅结论段由裁判生成(每份 summary 一次调用)。score 为 null 或 status 为 error 的题目不计入均分,单独计数披露。

## 8. 错误处理

| 场景 | 行为 |
|---|---|
| 配置缺失/非法 | 启动报错,非零退出 |
| benchmark 文件校验失败 | 跳过该文件,打印定位,继续其他文件 |
| 单题调用失败(重试耗尽) | RECORD 记 error,继续 |
| 裁判解析失败(重试一次仍败) | evaluation 记 null 分,继续 |
| 目标目录无 RECORD / 无合法数据集 | 明确报错退出 |
| RECORD/EVALUATION 写入 | 临时文件 + os.replace 原子替换 |

## 9. 测试(pytest,LLM 全 mock)

- config:合法加载、各非法配置报错
- benchmark:合法样例通过;缺字段/类型错/id 重复的样例分别给出定位信息
- runner:断点续跑(已有 ok 且 question 一致→跳过;question 变化→重问);error 记录不中断;RECORD 字段完整
- judge:多策略 JSON 解析(纯 JSON/代码块/包裹文本)、非法 score 触发重试与 null 记录
- report:均分/分布/六维统计/命中率排行/缺口清单的计算正确性(构造小数据)
- llm_client:thinking 注入按 provider 策略生效、退避重试、`${ENV}` key 解析(mock HTTP)

## 10. 交付物清单

- `llm_eval/` 全部代码与测试
- `llm_eval/config.example.json`
- README(简):安装(requests)、两种模式配置与运行示例、输出文件说明
