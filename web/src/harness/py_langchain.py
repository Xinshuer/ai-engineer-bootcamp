"""LangChain / LangGraph exercises. The REAL libraries run unchanged (langchain-core, langchain,
langgraph + checkpoint + prebuilt, langchain-openai, langchain-deepseek, langchain-text-splitters,
openai); this file only fills the gaps of the browser runtime and points the network at the mock:

  - uuid_utils and ormsgpack are native packages Pyodide does not ship: pure-Python stand-ins
    (Python 3.14's own uuid.uuid7; a msgpack packer that follows ormsgpack's rules).
  - The browser has no threads: thread pools run each task at once, so parallel branches
    (Send, RunnableParallel, batch) run one after another. Results are the same.
  - There is no network: every httpx client (the openai SDK uses httpx) talks to the mock DeepSeek
    server in py_mock.py. Streaming requests get server-sent events; the SDK's automatic retries
    record their back-off in MOCK.sleeps instead of really sleeping.

Loaded as the module `_cclc`. The exercise setup calls prepare() (imports once, a few seconds the
first time) and use_mock(MOCK) (every run gets a fresh mock). The local export inlines this file:
on normal Python only the network part is installed.
"""
import json as _json
import sys as _sys
import types as _types
import warnings as _warnings

_BROWSER = _sys.platform == "emscripten"
_STATE = {"mock": None, "ready": False}


# ---------------------------------------------------------------- stand-ins for native packages
def _install_uuid_utils():
    if "uuid_utils" in _sys.modules:
        return
    import uuid
    mod = _types.ModuleType("uuid_utils")
    compat = _types.ModuleType("uuid_utils.compat")
    for m in (mod, compat):
        m.uuid7, m.uuid4, m.UUID = uuid.uuid7, uuid.uuid4, uuid.UUID
    mod.compat = compat
    _sys.modules["uuid_utils"] = mod
    _sys.modules["uuid_utils.compat"] = compat


