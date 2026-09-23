// Build the course site into dist/.
//   node build.mjs              parse content, validate every exercise, emit dist/
//   node build.mjs --day 3      validate only day 3, emit nothing (safe to run several at once)
//   node build.mjs --day 8,9    validate days 8 and 9
// Validation runs the SAME runners the page uses: Pyodide for Python, the TS compiler +
// a sandboxed job for TypeScript. Every solution must pass, every starter must fail,
// and predict-the-output answers are computed here, never typed by hand.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import os from "node:os";
import { execFileSync } from "node:child_process";
import ts from "typescript";

const ROOT = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const P = (...p) => path.join(decodeURIComponent(ROOT), ...p);
const DIST = P("dist");
const onlyDays = process.argv.includes("--day")
  ? new Set(String(process.argv[process.argv.indexOf("--day") + 1]).split(",").map(Number))
  : null;
const EMIT = onlyDays === null;
const SHOW = process.argv.includes("--show");   // print concept / predict outputs while validating

// ---------------------------------------------------------------- parse
function parseContent(file) {
  const text = fs.readFileSync(file, "utf8").replace(/\r\n/g, "\n");
  const blocks = text.split(/^@@ /m).slice(1);
  let day = null;
  for (const block of blocks) {
    const lines = block.split("\n");
    const [kind, id] = lines[0].trim().split(/\s+/);
    const obj = { kind, id };
    let section = null;
    let buf = [];
    const flush = () => {
      if (section) obj[section] = buf.join("\n").replace(/^\n+|\s+$/g, "");
      buf = [];
    };
    for (const line of lines.slice(1)) {
      const m = /^--- (\w+)\s*$/.exec(line);
      if (m) { flush(); section = m[1]; continue; }
      const late = /^(answer|verify|placeholder):\s*(.*)$/.exec(line);
      if (late) { obj[late[1]] = late[2].trim(); continue; }
      if (section) { buf.push(line); continue; }
      const kv = /^(\w+):\s*(.*)$/.exec(line);
      if (kv) obj[kv[1]] = kv[2].trim();
    }
    flush();
    if (kind === "day") { day = { ...obj, checklist: list(obj.checklist), concepts: [], items: [] }; DAYS.push(day); }
    // concepts are numbered d<day>-c<n>; a named one (`@@ concept intro`) is d<day>-intro and does not shift the numbers
    else if (kind === "concept") { obj.id = id ? `d${day.id}-${id}` : `d${day.id}-c${day.concepts.filter((c) => !c.named).length + 1}`; obj.named = !!id; day.concepts.push(normalize(obj, day)); }
    else if (kind === "item") day.items.push(normalize(obj, day));
    else throw new Error(`${file}: unknown block ${kind}`);
  }
}
const list = (s) => (s ? s.split(/^- /m).map((x) => x.trim()).filter(Boolean) : []);
function normalize(o, day) {
  const out = { ...o, lang: o.lang || day.lang };
  // SQL blocks use the day's dataset unless they name one; Python blocks name it explicitly
  if (out.lang === "sql" && !out.dataset && day.dataset) out.dataset = day.dataset;
  for (const k of ["options", "hints", "checklist"]) if (o[k] !== undefined) out[k] = list(o[k]);
  if (o.answer !== undefined) out.answer = o.answer.split(",").map((x) => Number(x.trim()) - 1);
  for (const k of ["exam", "mock", "cloud", "ordered", "bq"]) out[k] = o[k] === "yes";
  // LangChain / LangGraph (real libraries + the mock DeepSeek server): per block, or for every
  // Python block of a day with `langchain: yes` on the day (a block can opt out with `langchain: no`)
  out.langchain = out.lang === "py" && (o.langchain === "yes" || (o.langchain === undefined && day.langchain === "yes"));
  if (o.level) out.level = Number(o.level);
  if (o.type === "fill") {
    out.solution = o.template.replace(/\[\[(.*?)\]\]/g, "$1");
    out.starter = o.template.replace(/\[\[(.*?)\]\]/g, "");
    out.fills = [...o.template.matchAll(/\[\[(.*?)\]\]/g)].map((m) => m[1]);
  }
  if (o.type === "testwrite") {
    // --- mutants: variants of --- impl, each starting with a "===== clue" line
    out.mutants = (o.mutants || "").split(/^=====[ \t]*/m).slice(1).map((chunk) => {
      const nl = chunk.indexOf("\n");
      return { note: chunk.slice(0, nl).trim(), code: chunk.slice(nl + 1).replace(/\s+$/, "") };
    });
  }
  if (o.type === "order") {
    out.lines = o.lines.split("\n");
    out.distractors = o.distractors ? o.distractors.split("\n") : [];
    out.solution = o.lines;
  }
  delete out.kind;
  return out;
}

