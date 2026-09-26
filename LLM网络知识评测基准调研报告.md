# LLM 网络知识评测基准调研报告

> 范围:可用于评估大模型掌握 IP 网络(数据通信)知识程度的公开基准,共 17 项核心基准 + 相邻领域若干;信息截至 2026-09。

---

## 1. 基准总览

按评估形态分为四大类:**静态知识问答**(纯文本题目)、**结构化理解**(拓扑/状态机等结构重建)、**生成可验证**(生成配置或代码并机器验证)、**可执行智能体**(仿真环境闭环交互)。

| 基准 | 机构 | 发布 | 最新更新 | 类型 | 规模 | 评估方式 |
|---|---|---|---|---|---|---|
| TeleQnA | 华为巴黎研究中心 NetOp 团队 | 2024-02 | 2025-06(HF 卡) | 静态问答 | 10,000 道选择题 | 选择题判分 |
| NetEval | NASP | 2023 | 2023-09 | 静态问答 | 5,269 道选择题 | 选择题判分 |
| NetBench(NetoAI) | NetoAISolutions | 2025-12 | 2025-12 | 静态问答 | 1K–10K 专家级问答对,20 类目 | 问答判分(受控访问) |
| LLM-Network-Eval | UIUC | 2025(ACM) | 2025-09 | 静态问答 | Coursera/CCNA 来源选择题集 | 判分 + 误解模式分析 |
| CCNA 考试研究 | 昆士兰大学 | 2026-03 | 2026-03 | 静态问答 | CCNA 题库 7 大类 + CTF 实操 | 考试通过性 vs 深层理解对比 |
| TSNBench | DTU TSN 团队 | 2026 | 2026 | 静态问答(TSN 专项) | 939 道专家校验 MCQ + 100 道 WCD 计算题 | 选择题 + 数值计算判分 |
| OpsEval | AIOps 领域 | 2023-10 | 2023 | 静态问答(AIOps,相邻) | 7,334 MCQ + 1,736 问答 | 判分 |
| PSMBench | Shen 等 | NeurIPS 2025 | 2025 | 结构化理解 | 1,580 页 RFC 文本,108 状态,297 迁移边 | 状态机图结构 F1 |
| LLM-SysAdmin(VSA) | 帕多瓦大学 | LCN 2024 | 2024-07 | 结构化理解(拓扑) | 多规模 NetJSON 拓扑 × 多任务 | 拓扑问答准确率(最佳 79.3%) |
| NetConfEval | Red Hat Research + Sapienza | CoNEXT 2024 | 2025-03 | 生成可验证 | 4 类实验,多场景(Cisco/Juniper) | 规约/函数调用/路由算法/配置生成 |
| NeMoEval | 微软等 | HotNets 2023 | 2023-10 | 生成可验证 | 2 类应用(查询 QA + 网络算法代码) | 生成代码功能正确性(GPT-4 达 88%) |
| p4benchmarks | p4llms | 2025-02 | 2025-02 | 生成可验证(P4 编程) | 2 个数据集(benchmarks + 训练集) | P4 程序判分 |
| NetConfArena | 清华大学 | 2026-08 | 2026-08 | 可执行智能体(配置) | 96 协议模板→480 任务;416 评分组/1109 检查;3840 轨迹 | GNS3 仿真,隐藏测试用例 + 确定性谓词 |
| NetConfBench | IETF NMRG | 2025(草案 -02) | 2025–2026 | 可执行智能体(配置) | 40 任务(BGP/OSPF、QoS、ACL) | 三层指标:Testcase/Command/Reasoning |
| NetPress / NetArena | 微软研究院 + 马里兰大学 | 2025-06 / ICLR 2026 | 2026-07 | 可执行智能体(云网运维) | 3 类应用(Mininet 路由/容量规划/K8s),任务动态生成 | 仿真器执行,Correctness/Safety/Latency |
| NIKA | 都灵理工 SANDS Lab | 2025-12 | 2025-12 | 可执行智能体(排错) | 数百个网络事故,54 种故障,5–6 类场景;900+ 轨迹 | Kathará + MCP,根因/修复/效率多指标 |
| FaulT-Bench | NIKA 同团队 | 2026-08 | 2026-08 | 可执行智能体(排错,抗误导) | 200 场景、8 种拓扑(不可靠工单) | Kathará 部署 + LLM 裁判 |

