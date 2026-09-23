// Download the Python wheels the site ships (vendor/ is not in git):
//   vendor/      Pydantic, loaded when an exercise uses it
//   vendor/lc/   LangChain / LangGraph and everything they import, loaded for the LangChain week
// Pyodide builds come from the Pyodide CDN (same version as node_modules/pyodide), pure-Python
// wheels from PyPI. Versions are pinned; change them here and rerun `node fetch-vendor.mjs`.
import fs from "node:fs";
import path from "node:path";

const ROOT = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const P = (...p) => path.join(decodeURIComponent(ROOT), ...p);
const PYODIDE = JSON.parse(fs.readFileSync(P("node_modules", "pyodide", "package.json"), "utf8")).version;
const LOCK = JSON.parse(fs.readFileSync(P("node_modules", "pyodide", "pyodide-lock.json"), "utf8"));
const CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE}/full/`;

const SETS = {
  vendor: { pyodide: ["pydantic", "pydantic-core", "typing-extensions", "annotated-types", "typing-inspection"], pypi: {} },
  "vendor/lc": {
    pyodide: ["xxhash", "msgpack", "orjson", "zstandard", "pyyaml", "requests", "httpx", "httpcore", "h11", "anyio",
      "sniffio", "idna", "certifi", "jsonpatch", "jsonpointer", "packaging", "charset-normalizer", "urllib3", "jiter",
      "tiktoken", "regex", "distro", "tqdm", "numpy"],
    pypi: {
      "langchain-core": "1.6.4", langchain: "1.4.2", "langchain-openai": "1.6.4", "langchain-deepseek": "1.1.1",
      "langchain-text-splitters": "1.1.2", "langchain-protocol": "0.0.19", langgraph: "1.2.12",
      "langgraph-checkpoint": "4.2.0", "langgraph-prebuilt": "1.1.0", "langgraph-sdk": "0.4.5",
      "langgraph-checkpoint-sqlite": "3.1.1", aiosqlite: "0.22.1",
      // langsmith >= 0.11 and openai >= 3 need httpx2, which Pyodide does not have
      langsmith: "0.10.18", openai: "2.54.0", tenacity: "9.1.4", "requests-toolbelt": "1.0.0", websockets: "17.1",
    },
    // tiktoken's encoding file, pre-placed in its cache so OpenAIEmbeddings works offline
    files: { "cl100k_base.tiktoken": "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken" },
  },
};

async function get(url, dest) {
  if (fs.existsSync(dest)) return;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  fs.writeFileSync(dest, Buffer.from(await res.arrayBuffer()));
  console.log("  " + path.basename(dest));
}

for (const [dir, set] of Object.entries(SETS)) {
  fs.mkdirSync(P(dir), { recursive: true });
  console.log(dir + "/");
  for (const name of set.pyodide) {
    const pkg = LOCK.packages[name];
    if (!pkg) throw new Error(`${name} is not in pyodide-lock.json`);
    await get(CDN + pkg.file_name, P(dir, pkg.file_name));
  }
  for (const [name, version] of Object.entries(set.pypi)) {
    const meta = await (await fetch(`https://pypi.org/pypi/${name}/${version}/json`)).json();
    const whl = meta.urls.find((u) => u.packagetype === "bdist_wheel" && /-none-any\.whl$/.test(u.filename));
    if (!whl) throw new Error(`${name} ${version}: no pure-Python wheel on PyPI`);
    await get(whl.url, P(dir, whl.filename));
  }
  for (const [file, url] of Object.entries(set.files || {})) await get(url, P(dir, file));
}
