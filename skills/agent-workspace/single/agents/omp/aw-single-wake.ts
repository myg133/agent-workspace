// aw-single-wake: 读取本地 .aw/wake/<agent>.json，把新消息转成一次 omp 用户消息。
// 安装：复制到 ~/.omp/agent/extensions/aw-single-wake.ts，重启 omp。
// 需要环境变量：AW_AGENT_ID；AW_SINGLE_ROOT 可选（默认从 cwd 向上找 .aw/config.json）。
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'

const POLL_MS = 2000
const MIN_INTERVAL_MS = 10000
const MAX_PARENT_LOOKUP = 8

const LOG = process.env.AW_OMP_WAKE_LOG || join(homedir(), '.omp', 'logs', 'aw-single-wake.log')
try { mkdirSync(dirname(LOG), { recursive: true }) } catch {}

function note(line) {
  try { appendFileSync(LOG, new Date().toISOString() + ' ' + line + '\n') } catch {}
}

function readJson(file) {
  try { return JSON.parse(readFileSync(file, 'utf8')) } catch { return undefined }
}

function findRoot() {
  const explicit = String(process.env.AW_SINGLE_ROOT || '').trim()
  if (explicit) return resolve(explicit)
  let dir = resolve(process.cwd())
  for (let i = 0; i < MAX_PARENT_LOOKUP; i += 1) {
    if (existsSync(join(dir, '.aw', 'config.json'))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return ''
}

export default function (pi) {
  const agent = String(process.env.AW_AGENT_ID || '').trim()
  const root = findRoot()
  if (!agent || !root) {
    note('disabled agent=' + (agent || '-') + ' root=' + (root || '-'))
    return
  }
  const wakePath = join(root, '.aw', 'wake', agent + '.json')
  const seenPath = join(root, '.aw', 'omp-wake-seen', agent + '.json')
  const sessionPath = join(root, '.aw', 'sessions', agent + '.json')
  const seen = new Set()
  let lastWakeAt = 0

  function writeSession(pid) {
    try {
      mkdirSync(dirname(sessionPath), { recursive: true })
      const now = new Date().toISOString()
      const record = {
        agent_id: agent,
        role: String(process.env.AW_ROLE || '').trim(),
        session_id: String(process.env.AW_SESSION_ID || '').trim() || ('proc-' + process.pid),
        pid: Number(pid || 0),
        pid_started_at: pid ? new Date(Date.now() - process.uptime() * 1000).toISOString() : '',
        host: String(process.env.COMPUTERNAME || process.env.HOSTNAME || ''),
        last_seen: now,
      }
      writeFileSync(sessionPath, JSON.stringify(record, null, 2))
    } catch (error) {
      note('session-error ' + String(error))
    }
  }

  writeSession(process.pid)
  const sessionTimer = setInterval(() => writeSession(process.pid), 30000)
  process.on?.('exit', () => writeSession(0))

  const initial = readJson(seenPath)
  if (Array.isArray(initial?.ids)) {
    for (const id of initial.ids) seen.add(String(id))
  } else {
    // 首次安装：把当前 wake 文件当历史，避免一启动就补旧消息。
    const current = readJson(wakePath)
    for (const m of current?.messages || []) if (m?.id) seen.add(String(m.id))
    saveSeen()
  }

  function saveSeen() {
    try {
      mkdirSync(dirname(seenPath), { recursive: true })
      writeFileSync(seenPath, JSON.stringify({ ids: [...seen].slice(-2000) }, null, 2))
    } catch (error) {
      note('save-seen-error ' + String(error))
    }
  }

  function tick() {
    const data = readJson(wakePath)
    const messages = Array.isArray(data?.messages) ? data.messages : []
    const fresh = []
    for (const m of messages) {
      const id = String(m?.id || '')
      if (!id || seen.has(id)) continue
      seen.add(id)
      fresh.push(m)
    }
    if (fresh.length === 0) return
    saveSeen()
    note('recv ' + fresh.map(m => m.id).join(','))
    if (Date.now() - lastWakeAt < MIN_INTERVAL_MS) return
    lastWakeAt = Date.now()
    const lines = fresh.slice(0, 5).map(m => {
      const expect = m?.expect ? '/' + m.expect : ''
      const subject = m?.subject ? ' ' + m.subject : ''
      return '- ' + m.id + ' ' + (m.from || '') + ' ' + (m.type || '') + expect + subject
    }).join('\n')
    const text = '[local] 收到 ' + fresh.length + ' 条消息（' + agent + '）：\n' + lines +
      '\n\n请用 msg inbox 取正文；纯 fyi 可忽略。'
    try {
      pi.sendUserMessage(text, { deliverAs: 'steer' })
      note('steer ' + fresh.length)
    } catch (error) {
      note('steer-error ' + String(error))
    }
  }

  const timer = setInterval(tick, POLL_MS)
  note('loaded agent=' + agent + ' root=' + root)
  // sessionTimer 由 event loop 持有；不要 unref，否则插件进程可能提前退出。
  pi.on?.('session_start', () => tick())
  // 保留 timer 引用，避免打包器/宿主把 interval 清掉。
  void timer
  void sessionTimer
}
