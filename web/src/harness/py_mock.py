# Mock DeepSeek server for exercises. Installs fake `requests` and `dotenv` modules and
# sets DEEPSEEK_API_KEY, so learner code is identical to what runs against the real API.
# Behaviour is mirrored in ts_runtime.js (__ccMock). Keep the two in sync.
import json as _cc_json
import os as _cc_os
import random as _cc_random
import re as _cc_re
import sys as _cc_sys
import types as _cc_types

_CC_RULES = [
    ("unlimited", "redline", "high", "liability_cap"),
    ("any country", "redline", "high", "data_processing"),
    ("perpetuity", "redline", "medium", "confidentiality"),
    ("twenty-four", "redline", "medium", "auto_renewal"),
    ("without notice", "flag", "medium", "payment"),
    ("subject to section", "flag", "high", "liability_cap"),
]
_CC_TOPICS = [
    ("liabil", "liability_cap"), ("renew", "auto_renewal"), ("data", "data_processing"),
    ("fee", "payment"), ("pay", "payment"), ("confiden", "confidentiality"), ("terminat", "termination"),
]
_CC_STATUS_TEXT = {429: "Rate limit reached, please retry later", 500: "Internal server error", 503: "Service unavailable"}


class _CCMock:
    def __init__(self):
        self.reset()

    def reset(self, seed=7):
        self.rng = _cc_random.Random(seed)
        self.queue = []
        self.calls = []
        self.last_system = None

    def seed(self, n):
        self.rng = _cc_random.Random(n)

    def fail_next(self, status, times=1):
        self.queue.extend([status] * times)

    def _judge(self, text):
        low = text.lower()
        m = _cc_re.search(r"clause\s+(\d+(?:\.\d+)*)", text, _cc_re.I)
        clause_id = m.group(1) if m else "unknown"
        if "as is" in low:
            verdict = "accept" if self.rng.random() < 0.6 else "flag"
            return {"clause_id": clause_id, "verdict": verdict, "risk_level": "low", "topic": "other",
                    "rationale": "Mock review: mutual 'AS IS' disclaimer; the mock is unsure on purpose."}
        for kw, verdict, risk, topic in _CC_RULES:
            if kw in low:
                return {"clause_id": clause_id, "verdict": verdict, "risk_level": risk, "topic": topic,
                        "rationale": f"Mock review: matched '{kw}'."}
        return {"clause_id": clause_id, "verdict": "accept", "risk_level": "low", "topic": "other",
                "rationale": "Mock review: nothing unusual found."}

    def handle(self, url, headers, body):
        self.calls.append({"url": url, "body": body})
        if not str(url).endswith("/chat/completions"):
            return 404, {"error": {"message": "Not Found: the URL should end with /chat/completions", "type": "not_found"}}
        headers = headers or {}
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        if not str(auth).startswith("Bearer sk-"):
            return 401, {"error": {"message": "Authentication Fails: send the header Authorization: Bearer <your key>", "type": "authentication_error"}}
        if self.queue:
            status = self.queue.pop(0)
            return status, {"error": {"message": _CC_STATUS_TEXT.get(status, "error"), "type": "server_error"}}
        if not isinstance(body, dict) or not isinstance(body.get("model"), str) or not isinstance(body.get("messages"), list) or not body["messages"]:
            return 400, {"error": {"message": "Invalid request: the body needs 'model' (a string) and 'messages' (a non-empty list)", "type": "invalid_request_error"}}
        if body["model"] not in ("deepseek-chat", "deepseek-reasoner"):
            return 400, {"error": {"message": f"Model Not Exist: {body['model']}", "type": "invalid_request_error"}}
        messages = body["messages"]
        for i, m in enumerate(messages):
            if not isinstance(m, dict) or m.get("role") not in ("system", "user", "assistant", "tool"):
                return 400, {"error": {"message": f"Invalid message at index {i}: needs a 'role' of system/user/assistant/tool", "type": "invalid_request_error"}}
            if m["role"] != "assistant" and not isinstance(m.get("content"), str):
                return 400, {"error": {"message": f"Invalid message at index {i}: 'content' must be a string", "type": "invalid_request_error"}}
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        cache_hit = len(system) // 4 if system and system == self.last_system else 0
        self.last_system = system
        prompt_text = "".join(m.get("content") or "" for m in messages)
        prompt_tokens = len(prompt_text) // 4 + 8
        user_text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        tools = body.get("tools") or []
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        fmt = (body.get("response_format") or {}).get("type")
        finish = "stop"
        if tools and not tool_msgs:
            low = user_text.lower()
            topic = next((t for kw, t in _CC_TOPICS if kw in low), "other")
            name = tools[0].get("function", {}).get("name", "tool")
            message = {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": name, "arguments": _cc_json.dumps({"topic": topic})}}]}
            finish = "tool_calls"
        else:
            if fmt == "json_object":
                content = _cc_json.dumps(self._judge(user_text))
                if "[bad-json]" in user_text:
                    content = "Sure! Here is the JSON you asked for:\n" + content
            elif tool_msgs:
                content = "Based on the playbook: " + str(tool_msgs[-1].get("content"))[:80]
            else:
                content = "Mock reply: " + user_text[:60]
            message = {"role": "assistant", "content": content}
        completion_tokens = len(message.get("content") or "") // 4 + 5
        usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                 "total_tokens": prompt_tokens + completion_tokens,
                 "prompt_cache_hit_tokens": cache_hit, "prompt_cache_miss_tokens": prompt_tokens - cache_hit}
        return 200, {"id": f"mock-{len(self.calls)}", "object": "chat.completion", "model": body["model"],
                     "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage}


class _CCHTTPError(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class _CCResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload
        self.text = _cc_json.dumps(payload, ensure_ascii=False)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return _cc_json.loads(self.text)

    def raise_for_status(self):
        if not self.ok:
            msg = (self._payload.get("error") or {}).get("message", "") if isinstance(self._payload, dict) else ""
            raise _CCHTTPError(f"{self.status_code} Error: {msg}", response=self)

    def __repr__(self):
        return f"<Response [{self.status_code}]>"


def _cc_install():
    mock = _CCMock()

    def post(url, headers=None, json=None, data=None, timeout=None, **_kwargs):
        body = json
        if body is None and data is not None:
            try:
                body = _cc_json.loads(data)
            except Exception:
                return _CCResponse(400, {"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}})
        status, payload = mock.handle(url, headers, body)
        return _CCResponse(status, payload)

    def get(url, **_kwargs):
        return _CCResponse(405, {"error": {"message": "Method Not Allowed: this endpoint needs POST", "type": "invalid_request_error"}})

    requests = _cc_types.ModuleType("requests")
    requests.post = post
    requests.get = get
    requests.HTTPError = _CCHTTPError
    requests.Response = _CCResponse
    requests.exceptions = _cc_types.SimpleNamespace(HTTPError=_CCHTTPError, Timeout=TimeoutError, RequestException=Exception)
    _cc_sys.modules["requests"] = requests

    dotenv = _cc_types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: True
    _cc_sys.modules["dotenv"] = dotenv

    _cc_os.environ["DEEPSEEK_API_KEY"] = "sk-mock-0000"
    return mock


MOCK = _cc_install()