---

## 2. 静态知识问答类

纯文本题目、离线批量可跑、成本低,适合快速横向比较模型的网络知识储备;共同局限是可被题库泄露与"猜选项"影响,且高分不等于会动手。

### 2.1 TeleQnA —— 电信领域规模标杆

- **来源**:arXiv 2024-02;GitHub `netop-team/TeleQnA`(82★),HF `netop/TeleQnA`
- **场景**:电信领域 LLM 知识评测,题目取自 3GPP 规范、电信术语与研究趋势
- **题型样例**:题干 + 四选一,如"3GPP TS 38.xxx 中某参数的取值含义"
- **规模**:10,000 道选择题(该方向最大规模)
- **优缺点**:✔ 规模大、影响广,衍生生态丰富(TelecomGPT、处理版子集等);✘ 侧重 3GPP/移动通信,IP 数据网(路由/交换)占比低

### 2.2 NetEval —— NetOps 评测套件

- **来源**:HF `NASP/neteval-exam`;论文《An Empirical Study of NetOps Capability of Pre-Trained Large Language Models》(Miao 等)
- **场景**:网络运维(NetOps)知识面评测
- **题型/规模**:5,269 道多选题
- **优缺点**:✔ 纯网络运维方向规模最大之一,免费下载;✘ 2023-09 后未更新;选择题形态

### 2.3 NetBench(NetoAI)—— 网络 SME 专家级问答

- **来源**:HF `NetoAISolutions/NetBench`(MIT,受控访问),2025-12
- **场景**:评测 LLM 能否达到网络**领域专家(SME)智能水平**,覆盖 20 个电信与网络工程类目(设备访问、VLAN、STP、LAG、二层安全、路由等)
- **题型/规模**:专家级开放问答对(非选择题),1K–10K 条
- **优缺点**:✔ 开放问答形态、类目体系完整、较新;✘ 访问受控、社区验证少、英文、无逐评分点机制

### 2.4 LLM-Network-Eval —— 误解分析型问答

- **来源**:ACM 2025(doi:10.1145/3717512.3717515);GitHub `mudbri/LLM-Network-Eval`
- **场景**:网络课程/认证风格选择题评测,重点在**暴露并归类模型的典型误解**,可用于构造微调数据
- **题型样例**:Coursera 网络课程与 CCNA 学习资源的选择题,逐题判分后做错误模式分析
- **规模**:多文件选择题集;已评测 GPT-3.5/4、Claude 3 Opus、Llama-3.1-70B、Gemma-2 等
- **优缺点**:✔ "误解类型学"视角对纠偏有直接价值,开源可复现;✘ 题量有限、无厂商设备/RFC 专项,选择题区分度上限低

### 2.5 CCNA 考试研究 —— "考得过 ≠ 懂网络"

- **来源**:Computer Networks 282(2026-03)112236,昆士兰大学
- **场景**:以 CCNA 认证考题为载体,量化"考试分数"与"真实理解"的差距
- **题型样例**:CCNA 题库 7 大类选择题 + **CTF 实操挑战**(真正动手解题)
- **主要发现**:开源与闭源模型普遍能通过 CCNA 考试,但在深层理解题与 CTF 实操上明显掉分
- **优缺点**:✔ 对"以认证题库选人/验收"有强解释力,双轨设计直接量化纸面/动手断层;✘ 题目与环境未开源;仅覆盖 CCNA 大纲(入门、偏思科)

### 2.6 TSNBench —— 时间敏感网络专项

