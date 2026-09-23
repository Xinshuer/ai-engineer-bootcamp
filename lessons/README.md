# 上手课：用 Clause Check 学会排错和检查

给第一次做 LLM 应用的人。每课只讲一件事，一条命令能跑完，10–20 分钟一课。
先在 `mock` 模式（不调模型、免费、秒出）找感觉，标了 🔑 的课再用 DeepSeek。

课文里的命令都在 Clause Check 项目文件夹里运行（项目：<https://github.com/Xinshuer/Contract-Clause-Reviewer>）。几个小脚本放在这个 repo 的 `lessons/` 里，运行时写它的完整路径，例如 `python "G:\Clause Check 编程营\lessons\inspect_report.py" data/map.report.json`。

```bash
cd "G:\Contract Clause Reviewer"
cp .env.example .env         # 填 DEEPSEEK_API_KEY=sk-...
```

| 课 | 一句话 | 需要模型 |
|---|---|---|
| [00 地图](00_map.md) | 跑一遍，认识报告长什么样 | 否 |
| [01 先看进去的是什么](01_parse.md) | 大多数"模型不行"其实是数据管道不行 | 否 |
| [02 用 trace 找问题](02_trace.md) | 四类问题各长什么样，先分类再改 | 否 |
| [03 随机性](03_stochastic.md) | 跑一次不算数，看通过率 | 🔑 |
| [04 失败案例进评测集](04_failure_to_dataset.md) | 修 bug 的正确顺序：先加用例，再改 | 🔑 |
| [05 改 prompt 要有对照](05_prompt_ab.md) | v1 vs v2，用表说话 | 🔑 |
| [06 缓存与成本](06_cache_cost.md) | 前缀不变才命中，一个时间戳让缓存归零 | 🔑 |
| [07 人在最后一道](07_hitl.md) | interrupt 停下来，换个进程再恢复 | 否 |

每课结尾有一句面试里能直接说的英文。做完 04 你就有了自己的 "v3"，那是这门课的作业。

## 排错的固定顺序（背下来）

1. **先看进去的是什么**：解析后的文本、切出来的条款，自己读一遍。
2. **再看 trace**：模型看到了什么、调了什么工具、返回了什么、最后说了什么。
3. **给问题分类**：检索 / 推理 / 格式 / 工具，四类修法完全不同。
4. **把失败案例存成用例**，跑一次确认它红。
5. **一次只改一个东西**，跑回归集，看它绿了、别的没红。

新手的反射是"不管什么问题都去改 prompt"。这门课的目的是把这个反射改掉。
