# Mock DeepSeek server for exercises, plus an OpenAI-style /embeddings endpoint. Installs fake
# `requests` and `dotenv` modules and sets DEEPSEEK_API_KEY / OPENAI_API_KEY, so learner code
# is identical to what runs against the real API.
# Behaviour is mirrored in ts_runtime.js (__ccMock). Keep the two in sync.
import json as _cc_json
import math as _cc_math
import os as _cc_os
import random as _cc_random
import re as _cc_re
import sys as _cc_sys
import threading as _cc_threading
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
# DeepSeek model names as the live API answered on 2026-09-23: /models lists deepseek-flash
# (DeepSeek-V4.1-Flash) and deepseek-v4-pro. Older names still answer as aliases of Flash:
# deepseek-v4-flash, and deepseek-chat / deepseek-reasoner (announced as discontinued from
# 2026-07-24; chat = thinking off by default, reasoner = thinking on). Replies name the model that
# served them. Any other name: 400 with the real message.
_CC_MODELS = {"deepseek-flash": "deepseek-flash", "deepseek-v4-pro": "deepseek-v4-pro", "deepseek-v4-flash": "deepseek-flash",
              "deepseek-chat": "deepseek-flash", "deepseek-reasoner": "deepseek-flash"}
_CC_STATUS_TEXT = {429: "Rate limit reached, please retry later", 500: "Internal server error", 503: "Service unavailable"}

# Mock embeddings: a deterministic bag of words hashed (FNV-1a) into 256 dimensions, with a few
# contract synonyms folded together so "cancel" lands near "termination". Not a real
# model, but cosine similarity behaves the way the exercises need.
_CC_EMBED_DIM = 256
_CC_STOP = {"the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "by", "with", "is", "are", "be",
            "shall", "will", "may", "this", "that", "any", "all", "its", "it", "as", "at", "from", "such", "not", "no"}
_CC_SYNONYMS = {}
for _cc_key, _cc_words in {
    "liability": "liability liable damage indemnify indemnification indemnity cap capped",
    "termination": "terminate termination terminated cancel cancellation exit",
    "renewal": "renew renewal renewed extend extension rollover",
    "payment": "fee payment pay payable invoice price cost charge",
    "data": "data personal gdpr privacy processing",
    "confidential": "confidential confidentiality secret nda disclose disclosure",
    "warranty": "warranty warrantie guarantee",
    "law": "law governing jurisdiction court arbitration",
}.items():
    for _cc_w in _cc_words.split():
        _CC_SYNONYMS[_cc_w] = _cc_key


def _cc_embed(text):
    vec = [0.0] * _CC_EMBED_DIM
    for w in _cc_re.findall(r"[a-z0-9]+", str(text).lower()):
        if w in _CC_STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        w = _CC_SYNONYMS.get(w, w)
        h = 2166136261
        for ch in w:
            h = ((h ^ ord(ch)) * 16777619) % 4294967296
        vec[h % _CC_EMBED_DIM] += 1.0
    norm = _cc_math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