- **来源**:arXiv:2606.27237,Debnath、Craciunas、Pop 等
- **场景**:评估 LLM 对 TSN(工业实时网络)的掌握,安全关键领域
- **题型样例**:939 道专家校验选择题 + 100 道**最坏时延(WCD)开放式计算题**(CBS/CQF 调度)
- **主要发现**:LLM 在安全关键 TSN 域存在"危险的过度自信与计算能力缺陷"
- **优缺点**:✔ 选择题之外引入数值计算题,直击参数级能力;✘ 领域窄,与通用数据网评测互补性大于替代性

### 2.7 OpsEval(AIOps,相邻领域)

- **来源**:arXiv 2023-10(2310.07637)
- **场景/规模**:AIOps 任务基准,7,334 道选择题 + 1,736 道问答,评测 24 个 LLM;网络运维混在更广的 IT 运维任务中
- **核心结论**:通用 NLP 指标在运维领域会误导,需要领域专属评测

### 2.8 相邻领域一览

| 基准 | 简介 |
|---|---|
| NetBench(流量,arXiv:2403.10319) | 面向网络流量基础模型的大规模流量数据集,属"流量理解"而非知识问答 |
| RoutingBench(arXiv:2609.22844) | 智能体路由分析能否扩展到生产级数据中心网络(2026-09 新作,详见 §5.6) |
| MMLU-Computer Security | 少量网络安全选择题,覆盖浅,不适合网络工程评测 |
| 自建 MCQA 题库 | 大量论文自建路由/交换/安全选择题(BGP、EVPN、VXLAN、MPLS),无统一官方发布;轻量但易被背题 |

---

## 3. 结构化理解类

要求模型把网络知识重建为**形式化结构**,比选择题更深地考察"是否真的理解"。

### 3.1 PSMBench —— RFC 协议状态机抽取

- **来源**:NeurIPS 2025 Datasets & Benchmarks Track;数据集 RFC2PSM
- **场景**:输入 RFC 原文,让 LLM 输出**协议状态机**(状态、事件、迁移边),直接服务于协议实现与验证
- **规模**:1,580 页清洗后的 RFC 文本;108 个人工校验状态、297 条迁移边;覆盖链路层到应用层多种协议(TCP、BGP 等)
- **评估**:输出状态迁移图与金标图做结构比对(F1)
- **主要发现**:LLM 容易记住孤立状态,难以正确推导完整迁移逻辑
- **优缺点**:✔ 把 RFC 理解从"答知识点"升级为"重建形式化模型",NeurIPS 正式发表、开源;✘ 静态任务;协议数量有限,不含 2021–2025 新 RFC 覆盖设计

### 3.2 LLM-SysAdmin(VSA)—— 拓扑理解问答

- **来源**:IEEE LCN 2024(arXiv:2404.12689),帕多瓦大学;GitHub `spritz-group/LLM-SysAdmin`
- **场景**:给模型一张网络拓扑(NetJSON)并就拓扑提问,检验"看图理解网络"能力
- **题型样例**:给定拓扑后回答节点可达性、路径、设备角色等问题
- **规模**:多个不同规模(小/中/复杂)拓扑 × 多任务;评测 GPT-4、Llama2 等
- **主要发现**:最佳模型平均准确率 79.3%;私有模型在中小拓扑表现好,复杂拓扑理解仍是短板;提示工程可提升部分任务
- **优缺点**:✔ 首个系统研究拓扑理解的工作,数据与提示词全开源;✘ 规模小、社区活跃度低、2024-07 后未更新

---

## 4. 生成可验证类

模型生成配置/代码/规约,由机器验证正确性——任务静态可复现、结果可判定,是"知识"与"动手"之间的折中形态。

### 4.1 NetConfEval —— 配置生成事实标准

