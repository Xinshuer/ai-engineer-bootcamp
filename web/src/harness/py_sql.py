"""SQL exercises, run on SQLite inside Pyodide (and in the build validator).

run_sql(user_sql, spec_json, setup_sql) -> JSON string with the same shape as run() in
py_runner.py, plus the result tables:
  {"stdout", "error", "error_line", "tests": [...], "table": {columns, rows}, "expected_table": ...}

spec: {"solution": reference SQL or null (just run and show the result),
       "check": a SELECT run after both scripts (for INSERT/UPDATE/DELETE/CREATE exercises),
       "ordered": compare rows in order (true when the task asks for an ORDER BY),
       "bq": BigQuery mode (see bq_translate)}

Loaded as the module `_ccsql` (see _cc_load_module in py_runner.py); the mock
google.cloud.bigquery client in py_cloud.py (module `_cccloud`) reuses its BigQuery helpers.
"""
import datetime as _dt
import json as _json
import re as _re
import sqlite3 as _sqlite3

_MAX_ROWS = 200


# ---------------------------------------------------------------- BigQuery flavour on SQLite
# Emulated (and only this): table names must carry the dataset (`project.dataset.table`,
# `dataset.table` or dataset.table, unless a default dataset is set); "/" always divides as
# FLOAT64; DIV(x, y); CAST / SAFE_CAST to STRING, INT64, FLOAT64, BOOL; IF(cond, a, b);
# SAFE_DIVIDE; COUNTIF (0 over no rows); LOGICAL_OR / LOGICAL_AND; STRING_AGG(x[, sep]) and
# STRING_AGG(DISTINCT x[, sep]); DATE_TRUNC / TIMESTAMP_TRUNC and DATE_DIFF / TIMESTAMP_DIFF
# with a bare date part (MONTH, not 'MONTH'); CURRENT_TIMESTAMP() / CURRENT_DATE().
# Not emulated: UNNEST, ARRAY, STRUCT, QUALIFY, APPROX_QUANTILES, SELECT * EXCEPT, partitions ...
class BigQueryError(Exception):
    """An error BigQuery itself would report (the mock client turns it into BadRequest)."""


_UNITS = "MICROSECOND|MILLISECOND|SECOND|MINUTE|HOUR|DAY|WEEK|MONTH|QUARTER|YEAR"
_PART = "§"  # marks a date part that was written bare, as BigQuery requires
_TYPES = {"STRING": "TEXT", "INT64": "INTEGER", "INTEGER": "INTEGER", "FLOAT64": "REAL", "NUMERIC": "REAL",
          "BIGNUMERIC": "REAL", "BOOL": "INTEGER", "BOOLEAN": "INTEGER"}
_KEYWORDS = {"select", "where", "on", "using", "group", "order", "limit", "left", "right", "inner", "outer", "full",
             "cross", "join", "union", "as", "lateral", "unnest"}


def _split_code(sql):
    """Yield (is_code, text) pieces so rewrites never touch string literals or comments."""
    pieces, i, start, n = [], 0, 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in "'\"":
            j = i + 1
            while j < n and not (sql[j] == ch and (j + 1 >= n or sql[j + 1] != ch)):
                j += 2 if sql[j] == ch else 1
            pieces += [(True, sql[start:i]), (False, sql[i:j + 1])]
            i = start = j + 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j < 0 else j
            pieces += [(True, sql[start:i]), (False, sql[i:j])]
            i = start = j
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j < 0 else j + 2
            pieces += [(True, sql[start:i]), (False, sql[i:j])]
            i = start = j
        else:
            i += 1
    pieces.append((True, sql[start:]))
    return [p for p in pieces if p[1]]


def _code_only(sql, fn):
    return "".join(fn(text) if is_code else text for is_code, text in _split_code(sql))


def _mask(sql):
    """The same text with string literals and comments blanked out (same length)."""
    return "".join(text if is_code else " " * len(text) for is_code, text in _split_code(sql))


