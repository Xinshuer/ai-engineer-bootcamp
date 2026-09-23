"""Exercise runner. The same file runs inside Pyodide (browser) and in the build validator.

run(user_code, test_code, setup_code) executes the learner's code as "main.py",
then the tests, and returns a JSON string:
  {"stdout": str, "error": str|None, "error_line": int|None, "tests": [ {label, passed, got?, expected?, error?} ]}
"""
import builtins
import io
import json
import linecache
import sys
import traceback

_MAX_OUT = 20000
_MAX_REPR = 300


def _short(text):
    text = str(text)
    return text if len(text) <= _MAX_REPR else text[:_MAX_REPR] + " ..."


def _register(name, src):
    linecache.cache[name] = (len(src), None, src.splitlines(True), name)


def _fmt_exc(exc, files=("main.py",)):
    te = traceback.TracebackException.from_exception(exc)
    frames = [f for f in te.stack if f.filename in files]
    lines = []
    if frames:
        lines.append("Traceback (most recent call last):")
        for f in frames:
            where = f'  File "{f.filename}", line {f.lineno}'
            if f.name != "<module>":
                where += f", in {f.name}"
            lines.append(where)
            if f.line:
                lines.append("    " + f.line.strip())
    lines.extend(part.rstrip("\n") for part in te.format_exception_only())
    return "\n".join(lines)


def _err_line(exc):
    if isinstance(exc, SyntaxError) and exc.filename == "main.py":
        return exc.lineno
    tb = exc.__traceback__
    line = None
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "main.py":
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


def _no_input(*_args, **_kwargs):
    raise RuntimeError("这里不能用 input()：请直接给变量赋值，例如 name = \"8.1\"")


def _same_kind(got, expected):
    if isinstance(expected, bool) or isinstance(got, bool):
        return isinstance(got, bool) and isinstance(expected, bool)
    if expected is None or got is None:
        return got is None and expected is None
    return True


def _make_asserts(results):
    def _record(label, fn, judge):
        rec = {"label": label, "passed": False}
        try:
            judge(rec, fn)
        except BaseException as exc:  # the learner's function raised
            rec["error"] = _fmt_exc(exc)
        results.append(rec)

    def expect(label, fn, expected):
        def judge(rec, fn):
            got = fn()
            rec["got"] = _short(repr(got))
            rec["expected"] = _short(repr(expected))
            rec["passed"] = bool(got == expected) and _same_kind(got, expected)
        _record(label, fn, judge)

    def expect_true(label, fn):
        def judge(rec, fn):
            got = fn()
            rec["got"] = _short(repr(got))
            rec["passed"] = bool(got)
        _record(label, fn, judge)

    def expect_raises(label, fn, exc_type):
        rec = {"label": label, "passed": False, "expected": f"抛出 {exc_type.__name__}"}
        try:
            got = fn()
            rec["got"] = "没有报错，返回了 " + _short(repr(got))
        except exc_type:
            rec["passed"] = True
            rec["got"] = f"抛出了 {exc_type.__name__}"
        except BaseException as exc:
            rec["got"] = f"抛出了 {type(exc).__name__}"
            rec["error"] = _fmt_exc(exc)
        results.append(rec)

    def expect_output(label, fn, expected):
        def judge(rec, fn):
            buf = io.StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                fn()
            finally:
                sys.stdout = old
            got = buf.getvalue().rstrip("\n")
            rec["got"] = _short(got)
            rec["expected"] = _short(expected)
            rec["passed"] = got == expected.rstrip("\n")
        _record(label, fn, judge)

    return {"expect": expect, "expect_true": expect_true, "expect_raises": expect_raises, "expect_output": expect_output}


def run(user_code, test_code="", setup_code=""):
    out = io.StringIO()
    res = {"stdout": "", "error": None, "error_line": None, "tests": []}
    _register("main.py", user_code)
    ns = {"__name__": "__main__", "__builtins__": builtins, "input": _no_input}
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = out
    try:
        try:
            if setup_code:
                exec(compile(setup_code, "setup.py", "exec"), ns)
        except BaseException as exc:
            res["error"] = "（题目环境出错，请告诉出题人）\n" + _fmt_exc(exc, ("setup.py",))
        if res["error"] is None:
            try:
                exec(compile(user_code, "main.py", "exec"), ns)
            except SystemExit:
                pass
            except BaseException as exc:
                res["error"] = _fmt_exc(exc)
                res["error_line"] = _err_line(exc)
        if res["error"] is None and test_code.strip():
            ns.update(_make_asserts(res["tests"]))
            try:
                exec(compile(test_code, "tests.py", "exec"), ns)
            except BaseException as exc:
                res["tests"].append({
                    "label": "测试没法运行：通常是函数名、参数个数或返回值和题目要求不一致",
                    "passed": False,
                    "error": _fmt_exc(exc, ("main.py", "tests.py")),
                })
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    text = out.getvalue()
    if len(text) > _MAX_OUT:
        text = text[:_MAX_OUT] + "\n……（输出太长，已截断）"
    res["stdout"] = text
    return json.dumps(res, ensure_ascii=False)