- **来源**:ACM CoNEXT 2024(doi:10.1145/3656296),Red Hat Research + Sapienza 罗马大学;GitHub `RedHatResearch/conext24-NetConfEval`(43★),HF 数据集;被引 200+
- **场景**:意图驱动网络配置(IBN)——把运营商高层需求转化为可下发的设备配置
- **题型(4 类实验)与样例**:
  1. 高层需求 → 形式化规约:转成含 reachability/waypoint/load-balancing 三类策略的数据结构
  2. 高层需求 → 函数/API 调用:生成 `add_reachability()`、`add_waypoint()`、`add_load_balance()` 并行函数调用(SDN 控制器场景,支持原生与 ad-hoc function calling)
  3. 路由算法开发:编写满足最短路径/可达/路径点/负载均衡的路由计算函数
  4. 底层配置生成:生成 Cisco IOS / Juniper Junos 风格配置(Docker 验证)
- **规模**:多场景参数化需求集,建议每实验 5 轮取统计;内置 GPT-4-Turbo 等配置,支持 OpenAI 与 HF 模型
- **优缺点**:✔ 任务分层清晰,能定位模型在配置流水线哪一环失能;学术影响最大、复现完善;✘ 英文与欧美厂商为中心,无华为 VRP;不考察协议原理知识;2025-03 后未更新

### 4.2 NeMoEval —— 网管代码生成

- **来源**:ACM HotNets 2023(arXiv:2310.06062),微软等
- **场景**:让 LLM 为网络管理任务生成可执行代码,把"网管问答"转化为"网管编程"
- **题型样例**:(1) 查询生成/问答(网络状态自然语言查询);(2) 网络算法代码生成(基于 NetworkX 的流量分析)
- **结果**:GPT-4 在 NetworkX 代码生成上达 88% 功能正确率
- **优缺点**:✔ 最早引入"生成代码+功能验证"的工作之一,影响后续 NetConfEval/NetArena;✘ 规模小(两个应用),仅覆盖可用 Python 表达的任务

### 4.3 p4benchmarks —— P4 数据面编程

- **来源**:HF `p4llms/p4benchmarks` 与 `p4dataset`(2025-02)
- **场景**:评测 LLM 编写 **P4**(SDN 数据面编程语言)程序的能力
- **优缺点**:✔ 填补"可编程数据面"独特子域;✘ 属编程任务,社区规模小

---

## 5. 可执行智能体类

Agent 在仿真环境中闭环交互(观察状态→下发命令→查看回显→迭代),以**业务最终是否达成**为主指标——最贴近真实运维,且动态出题免疫题库泄露。当前两大仿真底座:**GNS3**(NetConfBench、NetConfArena)与 **Kathará**(NIKA、FaulT-Bench);Mininet/K8s(NetArena)偏云网。

### 5.1 NetConfArena —— 配置 Agent(任务量与协议覆盖最佳)

- **来源**:arXiv:2608.23179(2026-08),清华大学;GitHub `liujona/NetConfArena`
- **场景**:GNS3 仿真的多设备闭环配置——每个任务给出拓扑 + 启动配置 + 运维语言描述的目标,Agent 通过五动作接口下发厂商 CLI、观察设备回显、迭代达标
- **任务覆盖**:96 个协议向模板——静态路由、RIP、OSPF、BGP、MPLS(LDP/TE/L3VPN 含 MPLS over GRE、L2VPN)、IP overlay(L2TPv3/GRE/DMVPN/IPsec);参数化实例化(设备名/接口/IP 种子随机渲染)→ **480 个任务实例**
- **判分**:既非文本比对也非 LLM 裁判——**隐藏测试用例**在仿真设备上执行诊断命令,以**确定性谓词**判定网络行为;共 416 评分组 / 1109 个可执行检查;轨迹记录支持过程级分析(规划、错误恢复、失败模式聚类),已采集 3840 条轨迹
- **工程特性**:ReAct / OneShot 双脚手架;提供 **MCP server**,第三方 Agent 框架可直接接入
- **优缺点**:✔ 隐藏测试用例 + 参数化实例化双重防背题;数据中心协议族覆盖好;判分确定可复现;✘ 2026-08 新发布,第三方复现少;依赖 GNS3 + 厂商镜像;无中文/华为场景

