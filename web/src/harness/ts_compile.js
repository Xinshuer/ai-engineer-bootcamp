// Shared by the page and the Node validator: type-check + transpile a TS exercise,
// and wrap the result into a self-contained job script.
// Defines globalThis.CCTS = { compile, buildJob }.
(function (root) {
  const SEP = "\n// ---- tests ----\n";
  const ROOTS = ["env.d.ts", "zod.d.ts", "main.ts"];
  const cache = new Map(); // file name -> SourceFile (libs are parsed once)

  function compile(ts, libs, userCode, testCode) {
    const full = userCode + SEP + (testCode || "");
    const userLines = userCode.split("\n").length;
    const options = {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      lib: ["lib.es2022.d.ts"],
      types: [],
      strict: true,
      noEmit: true,
      skipLibCheck: true,
      esModuleInterop: true,
      noFallthroughCasesInSwitch: true,
    };
    const norm = (n) => n.replace(/^[\\/]+/, "");
    const read = (name) => (name === "main.ts" ? full : libs[name]);
    const host = {
      getSourceFile(name, languageVersion) {
        const n = norm(name);
        const text = read(n);
        if (text === undefined) return undefined;
        if (n !== "main.ts") {
          if (!cache.has(n)) cache.set(n, ts.createSourceFile(n, text, languageVersion, true));
          return cache.get(n);
        }
        return ts.createSourceFile(n, text, languageVersion, true);
      },
      getDefaultLibFileName: () => "lib.es2022.d.ts",
      getDefaultLibLocation: () => "",
      writeFile: () => {},
      getCurrentDirectory: () => "",
      getDirectories: () => [],
      fileExists: (name) => read(norm(name)) !== undefined,
      readFile: (name) => read(norm(name)),
      getCanonicalFileName: (n) => n,
      useCaseSensitiveFileNames: () => true,
      getNewLine: () => "\n",
      directoryExists: () => true,
    };
    const program = ts.createProgram(ROOTS, options, host);
    const diagnostics = ts.getPreEmitDiagnostics(program)
      .filter((d) => d.file && norm(d.file.fileName) === "main.ts")
      .map((d) => {
        const pos = d.file.getLineAndCharacterOfPosition(d.start || 0);
        const line = pos.line + 1;
        return {
          line: line <= userLines ? line : line - userLines - 1,
          col: pos.character + 1,
          inTests: line > userLines,
          code: d.code,
          message: ts.flattenDiagnosticMessageText(d.messageText, "\n"),
        };
      });
    const js = ts.transpileModule(full, {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
    }).outputText;
    return { diagnostics, js };
  }

  // A self-contained script: runtime prelude + transpiled code. It reports through
  // postMessage (worker) or a __POST function supplied by the validator.
  function buildJob(runtimeSource, js) {
    return [
      "(async function (__post, __Zod) {",
      runtimeSource,
      "let __error = null;",
      "try {",
      js,
      "} catch (__e) { __error = __errText(__e); }",
      "try { await Promise.all(__pending); } catch (__e) {}",
      "await new Promise((r) => setTimeout(r, 0));",
      "__post({ stdout: __out.join('\\n'), error: __error, tests: __tests });",
      "})(typeof __POST === 'function' ? __POST : (m) => postMessage(m), typeof Zod !== 'undefined' ? Zod : null);",
    ].join("\n");
  }

  root.CCTS = { compile, buildJob, SEP };
})(typeof globalThis !== "undefined" ? globalThis : self);
