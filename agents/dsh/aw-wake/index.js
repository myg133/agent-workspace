import fs from 'node:fs'
import path from 'node:path'

export const name = 'aw-wake'
export const inject = ['agents']

const DEFAULT_TYPES = ['question', 'blocker', 'handoff', 'decision', 'contract-change']
const DEFAULT_EXPECT = ['reply', 'ack']
const SESSION_TTL_MS = 120 * 60 * 1000

/**
 * Watches the agent-workspace wake file of one agent and wakes the matching
 * DSH agent with agent.followup() when a message needs action.
 *
 * Session resolution (never guesses, never broadcasts):
 *   1. `.aw/sessions/<agentId>.map.json`  with session_authoritative === true
 *      and no conflicting session inside the TTL
 *   2. legacy `.aw/sessions/<agentId>.json` when session_authoritative === true
 *   3. explicit `sessionId` from the plugin config
 *   4. cwd match, only when exactly one live session matches
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
  const wakeAll = cfg.wakeAll !== false
  const wakeTypes = new Set((cfg.wakeTypes ?? DEFAULT_TYPES).map(String))
  const wakeExpect = new Set((cfg.wakeExpect ?? DEFAULT_EXPECT).map(String))
  const sessionId = String(cfg.sessionId ?? '').trim()
  const ttlMs = Math.max(1000, Number(cfg.sessionTtlMs ?? SESSION_TTL_MS))

  const wakeDir = cfg.wakeDir ? String(cfg.wakeDir) : path.join(repoRoot, '.aw', 'wake')
  const wakePath = path.join(wakeDir, `${agentId}.json`)
  const readPath = path.join(repoRoot, '.aw', 'msg-read', `${agentId}.json`)
  const mapPath = path.join(repoRoot, '.aw', 'sessions', `${agentId}.map.json`)
  const legacyPath = path.join(repoRoot, '.aw', 'sessions', `${agentId}.json`)
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

  function readIds() {
    const raw = readJson(readPath)
    return new Set(Array.isArray(raw?.ids) ? raw.ids.map(String) : [])
  }

  function realId(value) {
    const id = String(value ?? '').trim()
    if (!id || id.startsWith('proc-')) return ''
    return id
  }

  // Distinct session ids recorded inside the TTL window.
  function freshSessions(record) {
    const list = Array.isArray(record?.sessions) ? record.sessions : []
    const now = Date.now()
    const ids = new Set()
    for (const entry of list) {
      const id = realId(entry?.session_id)
      if (!id) continue
      const at = Date.parse(String(entry?.at ?? ''))
      if (Number.isFinite(at) && now - at > ttlMs) continue
      ids.add(id)
    }
    const main = realId(record?.session_id)
    if (main) ids.add(main)
    return ids
  }

  function mapDecision() {
    const record = readJson(mapPath)
    if (record) {
      const id = realId(record.session_id)
      if (record.session_authoritative === false) return { kind: 'refuse', reason: 'map-not-authoritative' }
      const fresh = freshSessions(record)
      if (fresh.size > 1) return { kind: 'refuse', reason: `map-ambiguous:${fresh.size}` }
      if (id) return { kind: 'session', id, reason: 'map' }
    }
    const legacy = readJson(legacyPath)
    if (legacy && legacy.session_authoritative === true) {
      const id = realId(legacy.session_id)
      if (id) return { kind: 'session', id, reason: 'sessions-file' }
    }
    return undefined
  }

  function cwdOf(agent) {
    const session = agent?.session
    const candidates = [session?.meta?.cwd, session?.header?.cwd, session?.cwd, agent?.options?.cwd]
    for (const value of candidates) {
      if (typeof value === 'string' && value.trim() !== '') return value
    }
    return ''
  }

  function sameRoot(cwd) {
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

  function resolveTargets() {
    const list = liveAgents()
    const mapped = mapDecision()
    if (mapped?.kind === 'refuse') {
      ctx.logger?.warn?.(`aw-wake: 会话映射不可用（${mapped.reason}），放弃唤醒`)
      return { targets: [], reason: mapped.reason }
    }
    if (mapped?.kind === 'session') {
      const hit = list.find(agent => String(agent?.id ?? '') === mapped.id)
      if (hit) return { targets: [hit], reason: mapped.reason }
      ctx.logger?.info?.(`aw-wake: 映射会话 ${mapped.id} 不在线，放弃唤醒`)
      return { targets: [], reason: `${mapped.reason}-offline` }
    }
    if (sessionId) {
      const hit = list.find(agent => String(agent?.id ?? '') === sessionId)
      if (hit) return { targets: [hit], reason: 'config' }
      ctx.logger?.info?.(`aw-wake: 配置 sessionId ${sessionId} 不在线，放弃唤醒`)
      return { targets: [], reason: 'config-offline' }
    }
    const matched = list.filter(agent => sameRoot(cwdOf(agent)))
    if (matched.length === 1) return { targets: matched, reason: 'cwd-unique' }
    if (matched.length > 1) {
      ctx.logger?.warn?.(
        `aw-wake: ${matched.length} 个会话的 cwd 都匹配 ${repoRoot}，无法确定目标，放弃唤醒（请写 map 文件或配置 sessionId）`,
      )
      return { targets: [], reason: 'ambiguous-cwd' }
    }
    return { targets: [], reason: 'no-session' }
  }

  function writeDebug(extra) {
    try {
      const agents = liveAgents().map(agent => ({
        id: String(agent?.id ?? ''),
        cwd: cwdOf(agent),
        status: agent?.status ?? '',
        matched: sameRoot(cwdOf(agent)),
      }))
      const record = readJson(mapPath)
      fs.writeFileSync(
        debugPath,
        JSON.stringify(
          {
            at: new Date().toISOString(),
            config: { repoRoot, agentId, wakeAll, sessionId, pollMs, minIntervalMs, ttlMinutes: ttlMs / 60000 },
            map: record
              ? {
                  session_id: realId(record.session_id),
                  session_authoritative: record.session_authoritative !== false,
                  fresh_sessions: [...freshSessions(record)],
                }
              : null,
            agents,
            ...extra,
          },
          null,
          2,
        ),
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

    const unread = readIds()
    const candidates = fresh.filter(message => !unread.has(String(message?.id ?? '')))
    const wanted = wakeAll
      ? candidates
      : candidates.filter(
          message =>
            wakeTypes.has(String(message?.type ?? '')) || wakeExpect.has(String(message?.expect ?? '')),
        )
    if (wanted.length === 0) return

    const { targets, reason } = resolveTargets()
    writeDebug({ pending: wanted.map(message => String(message.id)), resolve: reason, woke: targets.length })
    if (targets.length === 0) return
    if (Date.now() - lastWakeAt < minIntervalMs) return

    const lines = wanted
      .slice(0, 5)
      .map(message => {
        const expect = message?.expect ? `/${message.expect}` : ''
        const subject = message?.subject ? ` ${message.subject}` : ''
        return `- ${message.id} ${message.from ?? ''} ${message.type ?? ''}${expect}${subject}`
      })
      .join('\n')
    const text = `[bus] 收到 ${wanted.length} 条消息（${agentId}）：\n${lines}\n\n请用 msg_inbox 拉取；纯 fyi 可只确认、不展开。`

    for (const agent of targets) {
      try {
        agent.followup({ content: [{ type: 'text', text }], source: { kind: 'user' } })
        lastWakeAt = Date.now()
        ctx.logger?.info?.(`aw-wake: woke ${String(agent?.id ?? '')} for ${wanted.length} message(s) [${reason}]`)
      } catch (error) {
        ctx.logger?.error?.(`aw-wake: followup 失败 ${String(error)}`)
      }
    }
  }

  const timer = setInterval(tick, pollMs)
  timer.unref?.()
  ctx.effect(() => () => clearInterval(timer))
  ctx.logger?.info?.(`aw-wake: watching ${wakePath} for agent ${agentId} (wakeAll=${wakeAll})`)
  writeDebug({ resolve: 'startup' })
}