### 5.2 NetConfBench —— IETF 标准化框架

- **来源**:IETF NMRG Internet-Draft **draft-cui-nmrg-llm-benchmark**《A Framework to Evaluate LLM Agents for Network Configuration》(-00/-01/-02 多版本,IETF 125 汇报)
- **场景**:意图驱动配置 Agent 的可复现、公平评测,面向横向比较不同 LLM 网络配置 Agent
- **底座与规模**:GNS3;40 个任务,覆盖路由(BGP/OSPF)、QoS、ACL 安全
- **三层指标**:
  1. **Testcase score**(主指标)——仿真中执行测试,验证业务最终是否达成
  2. **Command score**——生成命令的语法与语义正确性
  3. **Reasoning score**——Agent 思考过程/推理链路质量
- **任务模式**:单轮 LLM 与 ReAct 多轮 Agent 均支持;Agent 可查询拓扑、查看 running-config、下发配置
- **优缺点**:✔ IETF 标准化背书,指标分层清晰,适合作为自建评测的方法论模板与报告引用锚点;✘ 草案仍在演进(非 RFC),任务规模较小,参考实现成熟度一般

### 5.3 NetPress / NetArena —— 云网运维 Agent

- **来源**:arXiv:2506.03231(2025-06,WCNC)→ ICLR 2026(NetArena);微软研究院 + 马里兰大学;GitHub `Froot-NetSys/NetArena`(45★),排行榜 netarena.ai
- **场景**:LLM 智能体在真实网络自动化任务中的表现,三类应用:Routing(Mininet 路由)、Capacity Planning/MALT(容量规划)、Kubernetes(KIND 集群容器网络)
- **题型样例**:给 Agent 一个网络环境与自然语言目标,多轮交互(查看状态→下发配置→观察反馈),系统在仿真器中实际执行
- **指标**:三维度——Correctness(方案正确)、**Safety**(不违反安全约束)、Latency(响应时间),附置信区间统计
- **优缺点**:✔ 动态生成免疫题库泄露,考"会不会做";安全维度入指标;工程完成度最高(Docker/排行榜/持续维护至 2026-07);✘ 部署重(仿真环境+GPU);测的是"Agent+工具链"综合能力而非模型知识本身;偏数据中心/云网

### 5.4 NIKA —— 排错 Agent(最大公开事故诊断基准)

- **来源**:arXiv:2512.16381(2025-12),都灵理工 SANDS Lab;项目页 sands-lab.github.io/nika,GitHub `sands-lab/nika`,Zenodo 发布 900+ 条排错轨迹
- **场景**:**网络故障排查智能体**——给 Agent 一张故障工单,登录设备、执行 show 命令、逐步探查定位根因
- **底座与规模**:Kathará 沙箱 + **MCP 工具接口**;数百个精选网络事故、54 种典型故障,覆盖数据中心、园区网、ISP 骨干、SDN fabric、overlay、K8s CNI 等 5–6 类场景
- **指标**:根因定位准确率、修复成功率、探查效率(命令条数)
- **生态**:衍生 Agent 研究已出现(SADE 相位门控诊断流,留出集根因 F1 0.77);FaulT-Bench 为其扩展
- **优缺点**:✔ 排错方向最系统,真实运维形态(工单+登机+show),开源完整(代码/数据/轨迹);✘ Kathará+MCP 部署有门槛;以通用协议/开源镜像为主,无厂商私有生态

### 5.5 FaulT-Bench —— 不可靠工单下的抗误导排错

- **来源**:arXiv:2608.27021(2026-08),NIKA 同团队
- **动机**:多数基准假设故障工单描述完全准确;现实报障人常给错误、虚假或模糊信息,易诱导 Agent 过度诊断
- **规模与机制**:200 个场景、8 种拓扑;自动化 harness 在 Kathará 中部署,Agent 经 NIKA 工具接口交互,自由文本诊断由 LLM 裁判评分
- **优缺点**:✔ 切中真实运维痛点(噪音工单),与 NIKA 基础设施复用;✘ 极新、复现少;LLM 裁判引入一定主观性