def _call_args(masked, open_paren):
    """Index of the ')' matching the '(' at open_paren (in the masked text)."""
    depth = 0
    for i in range(open_paren, len(masked)):
        if masked[i] == "(":
            depth += 1
        elif masked[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise BigQueryError("Syntax error: Unclosed parenthesis")


def _rewrite_call(text, name, fn):
    """Replace every NAME( ... ) call (outside strings and comments) by fn(inner_text)."""
    out, i = [], 0
    pat = _re.compile(r"\b" + name + r"\s*\(", _re.I)
    while True:
        masked = _mask(text)
        m = pat.search(masked, i)
        if not m:
            out.append(text[i:])
            return "".join(out)
        close = _call_args(masked, m.end() - 1)
        out.append(text[i:m.start()])
        out.append(fn(text[m.end():close]))
        i = close + 1


def _check_qualified(sql, tables, default_dataset):
    """BigQuery needs dataset-qualified table names unless a default dataset is set."""
    if default_dataset:
        return
    code = _code_only(sql, lambda t: t)
    ctes = {m.group(1).lower() for m in _re.finditer(r"(?:\bwith\b|,)\s*(\w+)\s+as\s*\(", code, _re.I)}
    for m in _re.finditer(r"\b(?:from|join|into|update|table)\s+([`\w.-]+)", code, _re.I):
        name = m.group(1)
        if "." in name or name.startswith("`") or name.lower() in ctes or name.lower() in _KEYWORDS:
            continue
        if name.lower() in {t.lower() for t in tables}:
            raise BigQueryError(f'Table name "{name}" missing dataset while no default dataset is set in the request.')


def bq_translate(sql, tables=(), datasets=("clausecheck",), default_dataset=None):
    """GoogleSQL (the subset above) -> SQLite. Raises BigQueryError for what BigQuery would reject."""
    _check_qualified(sql, tables, default_dataset)

    def code(s):
        s = _re.sub(r"`[\w-]+\.(\w+)\.(\w+)`", r"\2", s)                  # `project.dataset.table`
        s = _re.sub(r"`(\w+)\.(\w+)`", r"\2", s)                          # `dataset.table`
        for ds in datasets:
            s = _re.sub(r"(?<![\w.`])(?:[\w-]+\.)?" + _re.escape(ds) + r"\.(\w+)", r"\1", s)
        s = _re.sub(r"\bCURRENT_(TIMESTAMP|DATE)\s*\(\s*\)", r"CURRENT_\1", s, flags=_re.I)
        s = _re.sub(r"\bSAFE_CAST\s*\(", "CAST(", s, flags=_re.I)
        s = _re.sub(r"\bAS\s+(" + "|".join(_TYPES) + r")\b(?=\s*\))", lambda m: "AS " + _TYPES[m.group(1).upper()], s, flags=_re.I)
        s = s.replace("/", " * 1.0 / ")                                   # GoogleSQL "/" returns FLOAT64
        return s

    s = _code_only(sql, code)

    # a bare date part (MONTH, DAY, ...) is only a date part as the LAST argument of these functions;
    # elsewhere (e.g. an alias called month in GROUP BY customer, month) it is a plain name
    def date_part(fname):
        def fix(inner):
            masked, depth, cut = _mask(inner), 0, -1
            for i, ch in enumerate(masked):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                elif ch == "," and depth == 0:
                    cut = i
            last = inner[cut + 1:]
            m = _re.fullmatch(r"\s*(" + _UNITS + r")\s*", _mask(last), _re.I)
            if cut >= 0 and m:
                last = f" '{_PART}{m.group(1).upper()}'"
            return f"{fname}({inner[:cut + 1]}{last})"
        return fix

    for fname in ("DATE_TRUNC", "TIMESTAMP_TRUNC", "DATE_DIFF", "TIMESTAMP_DIFF"):
        s = _rewrite_call(s, fname, date_part(fname))
    s = _rewrite_call(s, "COUNTIF", lambda inner: f"COUNT(CASE WHEN ({inner}) THEN 1 END)")

    def string_agg(inner):
        if _re.search(r"\border\s+by\b", inner, _re.I):
            raise BigQueryError("本页的模拟不支持 STRING_AGG(... ORDER BY ...)：在真 BigQuery 里可以这样写")
        m = _re.match(r"\s*DISTINCT\s+(.*)$", inner, _re.I | _re.S)
        return f"_CC_STRING_AGG_DISTINCT({m.group(1)})" if m else f"STRING_AGG({inner})"

    s = _rewrite_call(s, "STRING_AGG", string_agg)
    return s


def _parse_ts(v):
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.replace(tzinfo=None)
    text = str(v).replace("T", " ")[:19]
    return _dt.datetime.fromisoformat(text) if len(text) > 10 else _dt.datetime.fromisoformat(text + " 00:00:00")


def _has_time(v):
    return v is not None and len(str(v)) > 10


def _unit(part):
    part = str(part)
    if not part.startswith(_PART):
        raise BigQueryError(f"日期部件要写成不带引号的关键字，比如 MONTH，而不是字符串 {part!r}（BigQuery 会报 A valid date part name is required）")
    return part[len(_PART):]


def _trunc(v, part):
    unit = _unit(part)
    t = _parse_ts(v)
    if t is None:
        return None
    if unit == "YEAR":
        t = t.replace(month=1, day=1, hour=0, minute=0, second=0)
    elif unit == "QUARTER":
        t = t.replace(month=(t.month - 1) // 3 * 3 + 1, day=1, hour=0, minute=0, second=0)
    elif unit == "MONTH":
        t = t.replace(day=1, hour=0, minute=0, second=0)
    elif unit == "WEEK":  # BigQuery weeks start on Sunday
        t = (t - _dt.timedelta(days=(t.weekday() + 1) % 7)).replace(hour=0, minute=0, second=0)
    elif unit == "DAY":
        t = t.replace(hour=0, minute=0, second=0)
    elif unit == "HOUR":
        t = t.replace(minute=0, second=0)
    elif unit == "MINUTE":
        t = t.replace(second=0)
    elif unit != "SECOND":
        raise BigQueryError(f"本页的模拟不支持按 {unit} 截断")
    # keep the input's shape: a DATE stays a DATE, a TIMESTAMP stays a TIMESTAMP
    return t.strftime("%Y-%m-%d %H:%M:%S") if _has_time(v) else t.strftime("%Y-%m-%d")


_SECONDS = {"MICROSECOND": 1e-6, "MILLISECOND": 1e-3, "SECOND": 1, "MINUTE": 60, "HOUR": 3600, "DAY": 86400}


def _timestamp_diff(a, b, part):
    unit = _unit(part)
    if unit not in _SECONDS:
        raise BigQueryError(f"TIMESTAMP_DIFF does not support the {unit} date part")
    ta, tb = _parse_ts(a), _parse_ts(b)
    if ta is None or tb is None:
        return None
    return int((ta - tb).total_seconds() / _SECONDS[unit])


def _date_diff(a, b, part):
    unit = _unit(part)
    ta, tb = _parse_ts(a), _parse_ts(b)
    if ta is None or tb is None:
        return None
    da, db = ta.date(), tb.date()
    if unit == "DAY":
        return (da - db).days
    if unit == "WEEK":  # number of Sunday boundaries crossed
        sa = da - _dt.timedelta(days=(da.weekday() + 1) % 7)
        sb = db - _dt.timedelta(days=(db.weekday() + 1) % 7)
        return (sa - sb).days // 7
    if unit == "MONTH":
        return (da.year - db.year) * 12 + da.month - db.month
    if unit == "QUARTER":
        return (da.year * 4 + (da.month - 1) // 3) - (db.year * 4 + (db.month - 1) // 3)
    if unit == "YEAR":
        return da.year - db.year
    raise BigQueryError(f"DATE_DIFF does not support the {unit} date part")


def _div(x, y):
    if x is None or y is None:
        return None
    if y == 0:
        raise BigQueryError("division by zero: DIV(x, 0)")
    q = abs(int(x)) // abs(int(y))
    return q if (x >= 0) == (y >= 0) else -q


def _safe_divide(a, b):
    return None if a is None or b is None or b == 0 else a / b


class _LogicalOr:
    def __init__(self):
        self.v = None

    def step(self, x):
        if x is not None:
            self.v = bool(self.v) or bool(x)

    def finalize(self):
        return None if self.v is None else int(self.v)


class _LogicalAnd:
    def __init__(self):
        self.v = None

    def step(self, x):
        if x is not None:
            self.v = (True if self.v is None else self.v) and bool(x)

    def finalize(self):
        return None if self.v is None else int(self.v)


class _StringAgg:
    distinct = False

    def __init__(self):
        self.parts, self.sep = [], ","

    def step(self, x, sep=","):
        self.sep = sep
        if x is not None and not (self.distinct and str(x) in self.parts):
            self.parts.append(str(x))

    def finalize(self):
        return self.sep.join(self.parts) if self.parts else None


class _StringAggDistinct(_StringAgg):
    distinct = True


# SQLite replaces an exception raised inside a function by "user-defined function raised
# exception"; keep the BigQuery error so it can be reported instead (see udf_error)
_LAST_UDF_ERROR = [None]


def _keep_error(fn):
    def wrapped(*args):
        try:
            return fn(*args)
        except BigQueryError as exc:
            _LAST_UDF_ERROR[0] = exc
            raise
    return wrapped


def udf_error(exc):
    """The BigQuery error behind a sqlite3 error, if a BigQuery function raised it."""
    kept, _LAST_UDF_ERROR[0] = _LAST_UDF_ERROR[0], None
    return kept if kept is not None and "user-defined function raised exception" in str(exc) else None


def bq_register(conn):
    conn.create_function("SAFE_DIVIDE", 2, _safe_divide)
    conn.create_function("DIV", 2, _keep_error(_div))
    conn.create_function("IF", 3, lambda cond, a, b: a if cond else b)
    conn.create_function("DATE_TRUNC", 2, _keep_error(_trunc))
    conn.create_function("TIMESTAMP_TRUNC", 2, _keep_error(_trunc))
    conn.create_function("DATE_DIFF", 3, _keep_error(_date_diff))
    conn.create_function("TIMESTAMP_DIFF", 3, _keep_error(_timestamp_diff))
    conn.create_aggregate("LOGICAL_OR", 1, _LogicalOr)
    conn.create_aggregate("LOGICAL_AND", 1, _LogicalAnd)
    for n in (1, 2):
        conn.create_aggregate("STRING_AGG", n, _StringAgg)
        conn.create_aggregate("_CC_STRING_AGG_DISTINCT", n, _StringAggDistinct)


def table_names(conn):
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]


# ---------------------------------------------------------------- running and comparing
def _norm(v):
    if isinstance(v, float):
        v = round(v, 6)
        return int(v) if v.is_integer() else v
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v


def _sort_key(row):
    return tuple((x is None, "num" if isinstance(x, (int, float)) else type(x).__name__, x if x is not None else 0) for x in row)


def table_text(columns, rows, limit=20):
    """A plain-text table, like the sqlite3 command line prints in box mode."""
    shown = [["NULL" if v is None else str(v) for v in r] for r in rows[:limit]]
    widths = [max([len(str(c))] + [len(r[i]) for r in shown]) for i, c in enumerate(columns)]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    out = [line, "| " + " | ".join(str(c).ljust(w) for c, w in zip(columns, widths)) + " |", line]
    out += ["| " + " | ".join(v.ljust(w) for v, w in zip(r, widths)) + " |" for r in shown]
    out.append(line)
    out.append(f"... 一共 {len(rows)} 行，只显示前 {limit} 行" if len(rows) > limit else f"{len(rows)} 行")
    return "\n".join(out)


def _connect(setup_sql, bq):
    conn = _sqlite3.connect(":memory:")
    if bq:
        bq_register(conn)
    if setup_sql:
        conn.executescript(setup_sql)
    return conn


def _query(conn, sql):
    cur = conn.execute(sql)
    if cur.description is None:
        return None
    return {"columns": [d[0] for d in cur.description], "rows": [[_norm(v) for v in r] for r in cur.fetchmany(_MAX_ROWS)]}


def _explain(exc):
    exc = udf_error(exc) or exc
    msg = str(exc)
    if "one statement at a time" in msg:
        return "这里一次只能写一条查询（SELECT 或 WITH ... SELECT）：去掉多余的语句或分号后面的内容"
    return f"{type(exc).__name__}: {msg}"


def run_sql(user_sql, spec_json="{}", setup_sql=""):
    spec = _json.loads(spec_json or "{}")
    bq = bool(spec.get("bq"))
    res = {"stdout": "", "error": None, "error_line": None, "tests": [], "table": None, "expected_table": None}
    check, solution = spec.get("check"), spec.get("solution")
    try:
        conn = _connect(setup_sql, bq)
    except Exception as exc:  # the dataset itself is broken
        res["error"] = "（题目环境出错，请告诉出题人）" + _explain(exc)
        return _json.dumps(res, ensure_ascii=False)
    tables = table_names(conn)
    tr = (lambda s: bq_translate(s, tables)) if bq else (lambda s: s)
    if not user_sql.strip():
        res["error"] = "还没有写 SQL"
        return _json.dumps(res, ensure_ascii=False)
    try:
        if check:
            conn.executescript(tr(user_sql))
            got = _query(conn, check)
        else:
            got = _query(conn, tr(user_sql))
            if got is None:
                raise _sqlite3.ProgrammingError("这条语句没有返回结果：这里要写一条 SELECT 查询")
    except Exception as exc:
        res["error"] = _explain(exc)
        return _json.dumps(res, ensure_ascii=False)
    res["table"] = got
    res["stdout"] = table_text(got["columns"], got["rows"])
    if not solution:
        return _json.dumps(res, ensure_ascii=False)
    ref = _connect(setup_sql, bq)
    if check:
        ref.executescript(tr(solution))
        want = _query(ref, check)
    else:
        want = _query(ref, tr(solution))
    res["expected_table"] = want
    ordered = bool(spec.get("ordered"))
    if not check:
        same_cols = [c.lower() for c in got["columns"]] == [c.lower() for c in want["columns"]]
        res["tests"].append({"label": "列：个数、顺序和名字（别名）都一致", "passed": same_cols,
                             "got": ", ".join(got["columns"]), "expected": ", ".join(want["columns"])})
    g_rows, w_rows = got["rows"], want["rows"]
    if not ordered:
        g_rows, w_rows = sorted(g_rows, key=_sort_key), sorted(w_rows, key=_sort_key)
    same_rows = g_rows == w_rows
    rec = {"label": ("表里的数据和期望一致" if check else "结果的行一致") + ("（顺序也要一致）" if ordered else "（不看顺序）"),
           "passed": same_rows, "got": f"{len(got['rows'])} 行", "expected": f"{len(want['rows'])} 行"}
    if not same_rows and len(g_rows) == len(w_rows):
        if not ordered or sorted(g_rows, key=_sort_key) != sorted(w_rows, key=_sort_key):
            first = next(i for i, (a, b) in enumerate(zip(g_rows, w_rows)) if a != b)
            rec["got"] = f"第 {first + 1} 行是 {g_rows[first]}"
            rec["expected"] = f"{w_rows[first]}"
        else:
            rec["got"], rec["expected"] = "行都对，但顺序不对", "按题目要求 ORDER BY"
    res["tests"].append(rec)
    return _json.dumps(res, ensure_ascii=False)
