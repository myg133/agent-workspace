import fs from 'node:fs'
import path from 'node:path'

export const name = 'aw-wake'
export const inject = ['agents']

const DEFAULT_TYPES = ['question', 'blocker', 'handoff', 'decision', 'contract-change']
const DEFAULT_EXPECT = ['reply', 'ack']

/**
 * Watches the agent-workspace wake file of one agent and wakes the matching
 * DSH agent with agent.followup() when a message needs action.
 */
export function apply(ctx, config) {
  const cfg = config ?? {}
  const repoRoot = String(cfg.repoRoot ?? '').trim()
  const agentId = String(cfg.agentId ?? '').trim()
  if (!repoRoot || !agentId) {
    ctx.logger?.warn?.('aw-wake: repoRoot 或 agentId 未配置，插件不生效')
    return
  }

  const pollMs = Math.max(500, Number(cfg.pollMs ?? 2000))
  const minIntervalMs = Math.max(0, Number(cfg.minIntervalMs ?? 10000))
  const wakeTypes = new Set((cfg.wakeTypes ?? DEFAULT_TYPES).map(String))
  const wakeExpect = new Set((cfg.wakeExpect ?? DEFAULT_EXPECT).map(String))
  const wakeDir = cfg.wakeDir ? String(cfg.wakeDir) : path.join(repoRoot, '.aw', 'wake')
  const wakePath = path.join(wakeDir, `${agentId}.json`)
  const seenPath = path.join(repoRoot, '.aw', 'aw-wake-seen.json')
  const debugPath = path.join(repoRoot, '.aw', 'aw-wake-debug.json')

  const seen = new Set()

  function readJson(file) {
    try {
      return JSON.parse(fs.readFileSync(file, 'utf8'))
    } catch {
      return undefined
    }
  }

  function saveSeen() {
    try {
      fs.writeFileSync(seenPath, JSON.stringify({ ids: [...seen].slice(-2000) }, null, 2))
    } catch (error) {
      ctx.logger?.warn?.(`aw-wake: 写 seen 失败 ${String(error)}`)
    }
  }

  function readWake() {
    const raw = readJson(wakePath)
    return Array.isArray(raw?.messages) ? raw.messages : []
  }

  function cwdOf(agent) {
    const session = agent?.session
    const candidates = [session?.meta?.cwd, session?.header?.cwd, session?.cwd, agent?.options?.cwd]
    for (const value of candidates) {
      if (typeof value === 'string' && value.trim() !== '') return value
    }
    return ''
  }

  function matches(agent) {
    const cwd = cwdOf(agent)
    if (!cwd) return false
    try {
      return path.resolve(cwd).toLowerCase() === path.resolve(repoRoot).toLowerCase()
    } catch {
      return false
    }
  }

  function liveAgents() {
    try {
      return ctx.agents.list() ?? []
    } catch {
      return []
    }
  }

  function writeDebug(extra) {
    try {
      const agents = liveAgents().map(agent => ({
        id: String(agent?.id ?? ''),
        cwd: cwdOf(agent),
        status: agent?.status ?? '',
        matched: matches(agent),
      }))
      fs.writeFileSync(
        debugPath,
        JSON.stringify({ at: new Date().toISOString(), repoRoot, agentId, agents, ...extra }, null, 2),
      )
    } catch {
      // debug output is best effort only
    }
  }

  // Seed from the current file: a plugin restart must not replay old messages.
  const initial = readJson(seenPath)
  if (Array.isArray(initial?.ids)) for (const id of initial.ids) seen.add(String(id))
  for (const message of readWake()) {
    if (message?.id) seen.add(String(message.id))
  }

  let lastWakeAt = 0

  function tick() {
    const fresh = []
    for (const message of readWake()) {
      const id = String(message?.id ?? '')
      if (!id || seen.has(id)) continue
      seen.add(id)
      fresh.push(message)
    }
    if (fresh.length === 0) return
    saveSeen()

    const wanted = fresh.filter(
      message => wakeTypes.has(String(message?.type ?? '')) || wakeExpect.has(String(message?.expect ?? '')),
    )
    if (wanted.length === 0) return

    writeDebug({ pending: wanted.map(message => String(message.id)) })

    if (Date.now() - lastWakeAt < minIntervalMs) return

    const targets = liveAgents().filter(matches)
    if (targets.length === 0) {
      ctx.logger?.info?.(`aw-wake: ${wanted.length} 条消息待处理，但没有 cwd 匹配 ${repoRoot} 的活跃会话`)
      return
    }

    const lines = wanted
      .slice(0, 5)
      .map(message => {
        const expect = message?.expect ? `/${message.expect}` : ''
        const subject = message?.subject ? ` ${message.subject}` : ''
        return `- ${message.id} ${message.from ?? ''} ${message.type ?? ''}${expect}${subject}`
      })
      .join('\n')
    const text = `[bus] 收到 ${wanted.length} 条需要处理的消息（${agentId}）：\n${lines}\n\n请用 msg_inbox 拉取并处理；fyi 可忽略。`

    for (const agent of targets) {
      try {
        agent.followup({ content: [{ type: 'text', text }], source: { kind: 'user' } })
        lastWakeAt = Date.now()
        ctx.logger?.info?.(`aw-wake: woke ${String(agent?.id ?? '')} for ${wanted.length} message(s)`)
      } catch (error) {
        ctx.logger?.error?.(`aw-wake: followup 失败 ${String(error)}`)
      }
    }
  }

  const timer = setInterval(tick, pollMs)
  timer.unref?.()
  ctx.effect(() => () => clearInterval(timer))
  ctx.logger?.info?.(`aw-wake: watching ${wakePath} for agent ${agentId}`)
  writeDebug()
}
