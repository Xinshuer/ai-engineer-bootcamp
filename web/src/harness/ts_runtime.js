// Runtime prelude for TypeScript exercises. Inserted inside an async function that
// receives (__post, __Zod). Runs in a Web Worker (browser) or a Node vm (validator).
// Mirrors py_mock.py for the mock DeepSeek server. Keep the two in sync.
const __out = [];
const __tests = [];
const __pending = [];

function __isIdent(k) { return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(k); }
function __quote(s) {
  const q = s.includes("'") && !s.includes('"') ? '"' : "'";
  const body = s.replace(/\\/g, "\\\\").replace(/\n/g, "\\n");
  return q + (q === "'" ? body.replace(/'/g, "\\'") : body) + q;
}
function __fmt(v, depth = 0, nested = false) {
  if (typeof v === "string") return nested ? __quote(v) : v;
  if (typeof v === "number") return Object.is(v, -0) ? "-0" : String(v);
  if (typeof v === "bigint") return String(v) + "n";
  if (v === null || v === undefined || typeof v === "boolean") return String(v);
  if (typeof v === "symbol") return v.toString();
  if (typeof v === "function") {
    const kind = v.constructor && v.constructor.name === "AsyncFunction" ? "AsyncFunction" : (/^class\s/.test(Function.prototype.toString.call(v)) ? "class" : "Function");
    if (kind === "class") return `[class ${v.name || "(anonymous)"}]`;
    return v.name ? `[${kind}: ${v.name}]` : `[${kind} (anonymous)]`;
  }
  if (v instanceof Error) return v.stack ? `${v.name}: ${v.message}` : String(v);
  if (typeof Promise !== "undefined" && v instanceof Promise) return "Promise { <pending> }";
  if (Array.isArray(v)) {
    if (v.length === 0) return "[]";
    if (depth > 2) return "[Array]";
    return "[ " + v.map((x) => __fmt(x, depth + 1, true)).join(", ") + " ]";
  }
  if (v instanceof Map) {
    if (depth > 2) return "[Map]";
    const parts = [...v].map(([k, x]) => `${__fmt(k, depth + 1, true)} => ${__fmt(x, depth + 1, true)}`);
    return `Map(${v.size}) ` + (parts.length ? "{ " + parts.join(", ") + " }" : "{}");
  }
  if (v instanceof Set) {
    if (depth > 2) return "[Set]";
    const parts = [...v].map((x) => __fmt(x, depth + 1, true));
    return `Set(${v.size}) ` + (parts.length ? "{ " + parts.join(", ") + " }" : "{}");
  }
  const proto = Object.getPrototypeOf(v);
  const name = proto && proto.constructor && proto.constructor.name !== "Object" ? proto.constructor.name + " " : "";
  const keys = Object.keys(v);
  if (keys.length === 0) return name + "{}";
  if (depth > 2) return "[Object]";
  return name + "{ " + keys.map((k) => `${__isIdent(k) ? k : __quote(k)}: ${__fmt(v[k], depth + 1, true)}`).join(", ") + " }";
}
function __log(...args) { __out.push(args.map((a) => __fmt(a)).join(" ")); }
const console = { log: __log, info: __log, warn: __log, error: __log, debug: __log };

function __deepEqual(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a !== typeof b || a === null || b === null || typeof a !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) return a.length === b.length && a.every((x, i) => __deepEqual(x, b[i]));
  const ka = Object.keys(a).filter((k) => a[k] !== undefined).sort();
  const kb = Object.keys(b).filter((k) => b[k] !== undefined).sort();
  return ka.length === kb.length && ka.every((k, i) => k === kb[i] && __deepEqual(a[k], b[k]));
}
function __errText(e) {
  if (e && typeof e === "object" && "message" in e) return `${e.name || "Error"}: ${e.message}`;
  return "Uncaught " + __fmt(e, 0, true);
}
const __PROMISE_HINT = "返回的是 Promise：这个函数是 async 的，测试拿到的是还没完成的结果";
function __rec(label) { const r = { label, passed: false }; __tests.push(r); return r; }
function __withTimeout(p, ms) {
  return Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error(`超时：${ms / 1000} 秒内没有结果（是不是忘了 await 或 return？）`)), ms))]);
}

