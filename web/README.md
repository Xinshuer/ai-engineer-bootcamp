# 编程营网站的源码

交互式练习网站：五周（35 天）自动判题的 Python / TypeScript / SQL 练习 + 知识卡片。第 5 周用的是真正的 LangChain 和 LangGraph。

```
content/day1.txt … day35.txt   题库（纯文本格式，见任意一个文件）
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
```

构建：

```bash
cd learn/web
npm install
node fetch-vendor.mjs            # 下载 Pydantic、LangChain/LangGraph 等 wheel 到 vendor/（版本写在脚本里）
node build.mjs                   # 全部验证，并生成 dist/
node build.mjs --day 3           # 只验证第 3 天，不写 dist/（可以同时跑好几个）
node build.mjs --day 8,9 --show  # 验证第 8、9 天，并打印卡片输出、预测题答案和 SQL 结果表
```

验证规则：每道题的参考答案必须通过、起始代码必须不通过、预测题的标准输出由程序运行得出（TypeScript 的还要和真实 Node 的输出一致，Python 的要连跑两次结果相同）。

- 「写测试」题（`type: testwrite`）：参考测试必须在正确实现上全部通过、并抓住每一个坏版本（`--- mutants` 里用 `===== 线索` 分隔）；起始测试不能已经抓住全部坏版本。
- SQL 题（`type: sql`，`lang: sql`，`dataset: clausecheck`）：学习者的查询和 `--- solution` 在同一份数据上运行，列（个数、顺序、别名）和行都要一致；`ordered: yes` 时顺序也要一致；`check:` 用于 INSERT / UPDATE 这类题，比较执行后的表；`bq: yes` 接受 BigQuery 写法（表名必须带数据集、`/` 是小数除法、SAFE_DIVIDE、COUNTIF、DATE_TRUNC(x, MONTH) 等，见 py_sql.py 开头的清单）。SQL 排序题的正确顺序也会跑一遍。
- Python 题加 `dataset: clausecheck` 会提供 `fresh_db()`（一个装好样例数据的 sqlite3 连接）；加 `cloud: yes` 会装上模拟的云 SDK 和给测试用的 `CLOUD` 对象。模拟 SDK 按官方文档和 SDK 源码核对过：只接受关键字参数、校验参数名和类型、首次调用时才检查凭证、boto3 自己会重试限流错误、BigQuery 的查询错误从 `job.result()` 抛出等；没实现的部分会抛 NotImplementedError。
- LangChain 题（`langchain: yes`，可以写在 `@@ day` 上）：跑的是真正的 langchain / langchain-core / langgraph / langchain-openai / langchain-deepseek（版本见 fetch-vendor.mjs），只有网络是假的：模型调用都进 py_mock.py 的模拟服务器（`MOCK.calls` 能看到 LangChain 实际发出的请求）。页面第一次遇到 LangChain 题时下载约 11 MB 并导入几秒，不计入单次运行的 10 秒上限。构建会拒绝在普通电脑上会出问题的写法（`SqliteSaver(sqlite3.connect(...))` 没有 `check_same_thread=False`、asyncio）。「复制为本机文件」导出的文件在本机装好这些包后同样能跑（网络同样接到模拟服务器）。

每道题都要有 `--- context`（写在 `--- prompt` 前面，页面标成「背景」：这一块在 Clause Check 或当天场景里的位置、真实输入是什么、结果拿去做什么，几句话、不超过 240 字，不能透露答案）和 `cards: 标题1; 标题2`（用到的知识卡片，同一天写标题，别的天写 `dN:标题`，构建时检查标题存在）。页面还会在第一次运行前列出「判题会检查」：每条 `expect` 的名字，直接调用学习者函数的那几条再加上「调用 → 结果」。有名字的卡片（`@@ concept intro`）的 id 是 `d<天>-intro`，不影响其他卡片的编号。

加题：照着 `content/` 里的格式写一个 `@@ item` 块，跑 `node build.mjs --day N`，全绿后再跑一次不带参数的完整构建（预测题的答案只在验证时计算），再发布。

学习进度存在浏览器本地（localStorage，切走或关闭标签页时立即写入）和页面的数据库里：`progress/<用户>` 是每道题的状态和汇总，`progress/<用户>/drafts/d<N>` 是第 N 天的代码草稿。
