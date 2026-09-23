// Serve dist/ locally: node serve.mjs [port]   then open http://localhost:8000
// dist/index.html is a page fragment (the form claude.ai artifacts use), so it is wrapped in a minimal
// document with a UTF-8 charset here. Without the claude.ai host, progress is kept in the browser only.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIST = path.join(path.dirname(fileURLToPath(import.meta.url)), "dist");
const PORT = Number(process.argv[2] || 8000);
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".json": "application/json", ".wasm": "application/wasm", ".txt": "text/plain; charset=utf-8" };
const HEAD = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>';

if (!fs.existsSync(path.join(DIST, "index.html"))) {
  console.error("dist/index.html not found: run node build.mjs first");
  process.exit(1);
}
http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split("?")[0]).replace(/^\/$/, "/index.html");
  const file = path.join(DIST, rel);
  if (!file.startsWith(DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end("not found"); }
  let body = fs.readFileSync(file);
  if (rel === "/index.html") body = Buffer.concat([Buffer.from(HEAD), body, Buffer.from("</body></html>")]);
  res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
  res.end(body);
}).listen(PORT, () => console.log(`http://localhost:${PORT}`));
