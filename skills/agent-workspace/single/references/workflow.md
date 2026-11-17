# 单机工作流

## 1. 角色

| 角色 | 职责 |
|------|------|
| Planner（可选） | 优先级、跨 BA 边界；首版不强制 |
| BA | 需求、验收、状态；唯一写 docs 状态的人 |
| Dev | 在 feature worktree 实现，handoff 后退出 |
| QA | 只读验证，报告交 BA |

没有 Deploy 角色；部署继续用现有流程。

## 1.1 角色不是进程层级

角色是**权限契约**，不是“必须由 BA spawn 的子进程”。

- 单机小项目可以由同一个人/同一个 agent 切换角色；
- 但 QA 的独立性会下降，**建议至少 QA 使用独立会话**；
- 技术约束仍然是：BA 写 status、Dev 只写 worktree、QA 只读不提交；
- `aw_single.py` 不检查父子进程关系，只看 `agent_id` / 可选 `AW_ROLE`。

## 2. BA

1. 在 docs 仓库创建 `demands/REQ-xxx/`；
2. 写 `demand.md` / `acceptance.md` / `status.md`；
3. `aw_single.py queue add REQ-xxx`；
4. `aw_single.py claim next`；
5. 把 worktree 路径、docs 路径、base sha 交给 Dev。

## 3. Dev

1. 只读 docs；
2. 在 worktree 实现；
3. 跑提交前快速门禁；
4. 写 `feature-meta/verification-report.md`；
5. 发 handoff，退出；
6. 不等 QA，不修改 docs 的 `status.md`。

## 4. QA

1. 只读 docs + worktree；
2. 跑验证；
3. 报告交 BA；
4. 不提交、不改状态。

## 5. 返工

- BA 在 docs 的 `status.md` 写 `return_reason`；
- BA spawn 新 Dev；
- 新 Dev 只读上一版报告 + return_reason，继续同一 worktree。

## 6. 消息与唤醒

本地消息，不走 bus，不写 git：

```text
.aw/
├── inbox/<agent>/<id>.json
├── msg-read/<agent>.json
├── wake/<agent>.json
└── watch-state.json
```

```bash
aw_single.py msg send --to ba-1 --type question --body "这个接口用 v2 吗？"
aw_single.py msg inbox
aw_single.py msg ack <id>
aw_single.py msg wait --timeout 120
aw_single.py watch --ensure --exec "bash start-agent.sh"
```

- `msg send/inbox/ack/wait`：同机通信，原子文件，无网络；
- `watch`：扫描未读消息，写 `.aw/wake/<agent>.json`；
  - `--exec` 可拉起 agent 进程；
  - `--ensure` 后台常驻，`--status` / `--stop` 管理；
  - 每次只写消息摘要（id/from/type/expect），不写正文；
- 需要审计的决策仍写 docs 的 `decisions.md`，消息只是通知。

## 7. 状态

docs 的 `status.md` 仍是唯一事实：

```text
草稿 → 已就绪 → 进行中 → 待验证 → 已验证 → 已完成
```

`aw_single.py` 不写 status，只负责 claim/worktree。
