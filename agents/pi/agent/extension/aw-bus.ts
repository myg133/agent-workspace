// aw-bus: 把 aw MCP 的 notifications/message 转成一次会话轮次
// 安装位置 ~/.omp/agent/extensions/aw-bus.ts，重启 omp 后生效。
// 自证日志：~/.omp/logs/aw-bus-bridge.log（loaded / recv / steer / error）
import { appendFileSync } from 'node:fs'

const seen = new Set<string>()
const LOG = '/home/myg133/.omp/logs/aw-bus-bridge.log'

function note(line: string) {
  try {
    appendFileSync(LOG, new Date().toISOString() + ' ' + line + '\n')
  } catch {}
}

export default function (pi) {
  note('bridge loaded pid=' + process.pid)
  pi.on('mcp_notification', async (event) => {
    try {
      if (!event || event.server !== 'aw') return
      if (event.method !== 'notifications/message') return
      const data = (event.params && event.params.data) || {}
      const id = String(data.id || '')
      note('recv ' + JSON.stringify(data))
      if (!id || seen.has(id)) return
      seen.add(id)
      if (seen.size > 500) seen.delete(seen.values().next().value as string)
      const text =
        `[bus ${id}] ${data.from || '?'} -> ${data.agent || ''} ` +
        `type=${data.type || ''} expect=${data.expect || 'none'} at=${data.at || ''}\n` +
        `用 msg_inbox 取正文（msg_show ${id} 看单条）。`
      pi.sendUserMessage(text, { deliverAs: 'steer' })
      note('steer ' + id)
    } catch (err) {
      note('error ' + String(err))
    }
  })
}
