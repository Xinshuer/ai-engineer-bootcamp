# 04 失败案例进评测集 🔑

这是整门课的作业：**按正确顺序修一个真 bug**。bug 就是 02 课看到的那个：模型把样板条款交给人复核。

修 bug 的顺序：先把失败存成用例 → 跑一次确认它红 → 改一个东西 → 跑，看它绿了、别的没红。

## 第 1 步：存成用例（10 分钟）

打开 `evals/cases.json`，在 `cases` 数组里加一条。用 15.2 "Entire Agreement"，它最干净：

```json
{
  "id": "entire-agreement-boilerplate",
  "kind": "must_accept",
  "clause": {"clause_id": "15.2", "heading": "Entire Agreement", "text": "This Agreement, together with the Order Form, constitutes the entire agreement between the parties and supersedes all prior agreements relating to its subject matter."},
  "expect": {"verdict_in": ["accept"]}
}
```

`text` 从 `data/sample_contract.txt` 里原样复制。**用例的正确答案来自人的判断**，不是模型说的。这里你就是那个"领域专家"：一个双方对等的完整协议条款，不该交给律师看。

## 第 2 步：确认它红（3 分钟）

```bash
python evals/run_evals.py --mode deepseek --runs 3 --only entire-agreement-boilerplate
```

如果 DeepSeek 直接 3/3 过了，说明这个 bug 是本地模型特有的。那就换一条：`--mode local` 跑同一个用例（慢，每次 1–2 分钟），或者把昨天 7 条里的 8.2 也加进去。**没有红过的用例不能证明修复有效。**

## 第 3 步：改一个东西（10 分钟）

两个候选，**只选一个**：

- **prompt**：`review.py` 里 `SYSTEM_INSTRUCTIONS_V2` 第 5 条 "If you are genuinely unsure, call mark_for_review" 太宽。复制 V2 成 `SYSTEM_INSTRUCTIONS_V3`，把第 5 条改成"mark_for_review 只用于有具体未解决问题的条款；理由结论是可接受就必须 accept"。然后在 `PROMPTS` 字典加 `"v3"`，`config.py` 允许的版本加 `"v3"`。
- **代码**：`model_review` 里 `if ctx.marks and verdict.verdict == "accept": 降级为 flag`。这是我写的保守规则，也可以去掉。

先改 prompt（模型层的问题优先在模型层修）。**不要两个一起改**，否则不知道谁起了作用。

## 第 4 步：验证（5 分钟）

```bash
python evals/run_evals.py --mode deepseek --runs 3 --prompt v3 --only entire-agreement-boilerplate   # 它绿了吗
python evals/run_evals.py --mode deepseek --runs 3 --prompt v3                                        # 别的红了吗
```

对比 03 课的基线：高风险召回不能掉。掉了就是"搬动 bug"，改回去换一种改法。

## 第 5 步：进轨迹断言（进阶，可跳过）

`evals/harness.py` 的 `check()` 里加一种断言 `must_not_call_prefix`，用例里写 `"must_not_call_prefix": ["mark_for_review"]`。这样即使判定碰巧对了，多调的那次 `mark_for_review` 也会被抓住。这就是"评轨迹，不只评答案"。

## 面试一句话

"Every production miss becomes a test case first. I don't touch the prompt until I have a case that fails, and I don't ship until the whole set is green again."