function expect(label, fn, expected) {
  const r = __rec(label);
  try {
    const got = fn();
    if (got instanceof Promise) { r.got = "Promise"; r.error = __PROMISE_HINT; return; }
    r.got = __fmt(got, 0, true); r.expected = __fmt(expected, 0, true);
    r.passed = __deepEqual(got, expected);
  } catch (e) { r.error = __errText(e); }
}
function expectTrue(label, fn) {
  const r = __rec(label);
  try { const got = fn(); r.got = __fmt(got, 0, true); r.passed = Boolean(got) && !(got instanceof Promise); }
  catch (e) { r.error = __errText(e); }
}
function expectThrows(label, fn) {
  const r = __rec(label); r.expected = "抛出错误";
  try { const got = fn(); r.got = "没有报错，返回了 " + __fmt(got, 0, true); }
  catch (e) { r.passed = true; r.got = "抛出了 " + __errText(e); }
}
function expectOutput(label, fn, expected) {
  const r = __rec(label);
  const start = __out.length;
  try {
    fn();
    const got = __out.splice(start).join("\n");
    r.got = got; r.expected = expected; r.passed = got === expected.replace(/\n+$/, "");
  } catch (e) { __out.splice(start); r.error = __errText(e); }
}
// async expectations run one after another (they share MOCK state), in the order written
let __chain = Promise.resolve();
function __queue(task) { __chain = __chain.then(task); __pending.push(__chain); }
function expectAsync(label, fn, expected) {
  const r = __rec(label);
  __queue(async () => {
    try {
      const got = await __withTimeout(Promise.resolve().then(fn), 3000);
      r.got = __fmt(got, 0, true); r.expected = __fmt(expected, 0, true);
      r.passed = __deepEqual(got, expected);
    } catch (e) { r.error = __errText(e); }
  });
}
function expectTrueAsync(label, fn) {
  const r = __rec(label);
  __queue(async () => {
    try { const got = await __withTimeout(Promise.resolve().then(fn), 3000); r.got = __fmt(got, 0, true); r.passed = Boolean(got); }
    catch (e) { r.error = __errText(e); }
  });
}
function expectRejects(label, fn) {
  const r = __rec(label); r.expected = "抛出错误（Promise 被 reject）";
  __queue(async () => {
    try { const got = await __withTimeout(Promise.resolve().then(fn), 3000); r.got = "没有报错，返回了 " + __fmt(got, 0, true); }
    catch (e) { r.passed = !String(e && e.message).startsWith("超时"); r.got = "抛出了 " + __errText(e); }
  });
}

