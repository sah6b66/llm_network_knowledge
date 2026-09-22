import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]      # d:\network_knowledge_set
MAIN = Path(__file__).resolve().parents[1] / "main.py"


def _run(args):
    return subprocess.run([sys.executable, str(MAIN), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          cwd=ROOT)


def test_missing_config_fails():
    r = _run(["--config", "llm_eval/tests/_no_such.json"])
    assert r.returncode == 2
    assert "配置" in (r.stderr + r.stdout)


def test_execute_mode_end_to_end_with_stub_server(tmp_path):
    """端到端冒烟:本地起一个 OpenAI 兼容 stub HTTP 服务,跑 execute 再跑 evaluate。"""
    import http.server
    import threading

    calls = {"execute": 0, "judge": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            if self.headers.get("Authorization") == "Bearer sk-judge":
                calls["judge"] += 1
                body = {"choices": [{"message": {"content": json.dumps({
                    "point_results": [{"point": "要点", "hit": True, "comment": "ok"}],
                    "score": 4, "comment": "总评"})}}]}
            else:
                calls["execute"] += 1
                body = {"choices": [{"message": {"content": "模型回答"}}]}
            data = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"

    bench = tmp_path / "benchmark"
    bench.mkdir()
    (bench / "dataset_smoke.json").write_text(json.dumps([{
        "id": 1, "difficulty": "简单",
        "category": {"scope": "网络", "protocol_layer": "IP层", "lifecycle": "维护"},
        "scenario": "通用", "device_type": "不限定",
        "question": "冒烟问题?", "answer": "冒烟参考答案",
        "scoring_points": ["要点"], "tags": []}], ensure_ascii=False),
        encoding="utf-8")

    for mode, key in (("execute", "sk-eval"), ("evaluate", "sk-judge")):
        cfg = {"mode": mode, "benchmark_dir": str(bench),
               "report_dir": str(tmp_path / "report"),
               "evaluatee_llm": {"provider": "GLM", "api_url": url,
                                 "api_key": "sk-eval", "model": "smoke-model",
                                 "timeout": 10, "thinking": {"mode": "enabled"}},
               "judge_llm": {"provider": "GLM", "api_url": url,
                             "api_key": "sk-judge", "model": "judge-model",
                             "timeout": 10, "thinking": {"mode": "disabled"}},
               "concurrency": 2, "max_retries": 0, "temperature": 0.1}
        p = tmp_path / f"config_{mode}.json"
        p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        r = _run(["--config", str(p)])
        assert r.returncode == 0, r.stdout + r.stderr

    # 1 次逐题评分 + 1 次 summary 结论生成(run_summaries 复用裁判 client)
    assert calls["execute"] == 1 and calls["judge"] == 2
    rp = tmp_path / "report" / "smoke-model"
    record = rp / "RECORD_smoke-model_enabled_dataset_smoke.json"
    evaluation = rp / "EVALUATION_judge-model_smoke-model_enabled_dataset_smoke.json"
    summary = rp / "EVALUATION_judge-model_smoke-model_enabled_summary.md"
    assert record.exists() and evaluation.exists() and summary.exists()
    ev = json.loads(evaluation.read_text(encoding="utf-8"))
    assert ev[0]["evaluation"]["score"] == 4
    srv.shutdown()
