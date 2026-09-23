// Build the 7-day course site into dist/.
//   node build.mjs            parse content, validate every exercise, emit dist/
//   node build.mjs --day 3    validate only day 3 (still emits everything)
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
const onlyDay = process.argv.includes("--day") ? Number(process.argv[process.argv.indexOf("--day") + 1]) : null;

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
    else if (kind === "concept") { obj.id = `d${day.id}-c${day.concepts.length + 1}`; day.concepts.push(normalize(obj, day)); }
    else if (kind === "item") day.items.push(normalize(obj, day));
    else throw new Error(`${file}: unknown block ${kind}`);
  }
}
const list = (s) => (s ? s.split(/^- /m).map((x) => x.trim()).filter(Boolean) : []);
function normalize(o, day) {
  const out = { ...o, lang: o.lang || day.lang };
  for (const k of ["options", "hints", "checklist"]) if (o[k] !== undefined) out[k] = list(o[k]);
  if (o.answer !== undefined) out.answer = o.answer.split(",").map((x) => Number(x.trim()) - 1);
  for (const k of ["exam", "mock"]) out[k] = o[k] === "yes";
  if (o.level) out.level = Number(o.level);
  if (o.type === "fill") {
    out.solution = o.template.replace(/\[\[(.*?)\]\]/g, "$1");
    out.starter = o.template.replace(/\[\[(.*?)\]\]/g, "");
    out.fills = [...o.template.matchAll(/\[\[(.*?)\]\]/g)].map((m) => m[1]);
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
for (const f of fs.readdirSync(P("content")).filter((f) => /^day\d+\.txt$/.test(f)).sort()) parseContent(P("content", f));

// ---------------------------------------------------------------- dist + runtimes
fs.rmSync(DIST, { recursive: true, force: true });
fs.mkdirSync(P("dist", "pyodide"), { recursive: true });
// The artifact host serves no .zip/.whl, so archives ship under a binary-safe .wasm name:
// the stdlib is loaded via stdLibURL, the Pydantic wheels are unpacked into site-packages.
for (const f of ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "pyodide-lock.json"])
  fs.copyFileSync(P("node_modules", "pyodide", f), P("dist", "pyodide", f));
fs.copyFileSync(P("node_modules", "pyodide", "python_stdlib.zip"), P("dist", "pyodide", "python_stdlib.wasm"));
fs.mkdirSync(P("dist", "pyodide", "pkg"), { recursive: true });
const WHEELS = fs.readdirSync(P("vendor")).filter((f) => f.endsWith(".whl")).map((f) => f.replace(/\.whl$/, ".wasm"));
for (const f of WHEELS) fs.copyFileSync(P("vendor", f.replace(/\.wasm$/, ".whl")), P("dist", "pyodide", "pkg", f));

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

fs.writeFileSync(P("build", "zod-entry.js"), 'export * from "zod";\n');
execFileSync(process.execPath, [P("node_modules", "esbuild", "bin", "esbuild"), P("build", "zod-entry.js"), "--bundle", "--format=iife", "--global-name=Zod", "--minify", `--outfile=${P("dist", "zod.iife.js")}`], { stdio: "ignore" });

const PY_RUNNER = fs.readFileSync(P("src", "harness", "py_runner.py"), "utf8");
const PY_MOCK = fs.readFileSync(P("src", "harness", "py_mock.py"), "utf8");
const TS_RUNTIME = fs.readFileSync(P("src", "harness", "ts_runtime.js"), "utf8");
const TS_COMPILE = fs.readFileSync(P("src", "harness", "ts_compile.js"), "utf8");
vm.runInThisContext(TS_COMPILE);
const ZOD = fs.readFileSync(P("dist", "zod.iife.js"), "utf8");

const { loadPyodide } = await import(new URL("file:///" + P("dist", "pyodide", "pyodide.mjs").replace(/\\/g, "/")).href);
const py = await loadPyodide({ indexURL: P("dist", "pyodide") + path.sep, stdLibURL: P("dist", "pyodide", "python_stdlib.wasm") });
const SITE = py.runPython("import site; site.getsitepackages()[0]");
for (const f of WHEELS) py.unpackArchive(new Uint8Array(fs.readFileSync(P("dist", "pyodide", "pkg", f))), "wheel", { extractDir: SITE });
py.runPython("import importlib; importlib.invalidate_caches(); import pydantic");
py.runPython(PY_RUNNER);
const pyRun = py.globals.get("run");
const runPy = (code, tests = "", mock = false) => JSON.parse(pyRun(code, tests, mock ? PY_MOCK : ""));

function runTs(code, tests = "") {
  const { diagnostics, js } = CCTS.compile(ts, libs, code, tests);
  const job = CCTS.buildJob(TS_RUNTIME, js);
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve({ timeout: true, diagnostics, tests: [] }), 8000);
    const ctx = { setTimeout, __POST: (m) => { clearTimeout(timer); resolve({ ...m, diagnostics, js }); } };
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
}

