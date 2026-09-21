# 07 人在最后一道：停下来，换个进程再恢复

危险操作（发给对方、写外部系统、花钱）必须由人批准。做法不是在 prompt 里写"先问用户"（那是建议），而是框架层拦截（那是强制）。这一课看 LangGraph 的 `interrupt()` + checkpoint。

## 跑：一个进程里停下再继续

```bash
python -m clausecheck review data/sample_contract.txt --mode mock --graph --approve ask --thread lesson-7
```

审完后会停下，列出待批的 redline，问你 `Apply to exported copy? [y/N]`。输 `y`，多出一个 `.redlined.txt`。

## 跑：停下来，进程退出，另一个进程恢复

这才是 checkpoint 的意义。审批可能几小时后才来，中间服务会重启。

第一个进程，跑到中断就退出（Ctrl+C 或者直接让它停）：

```bash
python -c "
from clausecheck.config import Settings
from clausecheck.graph import run_graph
run_graph('data/sample_contract.txt', 'data/lesson7.report.json', 'lesson-7b', Settings(mode='mock'), decide=None)
"
```

`decide=None` 表示"没人来批"，图停在 approve 节点，状态已经写进 `data/checkpoints.sqlite`。

第二个进程，先看有什么在等，再批准：

```bash
python -c "
from clausecheck.config import Settings
from clausecheck.graph import pending_interrupt, resume
s = Settings(mode='mock')
p = pending_interrupt('lesson-7b', s)
print('waiting:', [r['clause_id'] for r in p['redlines']] if p else None)
print(resume('lesson-7b', True, s).get('exported'))
"
```

第一行打印在等的条款；第二行从同一个 checkpoint 恢复，导出。**批准后由代码套用已定位的 redline，模型不再参与**，它没机会变卦。

## 看 `graph.py`

五个概念：`State`（状态字典）、节点（普通函数）、条件边（`route`：有 redline 才走 approve）、`checkpointer`（SQLite）、`interrupt()`。说得出为什么需要每一个，面试里 LangGraph 就够了。

## 为什么线性流水线（`pipeline.py`）不用图

流程固定，plain Python 就够；第一个真正需要框架的场景是"停下来等人，换个进程继续"。先手写，遇到第一个需要 checkpoint 的场景再上框架。

## 动手

在 `graph.py` 的 `approve` 节点里，interrupt 的 payload 只有 `clause_id / anchor / replacement / rationale`。审批的人还想看什么？加进去（比如 `risk_level` 和 `rule_ids`），再跑一遍第二个进程看它出现在 `waiting` 里。

## 面试一句话

"Anything irreversible goes through an interrupt with persisted state. The agent proposes, a person approves, and the approved call is executed by code, not re-decided by the model."