def _install_ormsgpack():
    # Only what langgraph.checkpoint.serde.jsonplus uses: packb / unpackb / Ext / the OPT_ flags.
    # ormsgpack packs None, bool, int, float, str, bytes, list, tuple and dict natively (subclasses
    # too); with the PASSTHROUGH options, enums, dataclasses, datetimes and UUIDs go to `default`.
    if "ormsgpack" in _sys.modules:
        return
    import enum
    import struct
    import msgpack

    mod = _types.ModuleType("ormsgpack")
    opts = dict(OPT_NAIVE_UTC=1 << 1, OPT_NON_STR_KEYS=1 << 2, OPT_SERIALIZE_NUMPY=1 << 3,
                OPT_SERIALIZE_PYDANTIC=1 << 4, OPT_PASSTHROUGH_DATACLASS=1 << 5, OPT_PASSTHROUGH_DATETIME=1 << 6,
                OPT_PASSTHROUGH_BIG_INT=1 << 7, OPT_PASSTHROUGH_SUBCLASS=1 << 8, OPT_PASSTHROUGH_TUPLE=1 << 9,
                OPT_PASSTHROUGH_UUID=1 << 10, OPT_OMIT_MICROSECONDS=1 << 11, OPT_REPLACE_SURROGATES=1 << 12,
                OPT_PASSTHROUGH_ENUM=1 << 13, OPT_UTC_Z=1 << 14, OPT_DATETIME_AS_TIMESTAMP_EXT=1 << 15)
    NON_STR_KEYS, SURROGATES, P_ENUM = opts["OPT_NON_STR_KEYS"], opts["OPT_REPLACE_SURROGATES"], opts["OPT_PASSTHROUGH_ENUM"]

    class MsgpackEncodeError(TypeError):
        pass

    class MsgpackDecodeError(ValueError):
        pass

    class Ext:
        __slots__ = ("tag", "data")

        def __init__(self, tag, data):
            if not isinstance(tag, int) or not -128 <= tag <= 127:
                raise TypeError("tag must be an int between -128 and 127")
            self.tag, self.data = tag, bytes(data)

    def text(s, option):
        try:
            return s.encode("utf-8")
        except UnicodeEncodeError:
            if option & SURROGATES:
                return "".join("\ufffd" if 0xD800 <= ord(c) <= 0xDFFF else c for c in s).encode("utf-8")
            raise MsgpackEncodeError("str is not valid UTF-8: surrogates not allowed") from None

    def head(n, small, tags):
        # tags: (8-bit, 16-bit, 32-bit) type bytes; small: (base, max) for the fix-size form
        if small and n <= small[1]:
            return struct.pack("B", small[0] | n)
        for tag, fmt, lim in zip(tags, (">B", ">H", ">I"), (0xFF, 0xFFFF, 0xFFFFFFFF)):
            if tag is not None and n <= lim:
                return tag + struct.pack(fmt, n)
        raise MsgpackEncodeError("object too large")

    def pack(obj, out, default, option, depth):
        if depth > 1024:
            raise MsgpackEncodeError("Recursion limit reached")
        if obj is None:
            out.append(b"\xc0")
        elif obj is True or obj is False:
            out.append(b"\xc3" if obj else b"\xc2")
        elif isinstance(obj, enum.Enum) and option & P_ENUM:
            pack_default(obj, out, default, option, depth)
        elif isinstance(obj, int):
            n = int(obj)
            if -32 <= n <= 0x7F:
                out.append(struct.pack("b" if n < 0 else "B", n))
            elif 0 <= n <= 0xFFFFFFFFFFFFFFFF:
                for tag, fmt, lim in ((b"\xcc", ">B", 0xFF), (b"\xcd", ">H", 0xFFFF), (b"\xce", ">I", 0xFFFFFFFF), (b"\xcf", ">Q", 0xFFFFFFFFFFFFFFFF)):
                    if n <= lim:
                        out.append(tag + struct.pack(fmt, n))
                        break
            elif -0x8000000000000000 <= n < 0:
                for tag, fmt, lim in ((b"\xd0", ">b", 0x80), (b"\xd1", ">h", 0x8000), (b"\xd2", ">i", 0x80000000), (b"\xd3", ">q", 0x8000000000000000)):
                    if n >= -lim:
                        out.append(tag + struct.pack(fmt, n))
                        break
            else:
                pack_default(obj, out, default, option, depth)
        elif isinstance(obj, float):
            out.append(b"\xcb" + struct.pack(">d", float(obj)))
        elif isinstance(obj, str):
            b = text(str(obj), option)
            out.append(head(len(b), (0xA0, 31), (b"\xd9", b"\xda", b"\xdb")) + b)
        elif isinstance(obj, (bytes, bytearray, memoryview)):
            b = bytes(obj)
            out.append(head(len(b), None, (b"\xc4", b"\xc5", b"\xc6")) + b)
        elif isinstance(obj, Ext):
            n = len(obj.data)
            fixed = {1: b"\xd4", 2: b"\xd5", 4: b"\xd6", 8: b"\xd7", 16: b"\xd8"}
            out.append((fixed[n] if n in fixed else head(n, None, (b"\xc7", b"\xc8", b"\xc9"))) + struct.pack(">b", obj.tag) + obj.data)
        elif isinstance(obj, (list, tuple)):
            out.append(head(len(obj), (0x90, 15), (None, b"\xdc", b"\xdd")))
            for x in obj:
                pack(x, out, default, option, depth + 1)
        elif isinstance(obj, dict):
            out.append(head(len(obj), (0x80, 15), (None, b"\xde", b"\xdf")))
            for k, v in obj.items():
                if not isinstance(k, str) and not option & NON_STR_KEYS:
                    raise MsgpackEncodeError("Dict key must be str")
                pack(k, out, default, option, depth + 1)
                pack(v, out, default, option, depth + 1)
        else:
            pack_default(obj, out, default, option, depth)

    def pack_default(obj, out, default, option, depth):
        if default is None:
            raise MsgpackEncodeError(f"Type is not msgpack serializable: {type(obj).__name__}")
        try:
            new = default(obj)
        except MsgpackEncodeError:
            raise
        except TypeError as e:
            raise MsgpackEncodeError(str(e)) from e
        if new is obj:
            raise MsgpackEncodeError(f"Type is not msgpack serializable: {type(obj).__name__}")
        pack(new, out, default, option, depth + 1)

    def packb(obj, /, default=None, option=None):
        out = []
        pack(obj, out, default, option or 0, 0)
        return b"".join(out)

    def unpackb(data, /, ext_hook=None, option=None):
        def hook(code, payload):
            if ext_hook is None:
                raise MsgpackDecodeError(f"unknown ext type {code}")
            return ext_hook(code, payload)
        try:
            return msgpack.unpackb(bytes(data), raw=False, strict_map_key=False, use_list=True, ext_hook=hook)
        except (ValueError, msgpack.exceptions.ExtraData, msgpack.exceptions.FormatError, msgpack.exceptions.StackError) as e:
            raise MsgpackDecodeError(str(e)) from e

    for k, v in opts.items():
        setattr(mod, k, v)
    mod.MsgpackEncodeError, mod.MsgpackDecodeError, mod.Ext = MsgpackEncodeError, MsgpackDecodeError, Ext
    mod.packb, mod.unpackb, mod.__version__ = packb, unpackb, "1.12.0"
    _sys.modules["ormsgpack"] = mod