const DAYS = [];
const dayNum = (f) => Number(/\d+/.exec(f)[0]);
for (const f of fs.readdirSync(P("content")).filter((f) => /^day\d+\.txt$/.test(f)).sort((a, b) => dayNum(a) - dayNum(b))) parseContent(P("content", f));
// datasets for SQL / database / cloud exercises: content/data/<name>.sql
const DATASETS = {};
if (fs.existsSync(P("content", "data")))
  for (const f of fs.readdirSync(P("content", "data")).filter((f) => f.endsWith(".sql")))
    DATASETS[f.replace(/\.sql$/, "")] = fs.readFileSync(P("content", "data", f), "utf8").replace(/\r\n/g, "\n");

// ---------------------------------------------------------------- runtimes
// Validation runs from node_modules + vendor/, so --day runs never touch dist/.
const WHEELS = fs.readdirSync(P("vendor")).filter((f) => f.endsWith(".whl")).map((f) => f.replace(/\.whl$/, ".wasm"));
// the LangChain week: vendor/lc/ (node fetch-vendor.mjs) holds the libraries and everything they import
const LC_WHEELS = fs.existsSync(P("vendor", "lc")) ? fs.readdirSync(P("vendor", "lc")).filter((f) => f.endsWith(".whl")).map((f) => f.replace(/\.whl$/, ".wasm")) : [];
// tiktoken's encoding file sits in its cache (the name is sha1 of the download URL), so OpenAIEmbeddings works offline
const TIKTOKEN = { file: "cl100k_base.tiktoken.txt", cache: "/tmp/data-gym-cache/9b5ad71b2ce5302211f9c61530b329a4922fc6a4" };
fs.mkdirSync(P("build"), { recursive: true });

const libs = {};
const libDir = P("node_modules", "typescript", "lib");
for (const todo = ["lib.es2022.d.ts"]; todo.length;) {
  const n = todo.pop();
  if (libs[n]) continue;
  libs[n] = fs.readFileSync(path.join(libDir, n), "utf8");
  for (const m of libs[n].matchAll(/<reference lib="([^"]+)"/g)) todo.push(`lib.${m[1].toLowerCase()}.d.ts`);
}
libs["env.d.ts"] = fs.readFileSync(P("src", "harness", "ts_env.d.ts"), "utf8");
libs["zod.d.ts"] = fs.readFileSync(P("src", "harness", "zod_shim.d.ts"), "utf8");

const ZOD_ENTRY = P("build", `zod-entry-${process.pid}.js`);
const ZOD_FILE = P("build", `zod-${process.pid}.iife.js`);
fs.writeFileSync(ZOD_ENTRY, 'export * from "zod";\n');
execFileSync(process.execPath, [P("node_modules", "esbuild", "bin", "esbuild"), ZOD_ENTRY, "--bundle", "--format=iife", "--global-name=Zod", "--minify", `--outfile=${ZOD_FILE}`], { stdio: "ignore" });

const PY_RUNNER = fs.readFileSync(P("src", "harness", "py_runner.py"), "utf8");
const PY_MOCK = fs.readFileSync(P("src", "harness", "py_mock.py"), "utf8");
const TS_RUNTIME = fs.readFileSync(P("src", "harness", "ts_runtime.js"), "utf8");
const PY_DISCOVER = fs.readFileSync(P("src", "harness", "py_discover.py"), "utf8");
const PY_SQL = fs.readFileSync(P("src", "harness", "py_sql.py"), "utf8");
const PY_CLOUD = fs.readFileSync(P("src", "harness", "py_cloud.py"), "utf8");
const PY_LANGCHAIN = fs.readFileSync(P("src", "harness", "py_langchain.py"), "utf8");
const TS_COMPILE = fs.readFileSync(P("src", "harness", "ts_compile.js"), "utf8");
vm.runInThisContext(TS_COMPILE);
const ZOD = fs.readFileSync(ZOD_FILE, "utf8");
for (const f of [ZOD_ENTRY, ZOD_FILE]) fs.rmSync(f, { force: true });

