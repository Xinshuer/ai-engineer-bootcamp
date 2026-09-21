# 00 地图：跑一遍，认识报告

## 跑

```bash
python -m clausecheck review data/sample_contract.txt --mode mock --out data/map.report.json
```

终端会逐条打印，最后一张表。这是这个项目的全部输出：每条条款一个判定（accept / flag / redline）、风险等级、命中的 playbook 规则、调过的工具。

## 看

打开 `data/map.report.json`，找到 `clause_id` 为 `"8.1"` 的那条，看它的四块：

| 字段 | 是什么 |
|---|---|
| `clause` | 切出来的原文：编号、标题、正文、`refs`（它引用了哪些条款） |
| `verdict` | 模型（这里是规则）的结论：判定、topic、理由、依据的规则 |
| `redline` | 如果建议改：改哪句（`matched_text`）、改成什么、diff |
| `trace` | 过程：调了哪些工具、几步、多少 token、多久、有没有报错 |

`trace.tool_calls` 里应该有 `get_clause:12`。8.1 自己写的是"双方责任上限相等"，是第 12 条把客户这边的上限抽掉了。**只看 8.1 会判错，看了 12 才对**。整个项目最重要的一条就是它。

## 动手

把 `data/sample_contract.txt` 里第 12 条最后一句（"For the avoidance of doubt..."）删掉，再跑一次。8.1 的判定变了吗？为什么？（改完记得 `git checkout data/sample_contract.txt` 还原。）

## 面试一句话

"Every verdict points back to the clause text and lists which tools were called, so I can always answer 'why did it say that' without re-running the model."
