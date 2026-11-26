# 通信层：Port 与 Adapter

角色只依赖通信 Port，不直接依赖 bus / MQTT / MCP。

## Port

~~~text
send(to, type, body, expect, ref) -> message_id
inbox(agent, session) -> messages
wait(agent, session, timeout) -> message
ack(agent, session, message_id)
~~~

约束：

- 收件人按 agent_id 寻址；投递按 authoritative session 路由；
- 同一 message_id 去重；
- 子 Agent 默认 `can_receive=false`；
- 发送失败不能丢消息：本地 outbox / bus 兜底 / MQTT 重试由 adapter 处理。

## 不属于 Port 的策略

- `msg report` 的目标选择（Planner 还是广播）：**BA 角色策略**；
- claim / WIP=1：domain；
- handoff 内容：domain；
- 子 Agent 是否可以收消息：角色契约 + session 规则。

## Adapter

| Adapter | 作用 |
|---------|------|
| local inbox | 同机落盘、已读、ack |
| Git bus | 跨机审计与兜底 |
| MQTT | 实时唤醒、presence |
| MCP | workspace 客户端工具 |
| OMP / DSH wake | 把消息转成会话轮次 |

细节：

- [消息格式与 ack](../global/messaging.md)
- [通道配置](../global/transport.md)
- [触发与 watcher](../global/trigger.md)
- [MCP](../global/mcp.md)
- [唤醒插件](../global/agent-plugins.md)
- [single MQTT + bus](../single/mqtt-bus-protocol.md)
