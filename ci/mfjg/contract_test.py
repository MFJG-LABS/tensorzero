"""Exercise a disposable gateway using only the synthetic provider network."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from synthetic_provider import FUNCTIONS


def get(url):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def wait_ready(url):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except HTTPError as error:
            error.close()
        except (URLError, TimeoutError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"synthetic service never became ready: {url}")


def request(function, **extra):
    before = len(get("http://provider:8080/attempts"))
    body = {
        "model": f"tensorzero::function_name::{function}",
        "messages": [{"role": "user", "content": "synthetic parity check"}],
        **extra,
    }
    with urlopen(
        Request(
            "http://gateway:3000/openai/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        ),
        timeout=15,
    ) as response:
        raw = response.read().decode()
    attempts = get("http://provider:8080/attempts")[before:]
    expected = [f"{function}-fail-{i}" for i in range(FUNCTIONS[function] - 1)] + [f"{function}-ok"]
    if attempts != expected:
        raise AssertionError(f"fallback evidence mismatch: {function}: {attempts!r} != {expected!r}")
    return raw


def run():
    wait_ready("http://provider:8080/health")
    wait_ready("http://gateway:3000/health")
    checks = []
    for function in FUNCTIONS:
        plain = json.loads(request(function))
        assert plain["choices"][0]["message"]["content"] == "synthetic-ok", plain
        assert plain["usage"]["total_tokens"] == 5, plain
        checks.append(f"{function}:chat:fallback:usage")
        raw = request(function, stream=True, stream_options={"include_usage": True})
        events = [line[6:] for line in raw.splitlines() if line.startswith("data: ")]
        assert events[-1] == "[DONE]", events
        chunks = [json.loads(event) for event in events[:-1]]
        text = "".join(
            choice["delta"].get("content", "") or "" for chunk in chunks for choice in chunk.get("choices", [])
        )
        assert text == "synthetic-ok", chunks
        assert any((chunk.get("usage") or {}).get("total_tokens") == 5 for chunk in chunks), chunks
        checks.append(f"{function}:stream:fallback:usage")
    tool = json.loads(
        request(
            "mechanical",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Synthetic test only",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                    },
                }
            ],
            tool_choice="required",
        )
    )
    call = tool["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == "lookup", tool
    assert json.loads(call["function"]["arguments"]) == {"path": "README.md"}, tool
    checks.append("mechanical:tool_call")
    structured = json.loads(request("mechanical", response_format={"type": "json_object"}))
    assert json.loads(structured["choices"][0]["message"]["content"]) == {"ok": True}, structured
    checks.append("mechanical:json")
    print(
        json.dumps(
            {
                "schema": "mfjg.synthetic-gateway-parity.v1",
                "passed": True,
                "checks": checks,
                "provider_requests": len(get("http://provider:8080/attempts")),
                "cloud_requests": 0,
                "database_migrations": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    run()
