# {契约名} v{版本}

- owner: {agent_id}
- consumers: [{agent_id, ...}]
- status: draft        # draft | review | ratified | deprecated
- breaking: no         # yes / no（相对上一版）
- since: {YYYY-MM-DD}

## 变更
- {相对上一版改了什么}

## 接口

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| POST | /xxx | {...} | {...} |

## 错误码

| code | 含义 |
|------|------|

## 兼容窗口

- 上一版 `v{上一版}` 保留到 {YYYY-MM-DD}，之后拒绝
