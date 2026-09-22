import json

import pytest

from evaluator.config import AppConfig, ConfigError, load_config

VALID = {
    "mode": "execute",
    "benchmark_dir": "../benchmark",
    "report_dir": "../report",
    "evaluatee_llm": {
        "provider": "GLM", "api_url": "https://x/v1", "api_key": "sk-1",
        "model": "glm-4.6", "thinking": {"mode": "enabled"},
    },
    "judge_llm": {
        "provider": "DeepSeek", "api_url": "https://y/v1", "api_key": "sk-2",
        "model": "deepseek-chat", "thinking": {"mode": "disabled"},
    },
    "concurrency": 4, "max_retries": 2, "temperature": 0.1,
}


def _write(tmp_path, cfg):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p


def test_load_valid_execute(tmp_path):
    cfg = load_config(_write(tmp_path, VALID))
    assert isinstance(cfg, AppConfig)
    assert cfg.mode == "execute"
    assert cfg.evaluatee_llm.thinking_mode == "enabled"
    assert cfg.judge_llm.thinking_mode == "disabled"
    # 相对路径相对配置文件目录解析
    assert cfg.benchmark_dir == (tmp_path / "../benchmark").resolve()
    assert cfg.report_dir == (tmp_path / "../report").resolve()


def test_defaults_applied(tmp_path):
    cfg = dict(VALID)
    for k in ("concurrency", "max_retries", "temperature"):
        cfg.pop(k)
    c = load_config(_write(tmp_path, cfg))
    assert (c.concurrency, c.max_retries, c.temperature) == (4, 2, 0.1)


@pytest.mark.parametrize("mutate", [
    lambda c: c.pop("mode"),
    lambda c: c.update(mode="run"),
    lambda c: c.pop("evaluatee_llm"),
    lambda c: c.pop("judge_llm"),
    lambda c: c["evaluatee_llm"].update(api_key=""),
    lambda c: c["evaluatee_llm"].update(model=""),
    lambda c: c["evaluatee_llm"]["thinking"].update(mode="adaptive"),
    lambda c: c.update(concurrency=0),
    lambda c: c.update(concurrency="four"),
    lambda c: c.update(temperature="x"),
])
def test_invalid_config_raises(tmp_path, mutate):
    cfg = json.loads(json.dumps(VALID))
    mutate(cfg)
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, cfg))


def test_evaluate_mode_needs_judge_complete_and_model_name(tmp_path):
    cfg = json.loads(json.dumps(VALID))
    cfg["mode"] = "evaluate"
    cfg["judge_llm"].update(api_key="")
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, cfg))
    # evaluate 模式下 evaluatee 只需 model 名(用于目录定位)
    cfg2 = json.loads(json.dumps(VALID))
    cfg2["mode"] = "evaluate"
    cfg2["evaluatee_llm"].update(api_url="", api_key="")
    c = load_config(_write(tmp_path, cfg2))
    assert c.mode == "evaluate"
