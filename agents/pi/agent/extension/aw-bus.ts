// aw-bus: 把 aw MCP 的 notifications/message 转成一次会话轮次
// 安装位置 ~/.omp/agent/extensions/aw-bus.ts，重启 omp 后生效。
// 自证日志：~/.omp/logs/aw-bus-bridge.log（loaded / recv / steer / error）
import { appendFileSync, mkdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { homedir } from 'node:os'

const seen = new Set<string>()
const LOG = process.env.AW_BUS_LOG
  || join(homedir(), '.omp', 'logs', 'aw-bus-bridge.log')
const SELF = String(process.env.AW_AGENT_ID || '').trim()
const SESSION = String(process.env.AW_SESSION_ID || process.env.PI_SESSION_ID || process.env.DSH_SESSION_ID || '').trim()
const ROLE = String(process.env.AW_ROLE || '').trim().toLowerCase()
const SUBAGENT = /^(1|true|yes|on)$/i.test(String(process.env.AW_SUBAGENT || process.env.AW_NO_MSG || ''))

function note(line: string) {
  try {
    mkdirSync(dirname(LOG), { recursive: true })
    appendFileSync(LOG, new Date().toISOString() + ' ' + line + '\n')
  } catch {}
}

function readJson(file: string): any {
  try { return JSON.parse(readFileSync(file, 'utf8')) } catch { return undefined }
}

export default function (pi) {
  const canReceive = !SUBAGENT && (!ROLE || ROLE === 'ba' || ROLE === 'planner')
  note('bridge loaded pid=' + process.pid + ' agent=' + (SELF || '-') + ' session=' + (SESSION || '-') + ' role=' + (ROLE || '-'))
  if (!SELF || !canReceive) {
    note('disabled no-agent-or-subagent self=' + (SELF || '-') + ' sub=' + SUBAGENT + ' role=' + (ROLE || '-'))
    return
  }
  pi.on('mcp_notification', async (event) => {
    try {
      if (!event || event.server !== 'aw') return
      if (event.method !== 'notifications/message') return
      const data = (event.params && event.params.data) || {}
      const recipient = String(data.agent || '').trim()
      if (recipient && recipient !== 'all' && recipient !== SELF) {
        note('skip agent ' + recipient + ' != ' + SELF)
        return
      }
      if (data.repo && SESSION) {
        const map = readJson(join(String(data.repo), '.aw', 'sessions', SELF + '.map.json'))
        if (map && map.session_authoritative === true && map.session_id && String(map.session_id) !== SESSION) {
          note('skip session ' + SESSION + ' != ' + map.session_id + ' agent=' + SELF)
          return
        }
      }
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
