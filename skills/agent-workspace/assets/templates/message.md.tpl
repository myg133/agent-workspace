[msg] {type} {subject} -> {to}

---
id: {8位十六进制}
from: {我的 agent_id}
to: [{agent_id 或 all 或 role:ba}]
cc: [{可选}]
at: {2026-10-21T07:40:12Z}
type: {fyi|question|blocker|handoff|contract-change|contract-ack|decision}
ref: BA/contracts/{契约名}/v{N}.md @ {commit-sha}
contract: {契约名}
version: {版本号}
deadline: {2026-10-22T00:00:00Z}
thread: {话题 id}
priority: {p0|p1|p2}
---
{正文，≤ 2000 字符；契约正文放 BA/contracts/，这里只写摘要}
