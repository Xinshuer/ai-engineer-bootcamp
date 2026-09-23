# 七日营网站的源码

交互式练习网站：7 天、145 道自动判题的 Python / TypeScript 练习 + 48 张知识卡片。

```
content/day1.txt … day7.txt   题库（纯文本格式，见任意一个文件）
src/index.html                 页面
src/harness/                   判题器：py_runner.py、py_mock.py（模拟 DeepSeek）、
                               ts_runtime.js、ts_compile.js、ts_env.d.ts、zod_shim.d.ts
build.mjs                      解析题库 → 在真实运行时里逐题验证 → 生成 dist/
```

构建：

```bash
cd learn/web
npm install
# vendor/ 放 Pydantic 的 Pyodide wheel（pyodide 314.0.7 对应版本，从 cdn.jsdelivr.net/pyodide 下载）
node build.mjs            # 全部验证
node build.mjs --day 3    # 只验证第 3 天（预测题的答案只在验证时计算，发布前要跑全量）
```

验证规则：每道题的参考答案必须通过测试、起始代码必须不通过、预测题的标准输出由程序运行得出（TypeScript 的还要和真实 Node 的输出一致）。

加题：照着 `content/` 里的格式写一个 `@@ item` 块，跑 `node build.mjs --day N`，全绿再发布。
