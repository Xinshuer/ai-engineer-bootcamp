# 03 随机性：跑一次不算数 🔑

同一个输入，模型两次给的答案可能不同。所以一条测试的结果不是"过 / 不过"，是**通过率**。

## 跑

先只跑一条用例，5 次：

```bash
python evals/run_evals.py --mode deepseek --runs 5 --only mutual-warranty-disclaimer
```

这条是"AS IS 免责声明，必须放过"。昨天本地模型 v2 是 1/2，属于"抽风"。DeepSeek 跑 5 次，看它是稳过、稳挂、还是抽风。**三档里只有抽风是最难修的**，因为你改了 prompt 也不知道是修好了还是运气。

## 看

表里两列：

- `pass rate`：5 次过几次。
- `pass^k`：是否 5 次全过。无人值守的 Agent 要看这个。单次 90% 的成功率，连续 5 次全对只有 59%。

## 温度 0 不等于确定

试试 `CLAUSECHECK_TEMPERATURE=0`，再跑 5 次。一般还是会有差异（GPU 求和顺序、批处理、供应商换权重）。更重要的是：**生产用什么参数就用什么参数测**，测 0 上线 0.7 等于没测。

## 跑几次够

5–10 次。它分不出 90% 和 95%，但分得出"稳过 / 稳挂 / 抽风"，抽风的才是要修的。

## 动手

跑完整套（9 条 × 3 次，约 5 分钟，几分钱）：

```bash
python evals/run_evals.py --mode deepseek --runs 3
```

记下 `high-risk recall` 和哪几条没到 3/3。这是你的**基线**，04 和 05 课要拿它对比。

## 面试一句话

"A single green run proves nothing. I sample each case N times and gate on the pass rate, with pass^k for anything that runs unattended."