def _no_threads():
    # Pyodide cannot start threads: submit() runs the task right away and returns a finished Future.
    # One exception: LangGraph's streaming "waiter" (SyncQueue.wait) blocks until another thread
    # produces output. Every task has already run by the time it would wait, so it is answered
    # at once with a finished Future ("output may be ready, go and look"), which is what it signals.
    import concurrent.futures as cf
    import contextvars
    import functools
    if getattr(cf.ThreadPoolExecutor, "_cc_sync", False):
        return

    def target(fn, args):
        while True:
            if isinstance(fn, functools.partial):
                fn, args = fn.func, fn.args + tuple(args)
            elif isinstance(getattr(fn, "__self__", None), contextvars.Context) and args:
                fn, args = args[0], args[1:]
            else:
                return fn

    def submit(self, fn, /, *args, **kwargs):
        f = cf.Future()
        real = target(fn, args)
        if getattr(real, "__name__", "") == "wait" and type(getattr(real, "__self__", None)).__name__ == "SyncQueue":
            f.set_result(None)
            return f
        try:
            f.set_result(fn(*args, **kwargs))
        except BaseException as e:  # noqa: BLE001 (a Future carries any exception)
            f.set_exception(e)
        return f

    cf.ThreadPoolExecutor.submit = submit
    cf.ThreadPoolExecutor._cc_sync = True