const { loadPyodide } = await import(new URL("file:///" + P("node_modules", "pyodide", "pyodide.mjs").replace(/\\/g, "/")).href);
const py = await loadPyodide({ indexURL: P("node_modules", "pyodide") + path.sep });
const SITE = py.runPython("import site; site.getsitepackages()[0]");
for (const f of WHEELS) py.unpackArchive(new Uint8Array(fs.readFileSync(P("vendor", f.replace(/\.wasm$/, ".whl")))), "wheel", { extractDir: SITE });
py.runPython("import importlib; importlib.invalidate_caches(); import pydantic");
py.runPython(PY_RUNNER);
const loadModule = py.globals.get("_cc_load_module");
loadModule("_ccsql", PY_SQL);
loadModule("_cccloud", PY_CLOUD);
loadModule("_cclc", PY_LANGCHAIN);
const pyRun = py.globals.get("run");
const pySqlRun = py.globals.get("_cc_run_sql");
let lcReady = false;
function ensureLangchain() {
  if (lcReady) return;
  if (!LC_WHEELS.length) throw new Error("vendor/lc/ is missing: run node fetch-vendor.mjs");
  for (const f of LC_WHEELS) py.unpackArchive(new Uint8Array(fs.readFileSync(P("vendor", "lc", f.replace(/\.wasm$/, ".whl")))), "wheel", { extractDir: SITE });
  py.FS.mkdirTree(path.posix.dirname(TIKTOKEN.cache));
  py.FS.writeFile(TIKTOKEN.cache, fs.readFileSync(P("vendor", "lc", "cl100k_base.tiktoken")));
  py.runPython("import importlib; importlib.invalidate_caches(); import _cclc; _cclc.prepare()");
  lcReady = true;
}
// what runs before the learner's Python code: the mock API, a dataset + fresh_db(), the mock cloud,
// LangChain pointed at the mock (the page builds exactly the same string, see pySetup in index.html)
const FRESH_DB = "def fresh_db():\n    import sqlite3\n    conn = sqlite3.connect(':memory:')\n    conn.executescript(DATASET_SQL)\n    return conn\n";
const LC_PREP = "import _cclc\n_cclc.prepare()\n";
function pySetup(o) {
  if (o.langchain) ensureLangchain();
  let s = o.langchain ? LC_PREP : "";
  s += o.mock || o.langchain ? PY_MOCK + "\n" : "";
  if (o.langchain) s += "_cclc.use_mock(MOCK)\n";
  if (o.dataset) {
    if (!(o.dataset in DATASETS)) throw new Error(`${o.id}: unknown dataset ${o.dataset}`);
    s += `DATASET_SQL = ${JSON.stringify(DATASETS[o.dataset])}\n${FRESH_DB}`;
  }
  if (o.cloud) s += `import _cccloud\nCLOUD = _cccloud._cc_cloud_install(${o.dataset ? "DATASET_SQL" : '""'})\n`;
  return s;
}
const runPy = (o, code, tests = "") => JSON.parse(pyRun(code, tests, pySetup(o)));
// testwrite: the learner's tests are main.py; the code under test is loaded first, as setup
const runTestwrite = (o, impl, testCode) => JSON.parse(pyRun(testCode, PY_DISCOVER, pySetup(o) + "\n" + impl));
// SQL: the dataset (plus the item's own --- schema) is the setup; the reference query is the answer
const sqlSetup = (o) => [o.dataset ? DATASETS[o.dataset] : "", o.schema || ""].join("\n");
const sqlSpec = (o, solution) => JSON.stringify({ solution: solution ?? null, check: o.check || null, ordered: !!o.ordered, bq: !!o.bq });
const runSql = (o, code, solution) => JSON.parse(pySqlRun(code, sqlSpec(o, solution), sqlSetup(o)));

