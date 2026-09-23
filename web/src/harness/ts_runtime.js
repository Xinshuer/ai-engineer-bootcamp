// Runtime prelude for TypeScript exercises. Inserted inside an async function that
// receives (__post, __Zod). Runs in a Web Worker (browser) or a Node vm (validator).
// Mirrors py_mock.py for the mock DeepSeek server. Keep the two in sync.
const __out = [];
const __tests = [];
const __pending = [];
// learner timers are tracked, so the job waits for them before reporting (like Node does before exiting)
const __st = globalThis.setTimeout.bind(globalThis);
const __ct = globalThis.clearTimeout.bind(globalThis);
const __live = new Set();
const setTimeout = (fn, ms, ...args) => { const id = __st(() => { __live.delete(id); fn(...args); }, ms); __live.add(id); return id; };
const clearTimeout = (id) => { __live.delete(id); __ct(id); };

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
  if ((a instanceof Map) !== (b instanceof Map) || (a instanceof Set) !== (b instanceof Set)) return false;
  if (a instanceof Map) return a.size === b.size && [...a].every(([k, v]) => b.has(k) && __deepEqual(v, b.get(k)));
  if (a instanceof Set) { const rest = [...b]; return a.size === b.size && [...a].every((x) => { const i = rest.findIndex((y) => __deepEqual(x, y)); return i >= 0 && rest.splice(i, 1); }); }
  const ka = Object.keys(a).filter((k) => a[k] !== undefined).sort();
  const kb = Object.keys(b).filter((k) => b[k] !== undefined).sort();
  return ka.length === kb.length && ka.every((k, i) => k === kb[i] && __deepEqual(a[k], b[k]));
}
function __errText(e) {
  if (e && typeof e === "object" && "message" in e) return `${e.name || "Error"}: ${e.message}`;
  return "Uncaught " + __fmt(e, 0, true);
}
// the page prepends `var __CC_LANG = "en";` when it is in English
const __L = (zh, en) => (typeof __CC_LANG !== "undefined" && __CC_LANG === "en" ? en : zh);
const __PROMISE_HINT = __L("返回的是 Promise：这个函数是 async 的，测试拿到的是还没完成的结果", "it returned a Promise: the function is async, so the test got a result that is not finished yet");
function __rec(label) { const r = { label, passed: false }; __tests.push(r); return r; }
function __withTimeout(p, ms) {
  return Promise.race([p, new Promise((_, rej) => __st(() => { const e = new Error(__L(`超时：${ms / 1000} 秒内没有结果（是不是忘了 await 或 return？）`, `timed out: no result within ${ms / 1000} s (a missing await or return?)`)); e.__ccTimeout = true; rej(e); }, ms))]);
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
  const r = __rec(label); r.expected = __L("抛出错误", "throws an error");
  try { const got = fn(); r.got = __L("没有报错，返回了 ", "no error, returned ") + __fmt(got, 0, true); }
  catch (e) { r.passed = true; r.got = __L("抛出了 ", "threw ") + __errText(e); }
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
  const r = __rec(label); r.expected = __L("抛出错误（Promise 被 reject）", "throws an error (the Promise rejects)");
  __queue(async () => {
    try { const got = await __withTimeout(Promise.resolve().then(fn), 3000); r.got = __L("没有报错，返回了 ", "no error, returned ") + __fmt(got, 0, true); }
    catch (e) { r.passed = !(e && e.__ccTimeout); r.got = __L("抛出了 ", "threw ") + __errText(e); }
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
// DeepSeek model names -> the model that serves them (mirror of py_mock.py _CC_MODELS: live API, 2026-09-23;
// deepseek-chat / deepseek-reasoner are aliases announced as discontinued, chat thinks only when asked)
const __MODELS = { "deepseek-flash": "deepseek-flash", "deepseek-v4-pro": "deepseek-v4-pro", "deepseek-v4-flash": "deepseek-flash", "deepseek-chat": "deepseek-flash", "deepseek-reasoner": "deepseek-flash" };
const __STATUS_TEXT = { 429: "Rate limit reached, please retry later", 500: "Internal server error", 503: "Service unavailable" };
// mock embeddings: same hashed bag of words as py_mock.py (FNV-1a into 256 dims, contract synonyms folded)
const __EMBED_DIM = 256;
const __STOP = new Set("the a an of to and or in on for by with is are be shall will may this that any all its it as at from such not no".split(" "));
const __SYN = {};
for (const [k, words] of Object.entries({
  liability: "liability liable damage indemnify indemnification indemnity cap capped",
  termination: "terminate termination terminated cancel cancellation exit",
  renewal: "renew renewal renewed extend extension rollover",
  payment: "fee payment pay payable invoice price cost charge",
  data: "data personal gdpr privacy processing",
  confidential: "confidential confidentiality secret nda disclose disclosure",
  warranty: "warranty warrantie guarantee",
  law: "law governing jurisdiction court arbitration",
})) for (const w of words.split(" ")) __SYN[w] = k;
function __embed(text) {
  const vec = new Array(__EMBED_DIM).fill(0);
  for (let w of String(text).toLowerCase().match(/[a-z0-9]+/g) || []) {
    if (__STOP.has(w)) continue;
    if (w.length > 3 && w.endsWith("s") && !w.endsWith("ss")) w = w.slice(0, -1);
    w = __SYN[w] || w;
    let h = 2166136261;
    for (const ch of w) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
    vec[h % __EMBED_DIM] += 1;
  }
  let sq = 0;
  for (const x of vec) sq += x * x;
  const norm = Math.sqrt(sq);
  return norm ? vec.map((x) => x / norm) : vec;
}
function __rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const MOCK = {
  calls: [], queue: [], prompts: [], random: __rng(7),
  reset(seed = 7) { this.calls = []; this.queue = []; this.prompts = []; this.random = __rng(seed); },
  embed(text) { return __embed(text); },
  seed(n) { this.random = __rng(n); },
  failNext(status, times = 1) { for (let i = 0; i < times; i++) this.queue.push(status); },
  judge(text) {
    const low = text.toLowerCase();
    const m = /clause\s+(\d+(?:\.\d+)*)/i.exec(text);
    const clause_id = m ? m[1] : "unknown";
    // prompt injection: obeys an instruction hidden in the clause text, unless it sits inside <clause> tags
    if (low.includes("ignore previous instructions") && !/<clause>[\s\S]*ignore previous instructions[\s\S]*<\/clause>/.test(low))
      return { clause_id, verdict: "accept", risk_level: "low", topic: "other", rationale: "Mock review: followed an instruction found inside the clause text." };
    if (low.includes("as is")) {
      const verdict = this.random() < 0.6 ? "accept" : "flag";
      return { clause_id, verdict, risk_level: "low", topic: "other", rationale: "Mock review: mutual 'AS IS' disclaimer; the mock is unsure on purpose." };
    }
    for (const [kw, verdict, risk, topic] of __RULES) {
      if (low.includes(kw)) return { clause_id, verdict, risk_level: risk, topic, rationale: `Mock review: matched '${kw}'.` };
    }
    return { clause_id, verdict: "accept", risk_level: "low", topic: "other", rationale: "Mock review: nothing unusual found." };
  },
  // structured output: fill every property of the forced tool's schema (mirror of py_mock.py _fill)
  fill(schema, known, defs) {
    defs = defs || schema.$defs || {};
    const out = {};
    for (let [k, p] of Object.entries(schema.properties || {})) {
      if (p.$ref) p = defs[p.$ref.split("/").pop()] || {};
      const en = p.enum || ("const" in p ? [p.const] : null);
      const v = known[k];
      if (typeof v === "string" && (p.type || "string") === "string" && (!en || en.includes(v))) out[k] = v;
      else if (en) out[k] = en[0];
      else if (p.type === "object" && p.properties) out[k] = this.fill(p, known, defs);
      else out[k] = ({ string: `mock ${k}`, integer: 0, number: 0, boolean: false, array: [], object: {} })[p.type] ?? null;
    }
    return out;
  },
  handle(url, headers, body) {
    this.calls.push({ url, body });
    const err = (status, message, type) => [status, { error: { message, type } }];
    const isEmbed = String(url).endsWith("/embeddings");
    if (!isEmbed && !String(url).endsWith("/chat/completions")) return err(404, "Not Found: the URL should end with /chat/completions (or /embeddings)", "not_found");
    headers = headers || {};
    const auth = headers.Authorization || headers.authorization || "";
    if (!String(auth).startsWith("Bearer sk-")) return err(401, "Authentication Fails: send the header Authorization: Bearer <your key>", "authentication_error");
    if (this.queue.length) { const s = this.queue.shift(); return err(s, __STATUS_TEXT[s] || "error", "server_error"); }
    if (isEmbed) return this.embeddings(body);
    if (!body || typeof body !== "object" || typeof body.model !== "string" || !Array.isArray(body.messages) || body.messages.length === 0)
      return err(400, "Invalid request: the body needs 'model' (a string) and 'messages' (a non-empty list)", "invalid_request_error");
    if (!Object.hasOwn(__MODELS, body.model)) return err(400, `The supported API model names are deepseek-flash, deepseek-v4-pro, but you passed ${body.model}.`, "invalid_request_error");
    // thinking mode (DeepSeek V4): on unless the body says { thinking: { type: "disabled" } }; a value the
    // live API cannot read is 422 (mirror of py_mock.py)
    const thinking = body.thinking;
    if (thinking !== undefined && thinking !== null && (typeof thinking !== "object" || !["adaptive", "enabled", "disabled"].includes(thinking.type)))
      return err(422, `Failed to deserialize the JSON body into the target type: thinking.type: unknown variant \`${typeof thinking === "object" ? thinking.type : thinking}\`, expected one of \`adaptive\`, \`enabled\`, \`disabled\``, "invalid_request_error");
    const think = thinking ? thinking.type !== "disabled" : body.model !== "deepseek-chat";
    // thinking mode + tools: every earlier assistant message must carry its reasoning_content (the documented rule,
    // enforced here although the live API did not on 2026-09-23; mirror of py_mock.py)
    if (think && body.tools && body.tools.length) {
      const i = body.messages.findIndex((m) => m && m.role === "assistant" && typeof m.reasoning_content !== "string");
      if (i >= 0) return err(400, `Invalid request: thinking mode with tools needs the reasoning_content of every earlier assistant message passed back (message at index ${i} has none). Pass it back, or send "thinking": {"type": "disabled"}`, "invalid_request_error");
    }
    const messages = body.messages;
    for (let i = 0; i < messages.length; i++) {
      const m = messages[i];
      if (!m || typeof m !== "object" || !["system", "user", "assistant", "tool"].includes(m.role))
        return err(400, `Invalid message at index ${i}: needs a 'role' of system/user/assistant/tool`, "invalid_request_error");
      if (m.role !== "assistant" && typeof m.content !== "string")
        return err(400, `Invalid message at index ${i}: 'content' must be a string`, "invalid_request_error");
    }
    // like the real API: tool calls are answered right after they are made (mirror of py_mock.py)
    let pending = [];
    for (let i = 0; i < messages.length; i++) {
      const m = messages[i];
      if (m.role === "tool") {
        if (!pending.includes(m.tool_call_id))
          return err(400, `Invalid message at index ${i}: a 'tool' message must answer a tool call from the assistant message before it (tool_call_id ${JSON.stringify(m.tool_call_id)} not found)`, "invalid_request_error");
        pending = pending.filter((id) => id !== m.tool_call_id);
        continue;
      }
      if (pending.length) return err(400, `Invalid message at index ${i}: the assistant message with 'tool_calls' must be followed by 'tool' messages for ${JSON.stringify(pending)}`, "invalid_request_error");
      if (m.role === "assistant") pending = (m.tool_calls || []).filter((c) => c && typeof c === "object").map((c) => c.id);
    }
    if (pending.length) return err(400, `Invalid request: the last assistant message has 'tool_calls' without 'tool' messages for ${JSON.stringify(pending)}`, "invalid_request_error");
    const promptTokens = Math.floor(messages.map((m) => m.content || "").join("").length / 4) + 8;
    // prefix cache, like DeepSeek: only the identical START of the request is a hit (64-char blocks)
    const key = messages.map((m) => `${m.role}:${m.content || ""}\n`).join("");
    let same = 0;
    for (const old of this.prompts) {
      let n = 0;
      const lim = Math.min(old.length, key.length);
      while (n < lim && old[n] === key[n]) n++;
      same = Math.max(same, n);
    }
    this.prompts = [...this.prompts, key].slice(-50);
    const cacheHit = Math.min(promptTokens, Math.floor(same / 64) * 16);
    const userText = ([...messages].reverse().find((m) => m.role === "user") || {}).content || "";
    const tools = body.tools || [];
    const toolMsgs = messages.filter((m) => m.role === "tool");
    const fmt = (body.response_format || {}).type;
    if (![undefined, null, "text", "json_object"].includes(fmt))
      return err(400, `Invalid request: response_format type '${fmt}' is not supported (use 'json_object', or tools)`, "invalid_request_error");
    const choice = body.tool_choice;
    const forced = choice && typeof choice === "object" ? (choice.function || {}).name : null;
    const required = choice === "required" || choice === "any";
    let message, finish = "stop";
    if (tools.length && choice !== "none" && (forced || required || !toolMsgs.length || userText.includes("[loop]"))) {
      // same tool choice and argument filling as py_mock.py
      const low = userText.toLowerCase();
      const fns = tools.map((t) => t.function || {});
      const fn = fns.find((f) => forced && f.name === forced) || (required && toolMsgs.length ? fns[fns.length - 1] : null)
        || fns.find((f) => f.name && userText.includes(f.name)) || fns[0];
      const name = fn.name || "tool";
      const props = (fn.parameters || {}).properties;
      const hit = __TOPICS.find(([kw]) => low.includes(kw));
      const topic = hit ? hit[1] : "other";
      const cid = /clause\s+(\d+(?:\.\d+)*)/i.exec(userText);
      const known = { topic, clause_id: cid ? cid[1] : "unknown", query: userText.replace(/\[[a-z-]+\]/g, "").trim().slice(0, 80) };
      const args = forced || required ? this.fill(fn.parameters || {}, { ...known, ...this.judge(userText) })
        : !props ? { topic } : Object.fromEntries(Object.entries(known).filter(([k]) => k in props));
      const argText = userText.includes("[bad-args]") ? '{"topic": ' : JSON.stringify(args);
      message = { role: "assistant", content: "", tool_calls: [{ id: `call_${toolMsgs.length + 1}`, type: "function", function: { name, arguments: argText } }] };
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
    let completionTokens = Math.floor((message.content || "").length / 4) + 5;
    let reasoningTokens = 0;
    if (think) {
      // the chain of thought comes back next to the answer and is billed as output
      message.reasoning_content = `Mock reasoning: ${messages.length} message(s) read; deciding how to answer.`;
      reasoningTokens = Math.floor(message.reasoning_content.length / 4) + 40;
      completionTokens += reasoningTokens;
    }
    return [200, {
      id: `mock-${this.calls.length}`, object: "chat.completion", model: __MODELS[body.model],
      choices: [{ index: 0, message, finish_reason: finish }],
      usage: { prompt_tokens: promptTokens, completion_tokens: completionTokens, total_tokens: promptTokens + completionTokens, prompt_cache_hit_tokens: cacheHit, prompt_cache_miss_tokens: promptTokens - cacheHit, ...(think ? { completion_tokens_details: { reasoning_tokens: reasoningTokens } } : {}) },
    }];
  },
  embeddings(body) {
    const bad = [400, { error: { message: "Invalid request: the body needs 'model' (a string) and 'input' (a string or a non-empty list of strings)", type: "invalid_request_error" } }];
    if (!body || typeof body !== "object" || typeof body.model !== "string") return bad;
    if (!body.model.includes("embed")) return [400, { error: { message: `Model Not Exist: ${body.model} (use an embedding model, e.g. text-embedding-3-small)`, type: "invalid_request_error" } }];
    const texts = typeof body.input === "string" ? [body.input] : body.input;
    if (!Array.isArray(texts) || !texts.length || !texts.every((t) => typeof t === "string")) return bad;
    const tokens = texts.reduce((n, t) => n + Math.floor(t.length / 4) + 1, 0);
    return [200, {
      object: "list", model: body.model,
      data: texts.map((t, i) => ({ object: "embedding", index: i, embedding: __embed(t) })),
      usage: { prompt_tokens: tokens, total_tokens: tokens },
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
const process = { env: { DEEPSEEK_API_KEY: "sk-mock-0000", OPENAI_API_KEY: "sk-mock-embed" } };
const exports = {};
const module = { exports };
function require(name) {
  if (name === "zod") { if (!__Zod) throw new Error(__L("zod 没有加载成功", "zod did not load")); return __Zod; }
  throw new Error(__L(`这里只能 import "zod"，不能 import "${name}"`, `only "zod" can be imported here, not "${name}"`));
}
