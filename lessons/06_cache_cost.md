# 06 缓存与成本 🔑

DeepSeek 和 Anthropic 都按**前缀**缓存 prompt：前面每个字节都一样才命中，命中的部分便宜十倍。这一课让你亲眼看到缓存命中和归零。

## 跑

```bash
python learn/cache_experiment.py
```

脚本用 DeepSeek 审同一条条款 3 次，打印每次的 `cache_read`（命中 token）和 `input`（未命中 token）；然后在 system prompt **最前面**加一个时间戳，再审 3 次。

## 看

第一组：第 1 次几乎全是 input（写缓存），第 2、3 次大部分变成 cache_read。
第二组：时间戳每次不同，前缀从第一个字节就变了，cache_read 一直是 0。

一个日期、一个请求 id、一个用户名，放在 system 开头就能让缓存永远不命中，而且账单上看不出来。所以顺序是：**系统指令 → 工具定义 → 合同全文 → 当前条款**，变的放最后。

## 算成本

拿 03 课跑完整套评测的 `total tokens`，或者一份合同的报告里的 `summary.tokens`，乘单价：

```
成本 = input × 输入单价 + cache_read × 缓存单价 + output × 输出单价   （单价在 config.py 的 PRICES，每百万 token）
```

报告里 `summary.estimated_cost_usd` 已经算好了。给客户报价时报**区间**，并说清什么会让它翻倍：合同变长、多一步 rerank、换大模型。

## 动手

把 `.env` 里 `CLAUSECHECK_FULL_CONTRACT` 设为 `0`（只给索引，不给全文）再跑一次 `cache_experiment.py`。input 少了多少？命中率变了吗？这就是"上下文是预算"的取舍：给全文，每条都能看到全局但每次都在付；给索引，便宜但模型只看得到它主动取的。

## 面试一句话

"Caching is a prefix match. If cache_read_input_tokens is zero across identical requests, something volatile is sitting in the prefix, and that's a bug even though nothing errors."