function runTs(code, tests = "") {
  const { diagnostics, js } = CCTS.compile(ts, libs, code, tests);
  const job = CCTS.buildJob(TS_RUNTIME, js);
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve({ timeout: true, diagnostics, tests: [] }), 8000);
    const ctx = { setTimeout, clearTimeout, __POST: (m) => { clearTimeout(timer); resolve({ ...m, diagnostics, js }); } };
    vm.createContext(ctx);
    vm.runInContext(ZOD, ctx);
    try { vm.runInContext(job, ctx); }
    catch (e) { clearTimeout(timer); resolve({ error: `${e.name}: ${e.message}`, tests: [], diagnostics, js }); }
  });
}
function realNode(js) {
  const f = P("build", `cc-predict-${process.pid}.cjs`);  // inside the project so require("zod") resolves
  fs.writeFileSync(f, js);
  try { return execFileSync(process.execPath, [f], { encoding: "utf8", timeout: 8000 }).replace(/\n$/, ""); }
  catch (e) { return "ERROR: " + (e.stderr || e.message).split("\n").slice(0, 6).join("\n"); }
  finally { fs.rmSync(f, { force: true }); }
}

// ---------------------------------------------------------------- validate
const problems = [];
let checked = 0;
const bad = (id, msg) => problems.push(`${id}: ${msg}`);
const allPass = (r) => !r.error && !(r.diagnostics || []).length && r.tests.length > 0 && r.tests.every((t) => t.passed);
const summary = (r) => r.error || (r.diagnostics || []).map((d) => `L${d.line} ${d.message}`).join("; ") || r.tests.filter((t) => !t.passed).map((t) => `${t.label} got=${t.got} exp=${t.expected} ${t.error || ""}`).join(" | ") || "(no tests)";

async function run(o, code, tests) {
  if (o.lang === "sql") return runSql(o, code, o.type === "predict" || !o.solution ? null : o.solution);
  return o.lang === "py" ? runPy(o, code, tests) : await runTs(code, tests);
}
// table info for the schema panel of SQL items: one entry per dataset (+ the item's own tables)
const TABLES = {};
const tableInfo = py.runPython(`
import json, sqlite3
def _cc_table_info(setup):
    conn = sqlite3.connect(":memory:")
    conn.executescript(setup)
    out = []
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY rowid"):
        cols = [{"name": c[1], "type": c[2]} for c in conn.execute(f"PRAGMA table_info({name})")]
        cur = conn.execute(f"SELECT * FROM {name} LIMIT 3")
        out.append({"name": name, "columns": cols, "count": conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0],
                    "sample": [list(r) for r in cur.fetchall()]})
    return json.dumps(out)
_cc_table_info
`);
function tablesKey(o) {
  if (o.lang !== "sql") return null;
  const key = o.schema ? `${o.dataset || ""}+${o.id}` : o.dataset || null;
  if (key && !TABLES[key]) TABLES[key] = JSON.parse(tableInfo(sqlSetup(o)));
  return key;
}