### 5.6 RoutingBench —— 生产网路由分析(新作)

- **来源**:arXiv:2609.22844(2026-09)
- **场景**:检验智能体路由分析能否扩展到生产级数据中心网络

---

## 6. 横向对比与选型建议

### 6.1 形态谱系

```
知识掌握深度 ──────────────────────────────► 动手能力
├─ 静态问答:TeleQnA、NetEval、NetBench、LLM-Network-Eval、CCNA 研究、TSNBench、OpsEval
├─ 结构化理解:PSMBench(RFC 状态机)、LLM-SysAdmin(拓扑)
├─ 生成可验证:NetConfEval、NeMoEval、p4benchmarks
└─ 可执行 Agent(仿真闭环):
   ├─ 配置类:NetConfArena(GNS3)、NetConfBench(GNS3/IETF)、NetArena(Mininet/K8s)
   └─ 排错类:NIKA(Kathará)、FaulT-Bench(Kathará,抗误导)
```

### 6.2 选型速查

| 需求 | 推荐 |
|---|---|
| 快速比较模型网络知识(离线批量) | TeleQnA(大而偏电信)、NetEval(纯 NetOps)、NetBench(专家问答)、TSNBench(TSN) |
| RFC 深度理解 | PSMBench(状态机重建) |
| 拓扑理解 | LLM-SysAdmin |
| 配置生成(单轮) | NetConfEval(事实标准) |
| 配置 Agent(闭环) | NetConfArena(任务量/协议覆盖最佳)、NetConfBench(IETF 框架,写报告引用)、NetArena(工程最成熟,偏云网) |
| 排错 Agent | NIKA(最系统)、FaulT-Bench(抗误导) |
| 证明"纸面分 ≠ 能运维" | CCNA 研究(2026)、NIKA/NetConfArena 失败模式分析 |

**核心提醒**:静态问答分数高 ≠ Agent 能做网络运维——多项研究(CCNA 2026、NIKA、NetConfArena)一致表明,选择题答对的模型放进仿真环境仍会下发错误配置、无法根据 show 输出修正,这正是评测重心转向可执行 Agent 基准的原因。

### 6.3 与本项目(llm_eval)的对照

本项目是**中文、开放问答 + LLM 裁判逐评分点打分(1–5 分)**的评测引擎:400 题通用数据集(basic/detail 双难度)+ 华为设备专项(100 题,绑定型号与版本)+ RFC 专项(2021–2025 年 50 篇 RFC,100 题)。

| 维度 | 公开基准 | 本项目 |
|---|---|---|
| 语言 | 几乎全英文 | **中文**(空白) |
| 题型 | 以选择题为主 | 开放问答 + 评分点判定(与"选择题高估能力"的研究结论互补) |
| 厂商覆盖 | Cisco/Juniper | **华为 VRP**(CE/S/NetEngine/AR/USG/AirEngine,含命令、告警 OID、日志)——全部 17 项基准均未覆盖 |
| 标准时效 | 无 RFC 专项 | **RFC 2021–2025 专项**;已评测各模型 rfc 数据集平均分普遍最低,印证缺口真实 |
| 打分方式 | 选择题判分 / 执行判分 | LLM-as-Judge 逐评分点 |

可借鉴的演进方向:
1. **防泄露**:参数化动态出题 + 隐藏测试用例(NetArena、NetConfArena)
2. **可执行验证**:引入 GNS3/EVE-NG/华为 eNSP 仿真执行,从"答得对"升级到"配得对";判分参考 NetConfBench 三层指标与 NetConfArena 确定性谓词
3. **误解分析**:LLM-Network-Eval 的错误模式归类,补强"知识缺口归因"
4. **RFC 深度**:借鉴 PSMBench 增加"协议状态机重建"类结构化题型
5. **排错方向**:借鉴 NIKA/FaulT-Bench 构建华为设备故障工单排错评测(含不可靠工单)
6. **标准化与接口**:跟踪 IETF NMRG 草案;若做 Agent 评测,提供 MCP 接口与业界对齐

