# 01 先看进去的是什么

冲刺计划里排第一的根因："解析丢内容"。demo 用的是干净文本，真实 PDF 有页眉页脚、跨页条款。这一课模拟这个故障。

## 跑

```bash
python -m clausecheck clauses data/sample_contract.txt      # 先看正常切分：29 条 + 15 个章节标题
python "G:\Clause Check 编程营\lessons\sim_page_break.py"                          # 再看分页后的两种处理
```

第二条命令把示例合同"打印"成 5 页，每页底部加一行页脚，并且故意让一页在 `8.1 Cap on Liability` 标题之后断开。然后用两种方式处理：

- **A 逐页切分**（错误做法）：8.1 的标题在第 3 页末尾、正文在第 4 页开头。切出来的 8.1 正文只剩页脚 "CloudNotes Confidential / Page 3 of 5"，真正的正文在第 4 页开头，上面没有标题，被丢掉了。`refs=[]`，所以它也不会去读第 12 条。**模型拿到的是一行页脚，然后一本正经地判它 accept。**
- **B 先拼页再切分**（`parse.py` 的做法）：先把重复的页脚删掉、所有页拼成一段，再切。8.1 完整，`refs=['12']`。

## 看

脚本会打印 A 和 B 各自切出的 8.1，以及 A 里页脚混进了哪几条正文（"页眉页脚插在段落中间"）。两种做法切出的条款数一样多，光看数量发现不了问题，**得抽几条打开读**。

## 为什么先讲这个

上线后有人说"这条很明显的责任上限没标出来"，你的第一反应不该是改 prompt，而是：**送进模型的文本里有这条吗？** 这一步在 trace 里看 `clause.text`，或者直接跑 `clauses` 命令。冲刺计划的故事 3 就是这个。

## 动手

在训练营的 `lessons/sim_page_break.py` 里把 `BREAK_AFTER` 改成 `"4.2 Automatic Renewal"`，再跑。这次消失的是哪条？

## 面试一句话

"Before touching the prompt I read the trace: the model never saw the clause. It was a pagination bug in the parser, not a model problem."