// LangChain code that passes in the browser but not on a normal machine (the browser has one thread
// and no event loop of its own), checked on every code field of the item
function lintLangchain(o) {
  const code = ["code", "starter", "solution", "tests", "impl", "template", "lines"].map((k) => o[k] || "").join("\n");
  if (/SqliteSaver\s*\(\s*sqlite3\.connect\((?![^)]*check_same_thread\s*=\s*False)/.test(code) || /sqlite3\.connect\((?![^)]*check_same_thread\s*=\s*False)[^)]*\)[\s\S]*SqliteSaver\s*\(/.test(code))
    bad(o.id, "SqliteSaver(sqlite3.connect(...)) needs check_same_thread=False: real LangGraph writes checkpoints from another thread (or use SqliteSaver.from_conn_string)");
  if (/\basyncio\.run\(|^\s*await\s|\bainvoke\(|\bastream\(|\babatch\(/m.test(code))
    bad(o.id, "async LangChain calls cannot run in the browser runtime (no asyncio.run); show them in concept text only");
}
for (const day of DAYS) for (const c of day.concepts) if (c.langchain && c.code) lintLangchain(c);

// ---------------------------------------------------------------- context, cards, checks
// `--- context`: a few sentences of background above the task. `cards: 字符串; d1:列表` names the knowledge
// cards the item uses (same day by title, another day as dN:title); the page links them. `checks` is what the
// grader looks at, shown before the first run: every expect line's label, plus the call and the value when the
// line calls the learner's own function with nothing the tests define.
const conceptByTitle = (dayId, title) => (DAYS.find((d) => Number(d.id) === Number(dayId))?.concepts || []).find((c) => c.title === title);
function splitTop(s) {
  const out = [];
  let depth = 0, quote = null, cur = "";
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    cur += ch;
    if (quote) { if (ch === "\\") cur += s[++i] ?? ""; else if (ch === quote) quote = null; continue; }
    if (ch === '"' || ch === "'" || ch === "`") quote = ch;
    else if ("([{".includes(ch)) depth++;
    else if (")]}".includes(ch)) depth--;
    else if (ch === "," && depth === 0) { out.push(cur.slice(0, -1).trim()); cur = ""; }
  }
  if (quote || depth) return null;
  if (cur.trim()) out.push(cur.trim());
  return out;
}
const unquote = (s) => { const m = /^[rf]?(["'`])([\s\S]*)\1$/.exec(s); return m ? m[2].replace(/\\(["'\\])/g, "$1") : s; };
function checksOf(it) {
  if (!it.tests || !["code", "fix", "fill", "order", "scratch"].includes(it.type) || it.lang === "sql") return [];
  const own = new Set();
  for (const m of (it.solution || "").matchAll(/^(?:export\s+)?(?:async\s+)?(?:def|class|function|const|let)\s+(\w+)/gm)) own.add(m[1]);
  const theirs = new Set(["MOCK", "_cc", "mock"]);
  for (const m of it.tests.matchAll(/^(?:(?:async\s+)?(?:def|class|function|const|let|var)\s+(\w+)|(\w+)\s*(?::[^=\n]*)?=(?!=))/gm)) theirs.add(m[1] || m[2]);
  const out = [];
  for (const line of it.tests.split("\n")) {
    const head = /^(expect\w*)\(/.exec(line);
    if (!head) continue;
    const args = splitTop(line.slice(head[0].length).replace(/\)\s*;?\s*$/, ""));
    const label = args && args[0] ? unquote(args[0]) : (/^\w+\(\s*[rf]?(["'])(.*?)\1/.exec(line) || [])[2];
    if (!label) continue;
    const check = { label };
    const kind = head[1];
    if (args && /^(expect|expect_raises|expectThrows)$/.test(kind) && args.length === (kind === "expectThrows" ? 2 : 3)) {
      const call = args[1].replace(/^lambda\s*:\s*/, "").replace(/^\(\)\s*=>\s*/, "");
      const value = kind === "expect" ? args[2] : kind === "expect_raises" ? `报错 ${args[2]}` : "报错";
      const fn = /^(\w+)\s*\(/.exec(call);
      const words = (call + " " + (kind === "expect" ? value : "")).match(/[A-Za-z_]\w*/g) || [];
      if (fn && own.has(fn[1]) && !words.some((w) => theirs.has(w)) && call.length <= 110 && value.length <= 90 && !/^async|await /.test(call)) Object.assign(check, { call, value });
    }
    out.push(check);
  }
  return out;
}
for (const day of DAYS) for (const it of day.items) {
  if (it.context !== undefined) {
    if (!it.context.trim()) bad(it.id, "empty --- context");
    else if ([...it.context].length > 240) bad(it.id, `--- context is ${[...it.context].length} characters; keep it to a few sentences (max 240)`);
  }
  if (it.cards !== undefined) {
    it.cardIds = [];
    for (const ref of it.cards.split(";").map((s) => s.trim()).filter(Boolean)) {
      const m = /^d(\d+):\s*(.+)$/.exec(ref);
      const c = m ? conceptByTitle(m[1], m[2].trim()) : conceptByTitle(day.id, ref);
      if (!c) bad(it.id, `cards: no knowledge card titled "${m ? m[2].trim() : ref}" on day ${m ? m[1] : day.id}`);
      else if (m && Number(m[1]) > Number(day.id)) bad(it.id, `cards: "${ref}" is on a later day`);
      else if (!it.cardIds.includes(c.id)) it.cardIds.push(c.id);
    }
    delete it.cards;
  }
  it.checks = checksOf(it);
}

const ids = new Set();
for (const day of DAYS) {
  const validate = onlyDays === null || onlyDays.has(Number(day.id));
  for (const c of day.concepts) {
    if (!validate || !c.code) continue;
    const r = await run(c, c.code, "");
    c.tables = tablesKey(c);
    checked++;
    if (SHOW) console.log(`--- ${c.id} ${c.title}\n${r.stdout || ""}${r.error || ""}${(r.diagnostics || []).map((d) => `L${d.line} ${d.message}`).join("\n")}`);
    if (c.error_demo === "yes") { if (!r.error && !(r.diagnostics || []).length) bad(c.id, "error demo did not error"); }
    else if (r.error || (r.diagnostics || []).length) bad(c.id, "concept example fails: " + summary(r));
  }
  for (const it of day.items) {
    if (ids.has(it.id)) bad(it.id, "duplicate id");
    ids.add(it.id);
    if (!it.title || !it.type) bad(it.id, "missing title/type");
    if (!validate) continue;
    checked++;
    const t = it.type;
    if (it.langchain) lintLangchain(it);
    if (t === "choice") {
      if (!it.options?.length || !it.answer?.length || it.answer.some((a) => a < 0 || a >= it.options.length)) bad(it.id, "bad options/answer");
      if (!it.explain) bad(it.id, "missing explain");
      continue;
    }
    it.tables = tablesKey(it);
    if (it.lang === "sql" && t === "order" && !it.tests) {
      // judged by line order only, but the correct order must still be a working query
      const r = runSql(it, it.solution, null);
      if (r.error) bad(it.id, "the correct line order is not a valid query: " + r.error.split("\n").pop());
      continue;
    }
    if (it.lang === "sql" && t !== "choice" && t !== "local" && !(t === "order" && !it.tests)) {
      if (!["sql", "fill", "order"].includes(t)) { bad(it.id, `SQL items are type sql / fill / order, not ${t}`); continue; }
      if (!it.solution) { bad(it.id, "SQL item needs --- solution"); continue; }
      const sol = runSql(it, it.solution, it.solution);
      if (!allPass(sol)) { bad(it.id, "SOLUTION fails: " + summary(sol)); continue; }
      if (!sol.table.rows.length && it.allow_empty !== "yes") bad(it.id, "solution returns no rows (set allow_empty: yes if that is the point)");
      it.expected_table = sol.expected_table;
      if (SHOW) console.log(`--- ${it.id} ${it.title}\n${sol.stdout}`);
      const starter = it.starter;
      if (starter !== undefined && starter.trim() && it.skip_starter !== "yes") {
        const st = runSql(it, starter, it.solution);
        if (allPass(st)) bad(it.id, "STARTER already passes");
      }
      if (t === "sql" && it.exam && it.starter) bad(it.id, "exam items have no starter");
      continue;
    }
    if (t === "predict") {
      const r = await run(it, it.code, "");
      if (r.error || (r.diagnostics || []).length) { bad(it.id, "predict code errors: " + summary(r)); continue; }
      it.expected = r.stdout.replace(/\s+$/, "");
      if (!it.expected) bad(it.id, "predict prints nothing");
      // the answer must not depend on the run (message ids, interrupt ids, timings, random jitter)
      if (it.lang === "py") {
        const again = (await run(it, it.code, "")).stdout.replace(/\s+$/, "");
        if (again !== it.expected) bad(it.id, `predict output differs between two runs:\n  1: ${JSON.stringify(it.expected).slice(0, 300)}\n  2: ${JSON.stringify(again).slice(0, 300)}`);
      }
      if (SHOW) console.log(`--- ${it.id} ${it.title}\n${it.expected}`);
      if (it.lang === "ts") {
        const real = realNode(r.js);
        const norm = (x) => x.split("\n").map((l) => l.replace(/\s+$/, "")).join("\n");
        if (norm(real) !== norm(it.expected)) bad(it.id, `console shim differs from Node:\n  shim: ${JSON.stringify(it.expected)}\n  node: ${JSON.stringify(real)}`);
      }
      continue;
    }
    if (t === "local") { if (!it.verify) bad(it.id, "local task needs verify"); continue; }
    if (t === "testwrite") {
      if (it.lang !== "py") { bad(it.id, "testwrite is Python only"); continue; }
      if (!it.impl || !it.mutants.length || !it.solution || it.starter === undefined) { bad(it.id, "testwrite needs impl, mutants, solution (reference tests) and starter"); continue; }
      const onImpl = runTestwrite(it, it.impl, it.solution);
      if (!allPass(onImpl)) bad(it.id, "reference tests fail on the correct impl: " + summary(onImpl));
      it.mutants.forEach((m, i) => {
        if (!m.note) bad(it.id, `mutant ${i + 1} has no clue after =====`);
        const r = runTestwrite(it, m.code, it.solution);
        if (r.error) bad(it.id, `mutant ${i + 1} does not even load: ${r.error.split("\n").pop()}`);
        else if (allPass(r)) bad(it.id, `reference tests miss mutant ${i + 1} (${m.note})`);
      });
      const st = runTestwrite(it, it.impl, it.starter);
      if (allPass(st) && it.mutants.every((m) => !allPass(runTestwrite(it, m.code, it.starter)))) bad(it.id, "STARTER tests already catch every mutant");
      continue;
    }
    if (t === "order" && !it.tests) continue;
    if (!it.tests) { bad(it.id, "missing tests"); continue; }
    const sol = await run(it, it.solution, it.tests);
    if (!allPass(sol)) bad(it.id, "SOLUTION fails: " + summary(sol));
    else if (sol.tests.length < 2 && !it.exam) bad(it.id, "fewer than 2 tests");
    if (t === "order") {
      const scrambled = [...it.lines].reverse().join("\n");
      const r = await run(it, scrambled, it.tests);
      if (allPass(r)) bad(it.id, "reversed order also passes");
      continue;
    }
    if (it.starter !== undefined && it.skip_starter !== "yes") {
      const st = await run(it, it.starter, it.tests);
      if (allPass(st)) bad(it.id, "STARTER already passes");
    } else if (t !== "scratch" && it.starter === undefined) bad(it.id, "missing starter");
  }
}

// ---------------------------------------------------------------- report + emit
const counts = DAYS.map((d) => `D${d.id}:${d.items.length}+${d.concepts.length}c`).join(" ");
console.log(`checked ${checked} | ${counts} | items ${DAYS.reduce((n, d) => n + d.items.length, 0)}`);
const allItems = DAYS.flatMap((d) => d.items);
console.log(`context ${allItems.filter((it) => it.context).length}/${allItems.length} | cards ${allItems.filter((it) => it.cardIds?.length).length} | checks with a call ${allItems.filter((it) => it.checks.some((c) => c.call)).length}/${allItems.filter((it) => it.checks.length).length}`);
if (problems.length) { console.log(`\n${problems.length} PROBLEM(S):\n- ` + problems.join("\n- ")); process.exitCode = 1; }
else console.log(EMIT ? "all exercises valid" : `day ${[...onlyDays].join(",")} valid (validation only, dist/ not written)`);
if (!EMIT) process.exit();

fs.rmSync(DIST, { recursive: true, force: true });
fs.mkdirSync(P("dist", "pyodide", "pkg"), { recursive: true });
// The artifact host serves no .zip/.whl, so archives ship under a binary-safe .wasm name:
// the stdlib is loaded via stdLibURL, the Pydantic wheels are unpacked into site-packages.
for (const f of ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "pyodide-lock.json"])
  fs.copyFileSync(P("node_modules", "pyodide", f), P("dist", "pyodide", f));
fs.copyFileSync(P("node_modules", "pyodide", "python_stdlib.zip"), P("dist", "pyodide", "python_stdlib.wasm"));
for (const f of WHEELS) fs.copyFileSync(P("vendor", f.replace(/\.wasm$/, ".whl")), P("dist", "pyodide", "pkg", f));
for (const f of LC_WHEELS) fs.copyFileSync(P("vendor", "lc", f.replace(/\.wasm$/, ".whl")), P("dist", "pyodide", "pkg", f));
if (LC_WHEELS.length) fs.copyFileSync(P("vendor", "lc", "cl100k_base.tiktoken"), P("dist", "pyodide", "pkg", TIKTOKEN.file));
fs.writeFileSync(P("dist", "zod.iife.js"), ZOD);
const course = { builtAt: new Date().toISOString(), days: DAYS, datasets: DATASETS, tables: TABLES };
fs.writeFileSync(P("dist", "course.js"), "window.CC_COURSE = " + JSON.stringify(course) + ";\n");
fs.writeFileSync(P("dist", "harness.js"), [
  "window.CC_HARNESS = " + JSON.stringify({ PY_RUNNER, PY_MOCK, PY_DISCOVER, PY_SQL, PY_CLOUD, PY_LANGCHAIN, TS_RUNTIME, WHEELS, LC_WHEELS, TIKTOKEN }) + ";",
  TS_COMPILE,
].join("\n"));
fs.writeFileSync(P("dist", "ts-libs.json"), JSON.stringify(libs));
const CM_CSS = fs.readFileSync(P("node_modules", "codemirror", "lib", "codemirror.css"), "utf8");
fs.writeFileSync(P("dist", "index.html"), fs.readFileSync(P("src", "index.html"), "utf8").replace("/*CODEMIRROR_CSS*/", () => CM_CSS));
console.log("dist/ written");
