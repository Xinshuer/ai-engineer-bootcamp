# AI Engineer Bootcamp

**English** · [中文](#中文)

A 35-day practice course that teaches Python, TypeScript, SQL, cloud basics and LangChain / LangGraph through one real project: [Clause Check](https://github.com/Xinshuer/Contract-Clause-Reviewer), a contract-clause reviewer built on an LLM. Every exercise is a small piece of that project. The site comes in English and Chinese: switch at the top right.

| Folder | What it is |
|---|---|
| [`web/`](web/) | The practice site: 753 auto-graded exercises and knowledge cards, all running in the browser (Python via Pyodide, the TypeScript compiler, SQLite, and simulated DeepSeek, AWS and GCP services). Each exercise has a background note, links to the cards it uses, and the checks the grader runs. The build validates every exercise: reference solutions must pass, starter code must fail. See [web/README.md](web/README.md). |
| [`lessons/`](lessons/) | Eight short hands-on lessons on debugging and checking an LLM app, run against the Clause Check project. |

## Build and run the site

```bash
cd web
npm install
node fetch-vendor.mjs   # downloads the pinned Python wheels (Pydantic, LangChain, LangGraph, ...) into vendor/
node build.mjs          # validates every exercise, then writes dist/
node serve.mjs          # http://localhost:8000
```

Week 5 runs the real LangChain and LangGraph libraries in the browser. Exercises never call a paid API: the model, the cloud SDKs and the database are simulated. Optional "local" tasks run on your own machine, some of them against the real DeepSeek API with your own key in the Clause Check project's `.env`.

---

<a id="中文"></a>

# AI 工程师训练营

[English](#ai-engineer-bootcamp) · **中文**

35 天的练习课：通过一个真实项目 [Clause Check](https://github.com/Xinshuer/Contract-Clause-Reviewer)（用大模型逐条审查合同条款的程序）学 Python、TypeScript、SQL、云服务基础和 LangChain / LangGraph。每道练习题都是这个项目里的一小块。网站有中文和英文两个版本，页面右上角切换。

| 文件夹 | 内容 |
|---|---|
| [`web/`](web/) | 练习网站：753 道自动判题的练习和知识卡片，全部在浏览器里运行（Pyodide 跑 Python、TypeScript 编译器、SQLite，以及模拟的 DeepSeek、AWS、GCP 服务）。每道题都有「背景」、要用到的知识卡片，以及判题会检查什么。构建时逐题验证：参考答案必须通过，起始代码必须不通过。详见 [web/README.md](web/README.md)。 |
| [`lessons/`](lessons/) | 八节动手小课：怎么排错、怎么检查一个大模型应用，都在 Clause Check 项目上做。 |

## 构建和运行

```bash
cd web
npm install
node fetch-vendor.mjs   # 下载固定版本的 Python 包（Pydantic、LangChain、LangGraph 等）到 vendor/
node build.mjs          # 逐题验证，然后生成 dist/
node serve.mjs          # 打开 http://localhost:8000
```

第 5 周在浏览器里运行真正的 LangChain 和 LangGraph。练习题不会调用任何付费接口：模型、云 SDK 和数据库都是模拟的。可选的「本机任务」在你自己的电脑上做，其中一些会用你放在 Clause Check 项目 `.env` 里的密钥调用真的 DeepSeek。
