# LLM 网络知识掌握度评估程序

## 安装
    pip install -r requirements.txt

## 使用
1. 复制 `config.example.json` 为 `config.json`,填写两个 LLM(被评测/裁判)的
   连接信息与 thinking.mode(enabled/disabled);自签/内网 HTTPS 端点可将
   `ssl_verify` 设为 `false`(缺省 false,跳过证书校验)
2. 执行模式(`"mode": "execute"`):逐题调用被评测 LLM,产出
   `report/<模型>/RECORD_<模型>_<思考模式>_<数据集>.json`(支持并发与断点续跑,
   中断后重跑自动跳过已完成题目)
3. 评估模式(`"mode": "evaluate"`):裁判 LLM 逐评分点打分并给 1-5 总分,产出
   `EVALUATION_<裁判>_<模型>_<思考模式>_<数据集>.json` 与
   `EVALUATION_<裁判>_<模型>_<思考模式>_summary.md`
   (summary 按数据集分别统计,不做跨数据集合并;评估同样支持断点续跑,
   作答或评分失败的题重跑对应模式会自动补齐)
4. 数据集放在 `../data/benchmark/` 下(config 中 `benchmark_dir` 所指目录),文件名以 `dataset` 开头、格式校验通过的才会执行

    python main.py --config config.json

## 测试
    python -m pytest tests/ -v
