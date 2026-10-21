# 契约管理（跨 BA 对齐接口）

## 1. 为什么需要

多个 BA 各自开发、各自派 Dev，最容易出的事故不是代码 bug，而是**契约漂移**：
A 改了请求字段，B 还在按旧约定实现，直到合并那天才发现。

所以契约必须是**文件**、有**版本**、有**消费方声明**、有**变更回执**。

## 2. 目录

```text
BA/contracts/
├── INDEX.md                  # 人工索引：契约 → owner → consumers
├── user-api/
│   ├── v1.md                 # 已批准版本，不可变
│   ├── v2.md
│   └── CURRENT               # 一行：v2
└── events/
    ├── v1.md
    └── CURRENT
```

## 3. 契约文件格式

```markdown
# user-api v2

- owner: pcA-ba-1
- consumers: [pcB-ba-1, pcA-ba-2]
- status: ratified          # draft | review | ratified | deprecated
- breaking: yes             # 相对上一版
- since: 2026-10-21

## 变更
- `POST /login` 增加可选 `mfaToken`

## 接口
| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|

## 兼容窗口
- v1 保留到 2026-11-04
```

规则：

| 规则 | 原因 |
|------|------|
| 已 `ratified` 的 `vN.md` 不可修改 | 历史必须可追溯 |
| 破坏性变更升大版本 | 并行支持，给消费方迁移窗口 |
| `CURRENT` 是唯一指针 | 读一个文件就知道该用哪版 |
| `owner` 只有一个 | 谁改谁负责 |

## 4. 消费方 pin

每个 feature worktree 在自己 manifest 里声明用哪版：

```json
// feature-REQ-002/.feature/manifest.json
{
  "req": "REQ-002",
  "agent_id": "pcB-ba-1",
  "contracts": { "user-api": 2 }
}
```

没有 pin 就等于"我不知道有契约"，检查会直接失败。

## 5. 变更流程

```text
① owner 写 contracts/user-api/v3.md（status: draft）
② owner 发消息：
   aw.py msg send --to pcB-ba-1,pcA-ba-2 --type contract-change \
     --contract user-api --version 3 --deadline 2026-10-22T00:00:00Z \
     --body "增加 mfaToken" --ref "BA/contracts/user-api/v3.md"
③ 消费方 aw.py msg ack <id> --ok
④ owner 把 status 改为 ratified，CURRENT → v3，提交
⑤ 消费方把 manifest 的 pin 改为 3
```

## 6. 检查规则

`aw.py contract check` 会逐条验证：

| # | 规则 | 级别 |
|---|------|------|
| R1 | `CURRENT` 指向的 `vN.md` 不存在 | FAIL |
| R2 | feature pin 的版本 < CURRENT | FAIL |
| R3 | feature pin 的版本 > CURRENT | FAIL |
| R4 | 契约声明的 consumer 在同一 feature 里没有 pin | FAIL |
| R5 | 契约未声明 consumers | WARN |
| R6 | 有 `contract-change` 但 consumer 未 ack | 超 deadline → FAIL，否则 WARN |

## 7. 命令

```bash
aw.py contract check [--strict] [--no-fetch] [--json]
```

- 默认读本机 bus（不发网络请求）；跨机协作时去掉 `--no-fetch`；
- `--strict`：WARN 也算失败，适合 CI；
- 退出码：0 通过 / 1 有问题。

示例：

```text
契约检查  （D:\proj）
契约      current  consumers  已 pin 的 feature
--------  -------  ---------  -------------------
user-api  v2       pcB-ba-1   feature-REQ-001(v1)
[FAIL] user-api: feature-REQ-001 pin v1 < current v2
[WARN] user-api v2 等待 ack: pcB-ba-1
结论: 1 FAIL / 1 WARN
```

## 8. 挂到门禁上

| 时机 | 做法 |
|------|------|
| BA 合并前 | `aw.py contract check`，FAIL 不放行 |
| CI | 在 develop 的 MR 流水线里跑 `--strict --no-fetch`（CI 无本地 bus 时只看 pin） |
| 每日巡检 | `aw.py contract check` + `aw.py claim doctor` |

## 9. 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 检查说"未启用契约管理" | `BA/contracts/` 不存在 | 不需要契约的项目可以忽略 |
| consumer 一直不 ack | 消息没送到 / 人不在 | 看 `msg list --all`，或换人代确认 |
| pin 忘记升级 | 变更后没改 manifest | 改 pin，或由 `claim release` 前强制提醒 |
| 契约改了但版本没升 | 直接改了 ratified 文件 | 回滚该文件，开新版本 |

## 10. 与消息通道的关系

- 契约正文：`demand` 分支（可 review、可追溯）
- 变更通知与回执：`bus` 分支（空 commit）
- pin：feature 分支的 `.feature/manifest.json`

三者由 `contract check` 串起来：**文件有没有、谁该看、有没有确认、实现有没有跟上**。