// ---- mock DeepSeek server (mirror of py_mock.py) ----
const __RULES = [
  ["unlimited", "redline", "high", "liability_cap"],
  ["any country", "redline", "high", "data_processing"],
  ["perpetuity", "redline", "medium", "confidentiality"],
  ["twenty-four", "redline", "medium", "auto_renewal"],
  ["without notice", "flag", "medium", "payment"],
  ["subject to section", "flag", "high", "liability_cap"],
];
const __TOPICS = [["liabil", "liability_cap"], ["renew", "auto_renewal"], ["data", "data_processing"], ["fee", "payment"], ["pay", "payment"], ["confiden", "confidentiality"], ["terminat", "termination"]];
const __STATUS_TEXT = { 429: "Rate limit reached, please retry later", 500: "Internal server error", 503: "Service unavailable" };
function __rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const MOCK = {
  calls: [], queue: [], lastSystem: null, random: __rng(7),
  reset(seed = 7) { this.calls = []; this.queue = []; this.lastSystem = null; this.random = __rng(seed); },
  seed(n) { this.random = __rng(n); },
  failNext(status, times = 1) { for (let i = 0; i < times; i++) this.queue.push(status); },
  judge(text) {
    const low = text.toLowerCase();
    const m = /clause\s+(\d+(?:\.\d+)*)/i.exec(text);
    const clause_id = m ? m[1] : "unknown";
    if (low.includes("as is")) {
      const verdict = this.random() < 0.6 ? "accept" : "flag";
      return { clause_id, verdict, risk_level: "low", topic: "other", rationale: "Mock review: mutual 'AS IS' disclaimer; the mock is unsure on purpose." };
    }
    for (const [kw, verdict, risk, topic] of __RULES) {
      if (low.includes(kw)) return { clause_id, verdict, risk_level: risk, topic, rationale: `Mock review: matched '${kw}'.` };
    }
    return { clause_id, verdict: "accept", risk_level: "low", topic: "other", rationale: "Mock review: nothing unusual found." };
  },
  handle(url, headers, body) {
    this.calls.push({ url, body });
    const err = (status, message, type) => [status, { error: { message, type } }];
    if (!String(url).endsWith("/chat/completions")) return err(404, "Not Found: the URL should end with /chat/completions", "not_found");
    headers = headers || {};
    const auth = headers.Authorization || headers.authorization || "";
    if (!String(auth).startsWith("Bearer sk-")) return err(401, "Authentication Fails: send the header Authorization: Bearer <your key>", "authentication_error");
    if (this.queue.length) { const s = this.queue.shift(); return err(s, __STATUS_TEXT[s] || "error", "server_error"); }
    if (!body || typeof body !== "object" || typeof body.model !== "string" || !Array.isArray(body.messages) || body.messages.length === 0)
      return err(400, "Invalid request: the body needs 'model' (a string) and 'messages' (a non-empty list)", "invalid_request_error");
    if (!["deepseek-chat", "deepseek-reasoner"].includes(body.model)) return err(400, `Model Not Exist: ${body.model}`, "invalid_request_error");
    const messages = body.messages;
    for (let i = 0; i < messages.length; i++) {
      const m = messages[i];
      if (!m || typeof m !== "object" || !["system", "user", "assistant", "tool"].includes(m.role))
        return err(400, `Invalid message at index ${i}: needs a 'role' of system/user/assistant/tool`, "invalid_request_error");
      if (m.role !== "assistant" && typeof m.content !== "string")
        return err(400, `Invalid message at index ${i}: 'content' must be a string`, "invalid_request_error");
    }
    const sys = (messages.find((m) => m.role === "system") || {}).content || "";
    const cacheHit = sys && sys === this.lastSystem ? Math.floor(sys.length / 4) : 0;
    this.lastSystem = sys;
    const promptTokens = Math.floor(messages.map((m) => m.content || "").join("").length / 4) + 8;
    const userText = ([...messages].reverse().find((m) => m.role === "user") || {}).content || "";
    const tools = body.tools || [];
    const toolMsgs = messages.filter((m) => m.role === "tool");
    const fmt = (body.response_format || {}).type;
    let message, finish = "stop";
    if (tools.length && !toolMsgs.length) {
      const low = userText.toLowerCase();
      const hit = __TOPICS.find(([kw]) => low.includes(kw));
      const name = (tools[0].function || {}).name || "tool";
      message = { role: "assistant", content: "", tool_calls: [{ id: "call_1", type: "function", function: { name, arguments: JSON.stringify({ topic: hit ? hit[1] : "other" }) } }] };
      finish = "tool_calls";
    } else {
      let content;
      if (fmt === "json_object") {
        content = JSON.stringify(this.judge(userText));
        if (userText.includes("[bad-json]")) content = "Sure! Here is the JSON you asked for:\n" + content;
      } else if (toolMsgs.length) {
        content = "Based on the playbook: " + String(toolMsgs[toolMsgs.length - 1].content).slice(0, 80);
      } else {
        content = "Mock reply: " + userText.slice(0, 60);
      }
      message = { role: "assistant", content };
    }
    const completionTokens = Math.floor((message.content || "").length / 4) + 5;
    return [200, {
      id: `mock-${this.calls.length}`, object: "chat.completion", model: body.model,
      choices: [{ index: 0, message, finish_reason: finish }],
      usage: { prompt_tokens: promptTokens, completion_tokens: completionTokens, total_tokens: promptTokens + completionTokens, prompt_cache_hit_tokens: cacheHit, prompt_cache_miss_tokens: promptTokens - cacheHit },
    }];
  },
};
function __response(status, payload) {
  const text = JSON.stringify(payload);
  return { ok: status >= 200 && status < 300, status, statusText: String(status), headers: { get: () => "application/json" }, json: async () => JSON.parse(text), text: async () => text };
}
async function fetch(url, init) {
  init = init || {};
  if ((init.method || "GET").toUpperCase() !== "POST") return __response(405, { error: { message: "Method Not Allowed: this endpoint needs method: \"POST\"", type: "invalid_request_error" } });
  let body;
  try { body = typeof init.body === "string" ? JSON.parse(init.body) : init.body; }
  catch { return __response(400, { error: { message: "Invalid JSON body: use JSON.stringify(...)", type: "invalid_request_error" } }); }
  const [status, payload] = MOCK.handle(String(url), init.headers, body);
  return __response(status, payload);
}
const process = { env: { DEEPSEEK_API_KEY: "sk-mock-0000" } };
const exports = {};
const module = { exports };
function require(name) {
  if (name === "zod") { if (!__Zod) throw new Error("zod 没有加载成功"); return __Zod; }
  throw new Error(`这里只能 import "zod"，不能 import "${name}"`);
}