# ---------------------------------------------------------------- the network goes to the mock
def _sse(body, payload):
    # a chat completion as the chunks a streaming request receives (reasoning first, then content,
    # in 12-character pieces)
    msg = payload["choices"][0]["message"]
    base = {"id": payload["id"], "object": "chat.completion.chunk", "created": 0, "model": payload["model"]}
    deltas = [{"role": "assistant", "content": ""}]
    reasoning = msg.get("reasoning_content") or ""
    deltas += [{"reasoning_content": reasoning[i:i + 12]} for i in range(0, len(reasoning), 12)]
    content = msg.get("content") or ""
    deltas += [{"content": content[i:i + 12]} for i in range(0, len(content), 12)]
    for j, tc in enumerate(msg.get("tool_calls") or []):
        fn = tc["function"]
        deltas.append({"tool_calls": [{"index": j, "id": tc["id"], "type": "function", "function": {"name": fn["name"], "arguments": ""}}]})
        deltas += [{"tool_calls": [{"index": j, "function": {"arguments": fn["arguments"][i:i + 10]}}]}
                   for i in range(0, len(fn["arguments"]), 10)]
    events = [dict(base, choices=[{"index": 0, "delta": d, "finish_reason": None}]) for d in deltas]
    events.append(dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": payload["choices"][0]["finish_reason"]}]))
    if (body.get("stream_options") or {}).get("include_usage"):
        events.append(dict(base, choices=[], usage=payload["usage"]))
    return "".join(f"data: {_json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"


def _respond(http, request):
    mock = _STATE["mock"]
    if mock is None:
        raise http.ConnectError("no network here: this exercise has no mock server", request=request)
    try:
        body = _json.loads(request.content or b"null")
    except ValueError:
        body = None
    status, payload = mock.handle(str(request.url), dict(request.headers), body)
    if status == 200 and isinstance(body, dict) and body.get("stream") and "choices" in payload:
        return http.Response(200, content=_sse(body, payload).encode(), headers={"content-type": "text/event-stream"}, request=request)
    return http.Response(status, json=payload, request=request)


def _route_httpx():
    # openai 2.x uses httpx; openai 3.x (what pip picks on a normal machine) uses its fork httpx2
    import importlib
    for name in ("httpx", "httpx2"):
        try:
            http = importlib.import_module(name)
        except ImportError:
            continue
        if getattr(http.Client, "_cc_mock", False):
            continue

        class MockTransport(http.BaseTransport):
            def handle_request(self, request, _http=http):
                return _respond(_http, request)

        class AsyncMockTransport(http.AsyncBaseTransport):
            async def handle_async_request(self, request, _http=http):
                return _respond(_http, request)

        def patch(cls, transport):
            orig = cls.__init__

            def __init__(self, *args, **kwargs):
                if kwargs.get("transport") is None:
                    kwargs["transport"] = transport()
                orig(self, *args, **kwargs)
            cls.__init__ = __init__
            cls._cc_mock = True

        patch(http.Client, MockTransport)
        patch(http.AsyncClient, AsyncMockTransport)


def _no_real_sleep():
    # the openai SDK retries 429 / 5xx itself (max_retries=2 by default) and sleeps in between:
    # record the back-off instead of waiting
    import time
    import openai._base_client as base

    class _Time:
        def __getattr__(self, name):
            return getattr(time, name)

        @staticmethod
        def sleep(seconds):
            mock = _STATE["mock"]
            if mock is not None:
                mock.sleeps.append(round(seconds, 3))

    base.time = _Time()


def prepare():
    """Import the stack once. The mock's fake `requests` module is hidden meanwhile: langsmith
    (imported by langchain_core) needs the real one."""
    if _STATE["ready"]:
        return
    if _BROWSER:
        _install_uuid_utils()
        _install_ormsgpack()
        _no_threads()
    fake = _sys.modules.get("requests")
    if fake is not None and getattr(fake, "__file__", None) is None:
        del _sys.modules["requests"]
    else:
        fake = None
    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")  # e.g. "Core Pydantic V1 functionality isn't compatible with Python 3.14"
            import langchain_core.messages  # noqa: F401
            import langchain_core.prompts  # noqa: F401
            import langchain_core.runnables  # noqa: F401
            import langchain_core.tools  # noqa: F401
            import langchain_core.output_parsers  # noqa: F401
            import langchain_core.documents  # noqa: F401
            import langchain_core.vectorstores  # noqa: F401
            import langchain_core.language_models.fake_chat_models  # noqa: F401
            import langgraph.graph  # noqa: F401
            import langgraph.types  # noqa: F401
            import langgraph.errors  # noqa: F401
            import langgraph.checkpoint.memory  # noqa: F401
            import langgraph.prebuilt  # noqa: F401
            import langchain.agents  # noqa: F401
            import langchain.chat_models  # noqa: F401
            import langchain_openai  # noqa: F401
            import langchain_deepseek  # noqa: F401
            import langchain_text_splitters  # noqa: F401
    finally:
        if fake is not None:
            _sys.modules["requests"] = fake
    _route_httpx()
    _no_real_sleep()
    _STATE["ready"] = True


def use_mock(mock):
    """Point every model call of this run at `mock` (the MOCK object of py_mock.py)."""
    mock.sleeps = []
    _STATE["mock"] = mock
