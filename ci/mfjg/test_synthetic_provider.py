"""Tests for the credential-free provider used by the MFJG parity gate."""

import json
import threading
import tomllib
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from synthetic_provider import Handler, Server, config


class SyntheticProviderTest(unittest.TestCase):
    def setUp(self):
        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, body):
        return urlopen(
            Request(
                self.url + "/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=2,
        )

    def test_provider_records_failure_before_success(self):
        with self.assertRaises(HTTPError) as failed:
            self.post({"model": "mechanical-fail-0"})
        self.assertEqual(failed.exception.code, 503)
        failed.exception.close()
        with self.post({"model": "mechanical-ok"}) as response:
            body = json.load(response)
        self.assertEqual(body["choices"][0]["message"]["content"], "synthetic-ok")
        self.assertEqual(self.server.attempts, ["mechanical-fail-0", "mechanical-ok"])

    def test_stream_finishes_and_preserves_usage(self):
        with self.post({"model": "mechanical-ok", "stream": True}) as response:
            lines = response.read().decode().splitlines()
        events = [line[6:] for line in lines if line.startswith("data: ")]
        self.assertEqual(events[-1], "[DONE]")
        parsed = [json.loads(line) for line in events[:-1]]
        self.assertEqual(parsed[0]["choices"][0]["delta"]["content"], "synthetic-ok")
        self.assertEqual(parsed[-1]["usage"]["total_tokens"], 5)

    def test_tool_call_and_json_have_distinct_wire_shapes(self):
        with self.post(
            {"model": "mechanical-ok", "tools": [{"type": "function", "function": {"name": "lookup"}}]}
        ) as response:
            body = json.load(response)
        self.assertEqual(body["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(body["choices"][0]["message"]["tool_calls"][0]["function"]["name"], "lookup")
        with self.post({"model": "mechanical-ok", "response_format": {"type": "json_object"}}) as response:
            body = json.load(response)
        self.assertEqual(json.loads(body["choices"][0]["message"]["content"]), {"ok": True})

    def test_unknown_model_and_malformed_payload_are_refused(self):
        for body in ({"model": "cloud-model"}, [], {"model": 123}):
            with self.subTest(body=body), self.assertRaises(HTTPError) as failure:
                self.post(body)
            self.assertEqual(failure.exception.code, 400)
            failure.exception.close()

    def test_generated_config_is_secrets_free_and_reproduces_seven_routes(self):
        document = tomllib.loads(config())
        expected = json.loads(Path(__file__).with_name("baseline.json").read_text())["function_provider_counts"]
        self.assertEqual(set(document["functions"]), set(expected))
        self.assertFalse(document["gateway"]["observability"]["enabled"])
        for name, count in expected.items():
            model = document["models"][f"tier-{name}"]
            self.assertEqual(len(model["routing"]), count)
            for provider in model["providers"].values():
                self.assertEqual(provider["api_base"], "http://provider:8080/v1/")
                self.assertEqual(provider["api_key_location"], "none")


if __name__ == "__main__":
    unittest.main()