---

## 7. 趋势观察(2023 → 2026)

1. **形态演进**:静态问答(2023–2024)→ 代码生成+功能验证(2023 HotNets / 2024 CoNEXT)→ 仿真闭环智能体(2025 NetPress/NIKA → 2026 NetConfArena/FaulT-Bench);2025–2026 新增**排错方向**与**抗误导鲁棒性**(不可靠工单)
2. **动态化防泄露**:参数化模板动态生成(NetArena、NetConfArena)叠加隐藏测试用例,应对基准污染
3. **判分从"看文本"到"看行为"**:NetConfBench 三层指标、NetConfArena 确定性谓词、NIKA 根因/修复/效率多指标——均以仿真内实际业务结果为主指标
4. **安全维度入指标**:NetArena 将 Safety 与 Correctness 并列,反映生产化诉求
5. **标准化成型**:IETF NMRG 草案(draft-cui-nmrg-llm-benchmark)多版本迭代并会议汇报,行业共识形成中
6. **工具接口协议化**:MCP 成为 Agent-仿真交互的事实接口(NetConfArena、NIKA 均提供 MCP server)
7. **空白仍在**:华为等中国厂商设备知识与中文网络知识评测在全部公开基准(含 Hugging Face)中均属空白——即本项目的差异化定位

---

## 8. 参考链接

### 静态问答类

- TeleQnA: https://github.com/netop-team/TeleQnA | https://huggingface.co/datasets/netop/TeleQnA
- NetEval: https://huggingface.co/datasets/NASP/neteval-exam
- NetBench(NetoAI): https://huggingface.co/datasets/NetoAISolutions/NetBench
- LLM-Network-Eval: https://dl.acm.org/doi/abs/10.1145/3717512.3717515 | https://github.com/mudbri/LLM-Network-Eval
- CCNA 考试研究: https://www.sciencedirect.com/science/article/pii/S1389128626002483 (Computer Networks 282, 2026)
- TSNBench: arXiv:2606.27237
- OpsEval: arXiv:2310.07637

### 结构化理解类

- PSMBench(NeurIPS 2025 D&B):数据集 RFC2PSM
- LLM-SysAdmin: https://arxiv.org/abs/2404.12689 | https://github.com/spritz-group/LLM-SysAdmin

### 生成可验证类

- NetConfEval: https://github.com/RedHatResearch/conext24-NetConfEval | https://huggingface.co/datasets/NetConfEval/NetConfEval (CoNEXT 2024, doi:10.1145/3656296)
- NeMoEval: arXiv:2310.06062 (HotNets 2023)
- p4benchmarks: https://huggingface.co/datasets/p4llms/p4benchmarks

### 可执行智能体类

- NetConfArena: https://arxiv.org/abs/2608.23179 | https://github.com/liujona/NetConfArena
- NetConfBench: https://datatracker.ietf.org/doc/draft-cui-nmrg-llm-benchmark (IETF NMRG)
- NetPress/NetArena: https://arxiv.org/pdf/2506.03231 (ICLR 2026) | https://github.com/Froot-NetSys/NetArena | https://www.netarena.ai
- NIKA: https://arxiv.org/abs/2512.16381 | https://sands-lab.github.io/nika | https://github.com/sands-lab/nika
- FaulT-Bench: arXiv:2608.27021
- RoutingBench: arXiv:2609.22844

> 说明:各基准的规模与指标以论文摘要、官方 README 或数据集卡可核验的表述为准;个别未公开精确数字的条目(NetConfBench 任务数、FaulT-Bench 场景数等)以论文/草案原文为准。