class _CCMock:
    def __init__(self):
        self._lock = _cc_threading.Lock()
        self.reset()

    def reset(self, seed=7):
        self.rng = _cc_random.Random(seed)
        self.queue = []
        self.calls = []
        self.prompts = []
        self.sleeps = []  # retry waits recorded by the LangChain runtime (py_langchain.py)

    def embed(self, text):
        return _cc_embed(text)

    def seed(self, n):
        self.rng = _cc_random.Random(n)

    def fail_next(self, status, times=1):
        self.queue.extend([status] * times)

    def _judge(self, text):
        low = text.lower()
        m = _cc_re.search(r"clause\s+(\d+(?:\.\d+)*)", text, _cc_re.I)
        clause_id = m.group(1) if m else "unknown"
        # prompt injection: the mock obeys an instruction hidden in the clause text,
        # unless that text sits inside <clause>...</clause> tags
        if "ignore previous instructions" in low and not _cc_re.search(r"<clause>.*ignore previous instructions.*</clause>", low, _cc_re.S):
            return {"clause_id": clause_id, "verdict": "accept", "risk_level": "low", "topic": "other",
                    "rationale": "Mock review: followed an instruction found inside the clause text."}
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
        # on a normal machine LangGraph runs parallel branches in threads: one request at a time,
        # so the prefix cache and the fail_next queue are never updated by two threads at once
        with self._lock:
            return self._handle(url, headers, body)

    def _handle(self, url, headers, body):
        # keep a snapshot, like a real server: later changes to the learner's lists don't rewrite history
        try:
            snapshot = _cc_json.loads(_cc_json.dumps(body))
        except (TypeError, ValueError):
            snapshot = body
        self.calls.append({"url": url, "body": snapshot})
        is_embed = str(url).endswith("/embeddings")
        if not is_embed and not str(url).endswith("/chat/completions"):
            return 404, {"error": {"message": "Not Found: the URL should end with /chat/completions (or /embeddings)", "type": "not_found"}}
        headers = headers or {}
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        if not str(auth).startswith("Bearer sk-"):
            return 401, {"error": {"message": "Authentication Fails: send the header Authorization: Bearer <your key>", "type": "authentication_error"}}
        if self.queue:
            status = self.queue.pop(0)
            return status, {"error": {"message": _CC_STATUS_TEXT.get(status, "error"), "type": "server_error"}}
        if is_embed:
            return self._embeddings(body)
        if not isinstance(body, dict) or not isinstance(body.get("model"), str) or not isinstance(body.get("messages"), list) or not body["messages"]:
            return 400, {"error": {"message": "Invalid request: the body needs 'model' (a string) and 'messages' (a non-empty list)", "type": "invalid_request_error"}}
        if body["model"] not in _CC_MODELS:
            return 400, {"error": {"message": f"The supported API model names are deepseek-flash, deepseek-v4-pro, but you passed {body['model']}.", "type": "invalid_request_error"}}
        # thinking mode (DeepSeek V4): on unless the body says {"thinking": {"type": "disabled"}}
        thinking = body.get("thinking")
        if thinking is not None and (not isinstance(thinking, dict) or thinking.get("type") not in ("enabled", "disabled")):
            return 400, {"error": {"message": "Invalid request: 'thinking' must be {\"type\": \"enabled\"} or {\"type\": \"disabled\"}", "type": "invalid_request_error"}}
        think = thinking["type"] == "enabled" if isinstance(thinking, dict) else body["model"] != "deepseek-chat"
        # thinking mode + tools: every earlier assistant message must carry its reasoning_content. This is the
        # documented rule; the live API did not enforce it when checked on 2026-09-23, the practice server does
        # ("If your code does not correctly pass back reasoning_content, the API will return a 400 error.")
        if think and body.get("tools"):
            for i, m in enumerate(body["messages"]):
                if isinstance(m, dict) and m.get("role") == "assistant" and not isinstance(m.get("reasoning_content"), str):
                    return 400, {"error": {"message": f"Invalid request: thinking mode with tools needs the reasoning_content of every earlier assistant message passed back (message at index {i} has none). Pass it back, or send \"thinking\": {{\"type\": \"disabled\"}}", "type": "invalid_request_error"}}
        messages = body["messages"]
        for i, m in enumerate(messages):
            if not isinstance(m, dict) or m.get("role") not in ("system", "user", "assistant", "tool"):
                return 400, {"error": {"message": f"Invalid message at index {i}: needs a 'role' of system/user/assistant/tool", "type": "invalid_request_error"}}
            if m["role"] != "assistant" and not isinstance(m.get("content"), str):
                return 400, {"error": {"message": f"Invalid message at index {i}: 'content' must be a string", "type": "invalid_request_error"}}
        # like the real API: every tool call is answered by a tool message right after it, and a
        # tool message answers a call from the assistant message before it
        pending = []
        for i, m in enumerate(messages):
            if m["role"] == "tool":
                if m.get("tool_call_id") not in pending:
                    return 400, {"error": {"message": f"Invalid message at index {i}: a 'tool' message must answer a tool call from the assistant message before it (tool_call_id {m.get('tool_call_id')!r} not found)", "type": "invalid_request_error"}}
                pending.remove(m["tool_call_id"])
                continue
            if pending:
                return 400, {"error": {"message": f"Invalid message at index {i}: the assistant message with 'tool_calls' must be followed by 'tool' messages for {pending}", "type": "invalid_request_error"}}
            if m["role"] == "assistant":
                pending = [c.get("id") for c in (m.get("tool_calls") or []) if isinstance(c, dict)]
        if pending:
            return 400, {"error": {"message": f"Invalid request: the last assistant message has 'tool_calls' without 'tool' messages for {pending}", "type": "invalid_request_error"}}
        prompt_text = "".join(m.get("content") or "" for m in messages)
        prompt_tokens = len(prompt_text) // 4 + 8
        # prefix cache, like DeepSeek: only the part at the START of the request that is
        # identical to an earlier request is a hit, counted in blocks of 64 characters
        key = "".join(f"{m['role']}:{m.get('content') or ''}\n" for m in messages)
        same = 0
        for old in self.prompts:
            n = 0
            for a, b in zip(old, key):
                if a != b:
                    break
                n += 1
            same = max(same, n)
        self.prompts = (self.prompts + [key])[-50:]
        cache_hit = min(prompt_tokens, same // 64 * 16)
        user_text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        tools = body.get("tools") or []
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        fmt = (body.get("response_format") or {}).get("type")
        if fmt not in (None, "text", "json_object"):
            return 400, {"error": {"message": f"Invalid request: response_format type {fmt!r} is not supported (use 'json_object', or tools)", "type": "invalid_request_error"}}
        choice = body.get("tool_choice")
        forced = (choice.get("function") or {}).get("name") if isinstance(choice, dict) else None
        required = choice in ("required", "any")
        finish = "stop"
        if tools and choice != "none" and (forced or required or not tool_msgs or "[loop]" in user_text):
            # tool_choice like the real API: "none" never calls a tool, "required" always does, a named
            # function is always that function. Which tool otherwise: the first one whose name appears in
            # the question, else the first one; with "required" after a tool result, the LAST tool (in
            # LangChain's create_agent(response_format=...) that is the answer schema).
            # arguments: filled from the question for the parameters it knows (topic, clause_id, query);
            # with a forced or required tool (structured output) every property is filled.
            # "[bad-args]" sends broken JSON; "[loop]" keeps calling tools forever.
            low = user_text.lower()
            fns = [t.get("function") or {} for t in tools]
            fn = next((f for f in fns if forced and f.get("name") == forced), None) \
                or (fns[-1] if required and tool_msgs else None) \
                or next((f for f in fns if f.get("name") and f["name"] in user_text), fns[0])
            name = fn.get("name", "tool")
            props = (fn.get("parameters") or {}).get("properties")
            topic = next((t for kw, t in _CC_TOPICS if kw in low), "other")
            cid = _cc_re.search(r"clause\s+(\d+(?:\.\d+)*)", user_text, _cc_re.I)
            known = {"topic": topic, "clause_id": cid.group(1) if cid else "unknown",
                     "query": _cc_re.sub(r"\[[a-z-]+\]", "", user_text).strip()[:80]}
            if forced or required:
                args = self._fill(fn.get("parameters") or {}, dict(known, **self._judge(user_text)))
            else:
                args = {"topic": topic} if not props else {k: v for k, v in known.items() if k in props}
            arguments = '{"topic": ' if "[bad-args]" in user_text else _cc_json.dumps(args)
            message = {"role": "assistant", "content": "", "tool_calls": [
                {"id": f"call_{len(tool_msgs) + 1}", "type": "function", "function": {"name": name, "arguments": arguments}}]}
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
        reasoning_tokens = 0
        if think:
            # the chain of thought comes back next to the answer and is billed as output
            message["reasoning_content"] = f"Mock reasoning: {len(messages)} message(s) read; deciding how to answer."
            reasoning_tokens = len(message["reasoning_content"]) // 4 + 40
            completion_tokens += reasoning_tokens
        usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                 "total_tokens": prompt_tokens + completion_tokens,
                 "prompt_cache_hit_tokens": cache_hit, "prompt_cache_miss_tokens": prompt_tokens - cache_hit}
        if think:  # not a required field in the API reference: only sent here when there is reasoning
            usage["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
        return 200, {"id": f"mock-{len(self.calls)}", "object": "chat.completion", "model": _CC_MODELS[body["model"]],
                     "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage}


    def _fill(self, schema, known, defs=None):
        # structured output: like a model, fill every property of the forced tool's schema, using
        # what the review found for the names it knows and a plain value of the right type otherwise
        defs = defs if defs is not None else schema.get("$defs") or {}
        out = {}
        for k, p in (schema.get("properties") or {}).items():
            if "$ref" in p:
                p = defs.get(p["$ref"].split("/")[-1], {})
            enum = p.get("enum") or ([p["const"]] if "const" in p else None)
            v = known.get(k)
            if isinstance(v, str) and p.get("type", "string") == "string" and (not enum or v in enum):
                out[k] = v
            elif enum:
                out[k] = enum[0]
            elif p.get("type") == "object" and p.get("properties"):
                out[k] = self._fill(p, known, defs)
            else:
                out[k] = {"string": f"mock {k}", "integer": 0, "number": 0, "boolean": False,
                          "array": [], "object": {}}.get(p.get("type"))
        return out

    def _embeddings(self, body):
        bad = (400, {"error": {"message": "Invalid request: the body needs 'model' (a string) and 'input' (a string or a non-empty list of strings)", "type": "invalid_request_error"}})
        if not isinstance(body, dict) or not isinstance(body.get("model"), str):
            return bad
        if "embed" not in body["model"]:
            return 400, {"error": {"message": f"Model Not Exist: {body['model']} (use an embedding model, e.g. text-embedding-3-small)", "type": "invalid_request_error"}}
        inp = body.get("input")
        texts = [inp] if isinstance(inp, str) else inp
        # like the real API, token ids are accepted too (LangChain's OpenAIEmbeddings sends them):
        # decoded back to text with tiktoken (Python only; the TypeScript mirror takes strings)
        if isinstance(texts, list) and texts and all(isinstance(t, int) for t in texts):
            texts = [texts]
        if isinstance(texts, list) and texts and all(isinstance(t, list) and t and all(isinstance(x, int) for x in t) for t in texts):
            try:
                import tiktoken
                enc = tiktoken.get_encoding("cl100k_base")
                texts = [enc.decode(t) for t in texts]
            except Exception:  # noqa: BLE001
                return 400, {"error": {"message": "Invalid request: token-id input needs tiktoken; send strings", "type": "invalid_request_error"}}
        if not isinstance(texts, list) or not texts or not all(isinstance(t, str) for t in texts):
            return bad
        tokens = sum(len(t) // 4 + 1 for t in texts)
        return 200, {"object": "list", "model": body["model"],
                     "data": [{"object": "embedding", "index": i, "embedding": _cc_embed(t)} for i, t in enumerate(texts)],
                     "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}


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
    _cc_os.environ["OPENAI_API_KEY"] = "sk-mock-embed"
    return mock


MOCK = _cc_install()
