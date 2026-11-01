"""Synthetic OpenAI provider. It has no upstream client or credential support."""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASELINE = json.loads(Path(__file__).with_name("baseline.json").read_text())
FUNCTIONS = BASELINE["function_provider_counts"]
MODELS = {
    model
    for name, count in FUNCTIONS.items()
    for model in [f"{name}-ok", *(f"{name}-fail-{i}" for i in range(count - 1))]
}
USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}


def config():
    lines = ["[gateway]", 'bind_address = "0.0.0.0:3000"', "[gateway.observability]", "enabled = false"]
    for name, count in FUNCTIONS.items():
        providers = [f"fail-{i}" for i in range(count - 1)] + ["ok"]
        lines += [f'[models."tier-{name}"]', f"routing = {json.dumps(providers)}"]
        for provider in providers:
            lines += [
                f'[models."tier-{name}".providers."{provider}"]',
                'type = "openai"',
                f'model_name = "{name}-{provider}"',
                'api_base = "http://provider:8080/v1/"',
                'api_key_location = "none"',
            ]
        lines += [
            f'[functions."{name}"]',
            'type = "chat"',
            f'[functions."{name}".variants.default]',
            'type = "chat_completion"',
            f'model = "tier-{name}"',
            "weight = 1.0",
        ]
    return "\n".join(lines) + "\n"


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts = []
        self.attempts_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"ok": True})
        elif self.path == "/attempts":
            with self.server.attempts_lock:
                attempts = list(self.server.attempts)
            self.reply(200, attempts)
        else:
            self.reply(404, {"error": "unknown synthetic endpoint"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.reply(404, {"error": "unknown synthetic endpoint"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 131072:
                raise ValueError("invalid request size")
            body = json.loads(self.rfile.read(size))
            model = body.get("model") if isinstance(body, dict) else None
            if not isinstance(model, str) or model not in MODELS:
                raise ValueError("unknown synthetic model")
        except (ValueError, TypeError):
            self.reply(400, {"error": "invalid synthetic request"})
            return
        with self.server.attempts_lock:
            self.server.attempts.append(model)
        if "-fail-" in model:
            self.reply(503, {"error": {"message": "synthetic provider unavailable", "type": "server_error"}})
            return
        message = {"role": "assistant", "content": "synthetic-ok"}
        finish = "stop"
        if body.get("tools"):
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "synthetic-call",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": '{"path":"README.md"}'},
                    }
                ],
            }
            finish = "tool_calls"
        elif body.get("response_format", {}).get("type") in {"json_object", "json_schema"}:
            message["content"] = '{"ok":true}'
        common = {"id": "chatcmpl-synthetic", "created": 1, "model": model}
        if body.get("stream"):
            chunks = [
                {
                    **common,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": message, "finish_reason": None}],
                },
                {
                    **common,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                },
                {**common, "object": "chat.completion.chunk", "choices": [], "usage": USAGE},
            ]
            raw = ("".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.reply(
                200,
                {
                    **common,
                    "object": "chat.completion",
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": USAGE,
                },
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", action="store_true")
    args = parser.parse_args()
    if args.config:
        print(config(), end="")
    else:
        Server(("0.0.0.0", 8080), Handler).serve_forever()
