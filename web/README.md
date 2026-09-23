# 编程营网站的源码

交互式练习网站：三周（21 天）自动判题的 Python / TypeScript 练习 + 知识卡片。

```
content/day1.txt … day21.txt   题库（纯文本格式，见任意一个文件）
src/index.html                 页面
src/harness/                   判题器：py_runner.py、py_mock.py（模拟 DeepSeek + embeddings）、
                               py_discover.py（「写测试」题的测试发现）、
                               ts_runtime.js、ts_compile.js、ts_env.d.ts、zod_shim.d.ts
build.mjs                      解析题库 → 在真实运行时里逐题验证 → 生成 dist/
```

构建：

```bash
cd learn/web
npm install
# vendor/ 放 Pydantic 的 Pyodide wheel（pyodide 314.0.7 对应版本，从 cdn.jsdelivr.net/pyodide 下载）
node build.mjs                 # 全部验证，并生成 dist/
node build.mjs --day 3         # 只验证第 3 天，不写 dist/（可以同时跑好几个）
node build.mjs --day 8,9 --show  # 验证第 8、9 天，并打印每张卡片和每道预测题的输出
```

验证规则：每道题的参考答案必须通过测试、起始代码必须不通过、预测题的标准输出由程序运行得出（TypeScript 的还要和真实 Node 的输出一致）。「写测试」题（`type: testwrite`）：参考测试必须在正确实现上全部通过、并抓住每一个坏版本（`--- mutants` 里用 `===== 线索` 分隔）；起始测试不能已经抓住全部坏版本。

加题：照着 `content/` 里的格式写一个 `@@ item` 块，跑 `node build.mjs --day N`，全绿后再跑一次不带参数的完整构建（预测题的答案只在验证时计算），再发布。

学习进度存在页面的数据库里：`progress/<用户>` 是每道题的状态和汇总，`progress/<用户>/drafts/d<N>` 是第 N 天的代码草稿。
