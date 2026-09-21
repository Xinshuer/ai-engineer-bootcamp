# 05 改 prompt 要有对照 🔑

"我改了 prompt，感觉好了"不是工程。这一课把感觉变成一张表。

## 跑

两版 prompt 各跑一遍（每遍 9 条 × 3 次，DeepSeek 约 5 分钟）：

```bash
python evals/run_evals.py --mode deepseek --runs 3 --prompt v1 --out evals/results.deepseek.v1.json
python evals/run_evals.py --mode deepseek --runs 3 --prompt v2 --out evals/results.deepseek.v2.json
```

## 看

两张表并排比。关注三个数：

1. **高风险召回**：v2 不能比 v1 低。漏掉一条高风险条款的代价最大。
2. **必须放过用例的误报**：v2 应该更少。这是 v2 想修的。
3. **哪条变了**：一条从 3/3 掉到 1/3 就是回归，即使总分更高也要查。

本地模型昨天的结果（README 里那张表）：召回 1.00 → 1.00，误报 3/6 → 1/6。DeepSeek 会不一样，**不同模型对同一份 prompt 的反应不同**，这也是为什么模型版本要钉死、换模型要重跑回归集。

## v1 和 v2 差在哪

`review.py` 里两段 prompt 放在一起，diff 一下：

- v1："playbook 沉默 → flag"；v2："样板条款默认 accept，不要因为没规则就 flag"。
- v2 明说 `preferred_language` 是 redline 用的措辞，不是检查清单。
- v2 把 `propose_redline` 限制在 redline 判定内。

每一条改动都对应昨天看到的一个具体失败。**prompt 改动要能指回一个用例**，指不回去的改动不要做。

## 动手

如果你 04 课写了 v3，再跑一遍 `--prompt v3`，三列并排。写三行话总结：v3 修了什么、代价是什么、下一个要修的是哪条。这三行就是面试里的故事 5。

## 面试一句话

"I wrote down the question I couldn't answer, then picked the tool. Now every prompt change comes with a number instead of a feeling."