// ---------------------------------------------------------------- validate
const problems = [];
let checked = 0;
const bad = (id, msg) => problems.push(`${id}: ${msg}`);
const allPass = (r) => !r.error && !(r.diagnostics || []).length && r.tests.length > 0 && r.tests.every((t) => t.passed);
const summary = (r) => r.error || (r.diagnostics || []).map((d) => `L${d.line} ${d.message}`).join("; ") || r.tests.filter((t) => !t.passed).map((t) => `${t.label} got=${t.got} exp=${t.expected} ${t.error || ""}`).join(" | ") || "(no tests)";

async function run(lang, code, tests, mock) { return lang === "py" ? runPy(code, tests, mock) : await runTs(code, tests); }

const ids = new Set();
for (const day of DAYS) {
  const validate = onlyDay === null || Number(day.id) === onlyDay;
  for (const c of day.concepts) {
    if (!validate || !c.code) continue;
    const r = await run(c.lang, c.code, "", c.mock);
    checked++;
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
    if (t === "choice") {
      if (!it.options?.length || !it.answer?.length || it.answer.some((a) => a < 0 || a >= it.options.length)) bad(it.id, "bad options/answer");
      if (!it.explain) bad(it.id, "missing explain");
      continue;
    }
    if (t === "predict") {
      const r = await run(it.lang, it.code, "", it.mock);
      if (r.error || (r.diagnostics || []).length) { bad(it.id, "predict code errors: " + summary(r)); continue; }
      it.expected = r.stdout.replace(/\s+$/, "");
      if (!it.expected) bad(it.id, "predict prints nothing");
      if (it.lang === "ts") {
        const real = realNode(r.js);
        const norm = (x) => x.split("\n").map((l) => l.replace(/\s+$/, "")).join("\n");
        if (norm(real) !== norm(it.expected)) bad(it.id, `console shim differs from Node:\n  shim: ${JSON.stringify(it.expected)}\n  node: ${JSON.stringify(real)}`);
      }
      continue;
    }
    if (t === "local") { if (!it.verify) bad(it.id, "local task needs verify"); continue; }
    if (t === "order" && !it.tests) continue;
    if (!it.tests) { bad(it.id, "missing tests"); continue; }
    const sol = await run(it.lang, it.solution, it.tests, it.mock);
    if (!allPass(sol)) bad(it.id, "SOLUTION fails: " + summary(sol));
    else if (sol.tests.length < 2 && !it.exam) bad(it.id, "fewer than 2 tests");
    if (t === "order") {
      const scrambled = [...it.lines].reverse().join("\n");
      const r = await run(it.lang, scrambled, it.tests, it.mock);
      if (allPass(r)) bad(it.id, "reversed order also passes");
      continue;
    }
    if (it.starter !== undefined && it.skip_starter !== "yes") {
      const st = await run(it.lang, it.starter, it.tests, it.mock);
      if (allPass(st)) bad(it.id, "STARTER already passes");
    } else if (t !== "scratch" && it.starter === undefined) bad(it.id, "missing starter");
  }
}

// ---------------------------------------------------------------- emit
const course = { builtAt: new Date().toISOString(), days: DAYS };
fs.writeFileSync(P("dist", "course.js"), "window.CC_COURSE = " + JSON.stringify(course) + ";\n");
fs.writeFileSync(P("dist", "harness.js"), [
  "window.CC_HARNESS = " + JSON.stringify({ PY_RUNNER, PY_MOCK, TS_RUNTIME, WHEELS }) + ";",
  TS_COMPILE,
].join("\n"));
fs.writeFileSync(P("dist", "ts-libs.json"), JSON.stringify(libs));
const CM_CSS = fs.readFileSync(P("node_modules", "codemirror", "lib", "codemirror.css"), "utf8");
fs.writeFileSync(P("dist", "index.html"), fs.readFileSync(P("src", "index.html"), "utf8").replace("/*CODEMIRROR_CSS*/", () => CM_CSS));

const counts = DAYS.map((d) => `D${d.id}:${d.items.length}+${d.concepts.length}c`).join(" ");
console.log(`checked ${checked} | ${counts} | items ${DAYS.reduce((n, d) => n + d.items.length, 0)}`);
if (problems.length) { console.log(`\n${problems.length} PROBLEM(S):\n- ` + problems.join("\n- ")); process.exitCode = 1; }
else console.log("all exercises valid");
