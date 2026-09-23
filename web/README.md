# The practice site

**English** · [中文](#中文)

An interactive practice site: five weeks (35 days) of auto-graded Python / TypeScript / SQL exercises plus knowledge cards. Week 5 runs the real LangChain and LangGraph. The course exists in Chinese and English; switch at the top right of the page (the choice is kept in the browser; `?lang=en` works too).

```
content/day1.txt … day35.txt      the Chinese course (a plain-text format: see any file)
content/en/day1.txt … day35.txt   the English course: same format, same ids and order, only the words differ (checked item by item at build time)
content/data/clausecheck.sql      sample data for the SQL / BigQuery / database exercises (customers, contracts, reviews, evals, tool calls)
src/index.html                    the page
src/harness/                      the graders:
  py_runner.py                    runs Python exercises (tests, errors, output)
  py_mock.py                      a mock DeepSeek API (as the live API answered on 2026-09-23: deepseek-flash / deepseek-v4-pro, old names as aliases, thinking mode) + OpenAI-style embeddings
  py_discover.py                  test discovery for "write tests" exercises
  py_sql.py                       SQL exercises: run on SQLite and compared with the reference query; a simulation of BigQuery's syntax
  py_cloud.py                     simulated boto3 (S3, SQS, Secrets Manager, Bedrock) and google-cloud (Storage, BigQuery, Secret Manager, Pub/Sub, google-genai)
  py_langchain.py                 week 5: runs the real LangChain / LangGraph in the browser (two native packages replaced, no threads, network routed to the mock server)
  ts_runtime.js, ts_compile.js, ts_env.d.ts, zod_shim.d.ts   TypeScript exercises
build.mjs                         parses the course → validates every exercise in the real runtimes → writes dist/
fetch-vendor.mjs                  downloads the Python packages the page ships (vendor/ is not in git)
serve.mjs                         previews dist/ locally: node serve.mjs, then open http://localhost:8000
```

Build:

```bash
cd web
npm install
node fetch-vendor.mjs            # downloads Pydantic, LangChain/LangGraph and more into vendor/ (pinned in the script)
node build.mjs                   # validates everything and writes dist/ (course.js, and course-en.js once every English day is valid)
node build.mjs --day 3           # validates day 3 only, writes nothing (several can run at once)
node build.mjs --day 8,9 --show  # validates days 8 and 9 and prints card outputs, predict answers and SQL result tables
node build.mjs --lang en --day 3 # validates the English day 3 only (and checks it against the Chinese item by item)
node build.mjs --preview-en      # writes course-en.js even while the translation is unfinished (missing days in Chinese)
```

Validation rules: every reference solution must pass, every starter must fail, and predict-the-output answers are computed by running the code (TypeScript output must also match real Node; Python output must be the same over two runs).

- "Write tests" exercises (`type: testwrite`): the reference tests must pass on the correct implementation and catch every broken version (`--- mutants`, separated by `===== clue`); the starter tests must not already catch them all.
- SQL exercises (`type: sql`, `lang: sql`, `dataset: clausecheck`): the learner's query and `--- solution` run on the same data; columns (count, order, aliases) and rows must match; with `ordered: yes` the order must match too; `check:` compares a table after INSERT / UPDATE exercises; `bq: yes` accepts BigQuery syntax (dataset-qualified table names, `/` as decimal division, SAFE_DIVIDE, COUNTIF, DATE_TRUNC(x, MONTH) and more; see the list at the top of py_sql.py). The correct order of a SQL ordering exercise is run as well.
- Python exercises with `dataset: clausecheck` get `fresh_db()` (a sqlite3 connection with the sample data); `cloud: yes` installs the simulated cloud SDKs and a `CLOUD` object for tests. The simulated SDKs were checked against the official docs and SDK sources: keyword-only arguments, parameter names and types validated, credentials checked on first call, boto3 retrying throttling errors itself, BigQuery query errors raised from `job.result()`, and so on; anything not implemented raises NotImplementedError.
- LangChain exercises (`langchain: yes`, also allowed on `@@ day`): the real langchain / langchain-core / langgraph / langchain-openai / langchain-deepseek run (versions in fetch-vendor.mjs); only the network is fake: model calls go to the mock server in py_mock.py (`MOCK.calls` shows what LangChain actually sent). The first LangChain exercise downloads about 11 MB and takes a few seconds to import, not counted in the 10-second run limit. The build rejects code that breaks on a normal computer (`SqliteSaver(sqlite3.connect(...))` without `check_same_thread=False`, asyncio). Files exported with "Copy as local file" run the same way on your computer once the packages are installed (the network again goes to the mock server).

Every exercise has a `--- context` (before `--- prompt`, shown as "Background": where this piece sits in Clause Check or the day's scenario, what the real input is, what the result is for; a few sentences, never the answer; at most 240 characters in Chinese and 520 in English) and `cards: Title 1; Title 2` (the knowledge cards it uses: the day's own card titles, or `dN:Title` for another day; the build checks they exist). Before the first run the page lists "What the grader checks": the name of every `expect`, plus "call → result" for tests that call the learner's function directly. A named card (`@@ concept intro`) gets the id `d<day>-intro` and does not shift the numbering of the others.

Adding an exercise: write an `@@ item` block in the format of `content/`, and the English version at the same place in the same day under `content/en/`; run `node build.mjs --day N` and `node build.mjs --lang en --day N`; when both are green run the full build once (predict answers are only computed while validating), then publish.

Progress is kept in the browser (localStorage, written as soon as the tab is hidden or closed) and in the page's database: `progress/<user>` holds each exercise's status and a summary, `progress/<user>/drafts/d<N>` holds day N's code drafts.

---

<a id="中文"></a>

# 编程营网站的源码

[English](#the-practice-site) · **中文**

交互式练习网站：五周（35 天）自动判题的 Python / TypeScript / SQL 练习 + 知识卡片。第 5 周用的是真正的 LangChain 和 LangGraph。中文和英文两套内容，页面右上角切换（选择记在浏览器里，也可以用 `?lang=en`）。

```
content/day1.txt … day35.txt   题库（纯文本格式，见任意一个文件）
content/en/day1.txt … day35.txt   英文题库：同样的格式、同样的题号和顺序，只有文字不同（构建时逐题核对）
content/data/clausecheck.sql   SQL / BigQuery / 数据库题用的样例数据（客户、合同、审查结果、评测、工具调用）
src/index.html                 页面
src/harness/                   判题器：
  py_runner.py                 运行 Python 题（测试、报错、输出）
  py_mock.py                   模拟 DeepSeek 接口（按 2026-09-23 实测：deepseek-flash / deepseek-v4-pro，旧名字当别名，思考模式）+ OpenAI 格式的 embeddings
  py_discover.py               「写测试」题的测试发现
  py_sql.py                    SQL 题：在 SQLite 上运行、和参考答案比结果；BigQuery 写法的模拟
  py_cloud.py                  模拟的 boto3（S3、SQS、Secrets Manager、Bedrock）和 google-cloud
                               （Storage、BigQuery、Secret Manager、Pub/Sub、google-genai）
  py_langchain.py              第 5 周：让真正的 LangChain / LangGraph 在浏览器里跑（补两个原生包、没有线程、网络接到模拟服务器）
  ts_runtime.js、ts_compile.js、ts_env.d.ts、zod_shim.d.ts   TypeScript 题
build.mjs                      解析题库 → 在真实运行时里逐题验证 → 生成 dist/
fetch-vendor.mjs               下载页面要带的 Python 包（vendor/ 不进 git）
serve.mjs                      本地预览 dist/：node serve.mjs，打开 http://localhost:8000
```

构建：

```bash
cd web
npm install
node fetch-vendor.mjs            # 下载 Pydantic、LangChain/LangGraph 等 wheel 到 vendor/（版本写在脚本里）
node build.mjs                   # 全部验证，并生成 dist/
node build.mjs --day 3           # 只验证第 3 天，不写 dist/（可以同时跑好几个）
node build.mjs --day 8,9 --show  # 验证第 8、9 天，并打印卡片输出、预测题答案和 SQL 结果表
node build.mjs --lang en --day 3 # 只验证英文的第 3 天（也会和中文逐题核对结构）
node build.mjs --preview-en      # 英文还没译完时也生成 course-en.js，缺的天先用中文顶上
```

验证规则：每道题的参考答案必须通过、起始代码必须不通过、预测题的标准输出由程序运行得出（TypeScript 的还要和真实 Node 的输出一致，Python 的要连跑两次结果相同）。

- 「写测试」题（`type: testwrite`）：参考测试必须在正确实现上全部通过、并抓住每一个坏版本（`--- mutants` 里用 `===== 线索` 分隔）；起始测试不能已经抓住全部坏版本。
- SQL 题（`type: sql`，`lang: sql`，`dataset: clausecheck`）：学习者的查询和 `--- solution` 在同一份数据上运行，列（个数、顺序、别名）和行都要一致；`ordered: yes` 时顺序也要一致；`check:` 用于 INSERT / UPDATE 这类题，比较执行后的表；`bq: yes` 接受 BigQuery 写法（表名必须带数据集、`/` 是小数除法、SAFE_DIVIDE、COUNTIF、DATE_TRUNC(x, MONTH) 等，见 py_sql.py 开头的清单）。SQL 排序题的正确顺序也会跑一遍。
- Python 题加 `dataset: clausecheck` 会提供 `fresh_db()`（一个装好样例数据的 sqlite3 连接）；加 `cloud: yes` 会装上模拟的云 SDK 和给测试用的 `CLOUD` 对象。模拟 SDK 按官方文档和 SDK 源码核对过：只接受关键字参数、校验参数名和类型、首次调用时才检查凭证、boto3 自己会重试限流错误、BigQuery 的查询错误从 `job.result()` 抛出等；没实现的部分会抛 NotImplementedError。
- LangChain 题（`langchain: yes`，可以写在 `@@ day` 上）：跑的是真正的 langchain / langchain-core / langgraph / langchain-openai / langchain-deepseek（版本见 fetch-vendor.mjs），只有网络是假的：模型调用都进 py_mock.py 的模拟服务器（`MOCK.calls` 能看到 LangChain 实际发出的请求）。页面第一次遇到 LangChain 题时下载约 11 MB 并导入几秒，不计入单次运行的 10 秒上限。构建会拒绝在普通电脑上会出问题的写法（`SqliteSaver(sqlite3.connect(...))` 没有 `check_same_thread=False`、asyncio）。「复制为本机文件」导出的文件在本机装好这些包后同样能跑（网络同样接到模拟服务器）。

每道题都要有 `--- context`（写在 `--- prompt` 前面，页面标成「背景」：这一块在 Clause Check 或当天场景里的位置、真实输入是什么、结果拿去做什么，几句话、不超过 240 字，不能透露答案）和 `cards: 标题1; 标题2`（用到的知识卡片，同一天写标题，别的天写 `dN:标题`，构建时检查标题存在）。页面还会在第一次运行前列出「判题会检查」：每条 `expect` 的名字，直接调用学习者函数的那几条再加上「调用 → 结果」。有名字的卡片（`@@ concept intro`）的 id 是 `d<天>-intro`，不影响其他卡片的编号。

加题：照着 `content/` 里的格式写一个 `@@ item` 块，在 `content/en/` 的同一天、同一位置写英文版，跑 `node build.mjs --day N` 和 `node build.mjs --lang en --day N`，全绿后再跑一次不带参数的完整构建（预测题的答案只在验证时计算），再发布。

学习进度存在浏览器本地（localStorage，切走或关闭标签页时立即写入）和页面的数据库里：`progress/<用户>` 是每道题的状态和汇总，`progress/<用户>/drafts/d<N>` 是第 N 天的代码草稿。
