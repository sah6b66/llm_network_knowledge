"""LLM 网络知识掌握度评估程序入口。

用法:
    python llm_eval/main.py --config llm_eval/config.json
模式(execute/evaluate)在配置文件中指定。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _main() -> int:
    parser = argparse.ArgumentParser(description="LLM 网络知识掌握度评估")
    parser.add_argument("--config", default=str(Path(__file__).parent / "config.json"))
    args = parser.parse_args()

    from evaluator.config import ConfigError, load_config
    from evaluator.llm_client import LLMClient

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"配置错误:{e}", file=sys.stderr)
        return 2

    if cfg.mode == "execute":
        from evaluator.runner import run_execute
        client = LLMClient(cfg.evaluatee_llm.__dict__, max_retries=cfg.max_retries)
        try:
            run_execute(cfg, client)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"执行失败:{e}", file=sys.stderr)
            return 2
        finally:
            client.close()
    else:
        from evaluator.judge import run_evaluate
        client = LLMClient(cfg.judge_llm.__dict__, max_retries=cfg.max_retries)
        try:
            run_evaluate(cfg, client)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"评估失败:{e}", file=sys.stderr)
            return 2
        finally:
            client.close()
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_main())
