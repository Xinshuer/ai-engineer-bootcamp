# 02 用 trace 找问题

调 LLM 系统没有 stack trace，只有一条"进去什么、出来什么"的链。第一步不是改，是看链条上坏在哪一环，然后分类。

## 四类问题

| 类型 | 在 trace 里看哪 | 典型症状 | 修什么 |
|---|---|---|---|
| 检索 | 送进模型的文本里有没有答案 | 说"合同未提及"，其实提了 | 解析、切分、`refs`、工具返回 |
| 推理 | 证据在，结论错 | 读了第 12 条还是判 accept | prompt、示例、拆步骤、换模型 |
| 格式 | 输出对但解析报错 | JSON 外面多一句话、枚举大小写错 | 结构化输出、校验回送、重试一次 |
| 工具 | 调了什么、参数是什么 | 用 search 查已知 id、少传参数 | 工具描述、参数 schema、减少工具数 |

**为什么先分类**：四类修法完全不同。检索问题改 prompt 永远修不好。

## 跑

`learn/inspect_report.py` 把一份报告里"值得看一眼"的条款挑出来：

```bash
python -m clausecheck review data/sample_contract.txt --mode mock --out data/map.report.json
python learn/inspect_report.py data/map.report.json
```

它检查这几个信号：判定不是 accept 但理由里写着 "standard / acceptable / consistent with"（模型改口了）；调了 `mark_for_review`（模型要人看）；redline 但 anchor 没定位到；步数到了上限（可能在兜圈）；有 error。

mock 模式下会列出 4 条，全是规则自己判的 redline / flag，被"理由里出现 standard"这个探测词误伤了。**探测脚本也有误报，它只负责把你的眼睛引过去，结论要自己读理由**。

真正有意思的是拿模型跑出来的报告看。项目里保留了一份本地 Qwen 用 v2 prompt 跑的：

```bash
python learn/inspect_report.py data/sample_contract.local.v2.report.json
```

会列出 11 条，读完理由后能分成三组：

1. **改口**（5.1、6.1、6.3、8.2、10.2、11.3、15.2）：全是样板条款，理由都说"标准、符合 playbook"，但判定是 flag，`tool_calls` 里都有 `mark_for_review`。证据对、结论对、多做了一个动作。这是**推理 / 工具类**问题，不是解析（文本完整），不是格式（JSON 合法）。
2. **兜圈**（2.1、15.1）：判定 accept 没错，但连着调了 4 次 `lookup_playbook`，换着 topic 试，撞到 6 步上限才停。这是**工具类**问题：模型不确定 topic 时没有一个"我不知道"的出口。多花的 4 次调用在生产里就是钱和延迟。
3. **误报**（9.1）：redline 是对的，只是理由里用了 "consistent with" 描述别的东西，探测词匹配上了。跳过。

## 动手

对着第 1 组，回答：修这个问题该动哪一层？prompt 里哪句话让模型觉得"应该叫人看看"？（答案在 `review.py` 的 v2 prompt 第 5 条，以及 `model_review` 里"被 mark 就降级为 flag"那两行代码。）先别改，04 课会让你按正确顺序改。

再对着第 2 组想：怎么让模型少兜圈？（提示：`lookup_playbook` 返回 `"rules": []` 时，附带的 `note` 已经列出了所有已知 topic。够吗？还是 prompt 里该说"一个 topic 查不到就用 other，不要换着试"？）

## 面试一句话

"I evaluate the trajectory, not just the answer: was each tool call justified given what the model had at that step?"
