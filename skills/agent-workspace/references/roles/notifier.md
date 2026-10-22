# Notifier 子 Agent（只读消息，不处理）

## 1. 为什么需要

BA 不会主动读 bus。靠"记得去读"是不可靠的，所以拆成两层：

| 层 | 作用 | 保证 |
|----|------|------|
| **门禁** | `claim next` 发现未读消息直接拒绝（exit 4） | 一定不会漏 |
| **Notifier** | 只读子 agent 把消息整理成摘要 | 读得快、读得全 |

门禁保证"不会忘"，Notifier 保证"读得省"。

## 2. 定位

| 项 | 值 |
|----|----|
| 生命周期 | 一次性：spawn → 读 → 报告 → 退出 |
| 写入能力 | **无** |
| 可执行命令 | `msg inbox --json`、`msg show <id>`、`msg list --all` |
| 禁止命令 | `msg send` / `msg ack` / `msg flush` / `claim` / `git` / 任何写文件 |
| 输出 | 结构化摘要，不含处置动作 |

## 3. 硬限制（写进 prompt）

```text
你是 Notifier，只读。允许的命令只有：
  aw.py --agent <me> msg inbox --json --no-advance
  aw.py --agent <me> msg show <id>
  aw.py --agent <me> msg list --all --json
禁止：msg send / ack / flush、claim、git、写文件、改状态、代替 BA 回复。
读消息必须带 --no-advance（不推进游标）——你只读，不消费。
你只负责"把消息整理出来"，任何决策交回 BA。
```

> 光靠 prompt 不够。落地时还要在平台侧给这个子 agent **只读沙箱**（不挂 write_roots、不开放写工具）。

## 4. 输出格式

```markdown
# 消息摘要（agent: pcA-ba-1）

## 需要我处理的（3）
| id | from | type | 主题 | 截止 |
|----|------|------|------|------|
| a1b2 | pcB-ba-1 | contract-change | user-api@3 | 10-22 |

## 仅知会（5）
- 2026-10-21T07:52Z pcA-ba-3 fyi：今晚 20:00 冻结 develop

## 建议（仅供参考，由 BA 决定）
- a1b2 需要 ack；c3d4 的 question 需要一个答复
```

## 5. BA 怎么用

```text
派 Notifier 的 prompt：
  角色：Notifier（只读），规范见 <skill>/references/roles/notifier.md
  我的身份：pcA-ba-1
  任务：读一遍我的未读消息，输出摘要；不要回复、不要 ack、不要改任何文件
```

拿到摘要后，BA 自己决定：

- 要不要 `msg ack`；
- 要不要看 `msg show <id>` 的全文；
- 要不要调整当前任务。

## 6. 触发时机

| 时机 | 谁触发 |
|------|--------|
| 会话启动 | BA 自己（或调度器） |
| 认领前 | **门禁强制**（不读就 exit 4） |
| 合并前 | BA 的清单 |
| 长任务中途 | 外部调度器每 N 分钟拉一次 |

## 6.1 游标：读但不算已读

Notifier 用 `--no-advance`，所以它跑多少次都不会消耗消息。
游标只由 BA 自己跑 `msg inbox` 时推进——这样即使 Notifier 中途失败，消息也不会丢。
代价：BA 看到摘要后仍需跑一次 `msg inbox`（可加 `--limit 0` 只看计数）来放行门禁。

## 7. 为什么不做长驻

- 子 agent 通常是任务型，长驻需要平台支持；
- 常驻 + 能回复 = 第二个 BA，职责边界会糊；
- 门禁已经保证不漏消息，Notifier 只是提速，不需要实时。

如果平台支持后台任务，可以把它做成"每 10 分钟跑一次的一次性任务"，但**仍然只读**。
