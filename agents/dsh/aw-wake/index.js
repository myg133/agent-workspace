import fs from 'node:fs'
import path from 'node:path'

export const name = 'aw-wake'
export const inject = ['agents']

const DEFAULT_TYPES = ['question', 'blocker', 'handoff', 'decision', 'contract-change']
const DEFAULT_EXPECT = ['reply', 'ack']
const SESSION_TTL_MS = 120 * 60 * 1000

/**
 * Watches the agent-workspace wake directory and wakes the matching DSH agent
 * with agent.followup().
 *
 * Two modes:
 *   single  cfg.agentId set -> watch <agentId>.json only; cwd fallback allowed
 *   multi   cfg.agentId unset/'*' -> watch every <agent>.json; each message goes
 *           ONLY to the session that .aw/sessions/<agent>.map.json points at.
 *           No cwd fallback once more than one agent may be in play, otherwise
 *           two sessions sharing a cwd would steal each other's wakes.
 *
 * Session resolution per recipient (never guesses, never broadcasts):
 *   1. .aw/sessions/<agent>.map.json, session_authoritative !== false,
 *      exactly one fresh session id inside the TTL
 *   2. legacy .aw/sessions/<agent>.json with session_authoritative === true
 *   3. explicit cfg.sessionId (pin)
 *   4. single mode: cwd match when exactly one live session matches
 *   5. multi mode + one-entry allowlist: cwd bootstrap (first run, before
 *      'aw.py agent whoami' has written a map)
 *   6. anything else -> refuse and log; never wake a session that belongs to
 *      another agent.
 */
export function apply(ctx, config) {
  const cfg = config ?? {}
  const repoRoot = String(cfg.repoRoot ?? '').trim()
  const rawAgentId = String(cfg.agentId ?? '').trim()
  const allow = new Set(
    (Array.isArray(cfg.agents) ? cfg.agents : []).map(v => String(v).trim()).filter(Boolean),
  )
  const singleAgent = Boolean(rawAgentId) && rawAgentId !== '*' && rawAgentId !== 'all'
  if (!repoRoot) {
    ctx.logger?.warn?.('aw-wake: repoRoot 未配置，插件不生效')
    return
  }

  const pollMs = Math.max(500, Number(cfg.pollMs ?? 2000))
  const minIntervalMs = Math.max(0, Number(cfg.minIntervalMs ?? 10000))
  const wakeAll = cfg.wakeAll !== false
  const wakeTypes = new Set((cfg.wakeTypes ?? DEFAULT_TYPES).map(String))
  const wakeExpect = new Set((cfg.wakeExpect ?? DEFAULT_EXPECT).map(String))
  const pinnedSession = String(cfg.sessionId ?? '').trim()
  const ttlMs = Math.max(1000, Number(cfg.sessionTtlMs ?? SESSION_TTL_MS))
  const multi = !singleAgent

  const wakeDir = cfg.wakeDir ? String(cfg.wakeDir) : path.join(repoRoot, '.aw', 'wake')
  const sessionsDir = path.join(repoRoot, '.aw', 'sessions')
  const readDir = path.join(repoRoot, '.aw', 'msg-read')
  const seenPath = path.join(repoRoot, '.aw', 'aw-wake-seen.json')
  const debugPath = path.join(repoRoot, '.aw', 'aw-wake-debug.json')

  const seen = new Set()
  const lastWakeAt = new Map()

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
      ctx.logger?.warn?.('aw-wake: 写 seen 失败 ' + String(error))
    }
  }

  const wakePathFor = agent => path.join(wakeDir, agent + '.json')
  const mapPathFor = agent => path.join(sessionsDir, agent + '.map.json')
  const legacyPathFor = agent => path.join(sessionsDir, agent + '.json')
  const readPathFor = agent => path.join(readDir, agent + '.json')

  function readWakeFile(agent) {
    const raw = readJson(wakePathFor(agent))
    return Array.isArray(raw?.messages) ? raw.messages : []
  }

  function listWakeFiles() {
    let names = []
    try {
      names = fs.readdirSync(wakeDir)
    } catch {
      return []
    }
    const out = []
    for (const fileName of names) {
      if (!fileName.endsWith('.json')) continue
      const agent = fileName.slice(0, -'.json'.length)
      if (singleAgent && agent !== rawAgentId) continue
      out.push([agent, readWakeFile(agent)])
    }
    return out
  }

  function readIds(agent) {
    const raw = readJson(readPathFor(agent))
    return new Set(Array.isArray(raw?.ids) ? raw.ids.map(String) : [])
  }

  function realId(value) {
    const id = String(value ?? '').trim()
    if (!id || id.startsWith('proc-')) return ''
    return id
  }

  // Distinct real session ids recorded inside the TTL window.
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

  // session_id -> [agent, ...] claimed by map files; used to refuse a session
  // that two agents both claim (the classic multi-instance collision).
  function claimsBySession() {
    const out = new Map()
    let names = []
    try {
      names = fs.readdirSync(sessionsDir)
    } catch {
      return out
    }
    for (const fileName of names) {
      if (!fileName.endsWith('.map.json')) continue
      const agent = fileName.slice(0, -'.map.json'.length)
      const record = readJson(path.join(sessionsDir, fileName))
      if (!record || record.session_authoritative === false) continue
      for (const id of freshSessions(record)) {
        const list = out.get(id) ?? []
        if (!list.includes(agent)) list.push(agent)
        out.set(id, list)
      }
    }
    return out
  }

  function mapDecision(agent) {
    const record = readJson(mapPathFor(agent))
    if (record) {
      if (record.session_authoritative === false) return { kind: 'refuse', reason: 'map-not-authoritative' }
      const fresh = freshSessions(record)
      if (fresh.size > 1) return { kind: 'refuse', reason: 'map-ambiguous:' + fresh.size }
      const id = realId(record.session_id)
      if (id) return { kind: 'session', id, reason: 'map' }
    }
    const legacy = readJson(legacyPathFor(agent))
    if (legacy && legacy.session_authoritative === true) {
      const id = realId(legacy.session_id)
      if (id) return { kind: 'session', id, reason: 'sessions-file' }
    }
    if (pinnedSession) return { kind: 'session', id: pinnedSession, reason: 'config' }
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

  function resolveTargets(agent, live) {
    const mapped = mapDecision(agent)
    if (mapped?.kind === 'refuse') return { targets: [], reason: mapped.reason }
    if (mapped?.kind === 'session') {
      const shared = claimsBySession().get(mapped.id) ?? []
      if (shared.length > 1) return { targets: [], reason: 'session-shared:' + shared.join(',') }
      const hit = live.find(item => String(item?.id ?? '') === mapped.id)
      if (hit) return { targets: [hit], reason: mapped.reason }
      return { targets: [], reason: mapped.reason + '-offline' }
    }
    const matched = live.filter(item => sameRoot(cwdOf(item)))
    if (!multi) {
      if (matched.length === 1) return { targets: matched, reason: 'cwd-unique' }
      if (matched.length > 1) return { targets: [], reason: 'ambiguous-cwd' }
      return { targets: [], reason: 'no-session' }
    }
    // multi mode: only bootstrap when the allowlist names exactly one agent,
    // so a message can never be delivered to a session owned by someone else.
    if (allow.size === 1 && allow.has(agent) && matched.length === 1) {
      return { targets: matched, reason: 'cwd-bootstrap' }
    }
    if (matched.length > 1) return { targets: [], reason: 'ambiguous-cwd' }
    return { targets: [], reason: 'no-map' }
  }

  function mapSnapshot(agent) {
    const record = readJson(mapPathFor(agent))
    if (!record) return null
    return {
      session_id: realId(record.session_id),
      session_authoritative: record.session_authoritative !== false,
      fresh_sessions: [...freshSessions(record)],
    }
  }

  function writeDebug(extra) {
    try {
      const live = liveAgents().map(agent => ({
        id: String(agent?.id ?? ''),
        cwd: cwdOf(agent),
        status: agent?.status ?? '',
        matched: sameRoot(cwdOf(agent)),
      }))
      let map = null
      if (singleAgent) {
        map = mapSnapshot(rawAgentId)
      } else {
        map = {}
        let names = []
        try {
          names = fs.readdirSync(sessionsDir)
        } catch {}
        for (const fileName of names) {
          if (!fileName.endsWith('.map.json')) continue
          map[fileName.slice(0, -'.map.json'.length)] = mapSnapshot(fileName.slice(0, -'.map.json'.length))
        }
      }
      fs.writeFileSync(
        debugPath,
        JSON.stringify(
          {
            at: new Date().toISOString(),
            config: {
              repoRoot,
              mode: multi ? 'multi' : 'single',
              agentId: singleAgent ? rawAgentId : '',
              agents: [...allow],
              wakeAll,
              sessionId: pinnedSession,
              pollMs,
              minIntervalMs,
              ttlMinutes: ttlMs / 60000,
            },
            map,
            agents: live,
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

  // Seed from the current files: a plugin restart must not replay old messages.
  const initial = readJson(seenPath)
  if (Array.isArray(initial?.ids)) for (const id of initial.ids) seen.add(String(id))
  for (const [, messages] of listWakeFiles()) {
    for (const message of messages) if (message?.id) seen.add(String(message.id))
  }

  function tick() {
    const files = listWakeFiles()
    const fresh = []
    for (const [fileAgent, messages] of files) {
      for (const message of messages) {
        const id = String(message?.id ?? '')
        if (!id || seen.has(id)) continue
        seen.add(id)
        const recipient = String(message?.agent ?? '').trim() || fileAgent
        if (multi && allow.size > 0 && !allow.has(recipient)) continue
        fresh.push({ recipient, message })
      }
    }
    if (fresh.length === 0) return
    saveSeen()

    const readCache = new Map()
    const isRead = agent => {
      if (!readCache.has(agent)) readCache.set(agent, readIds(agent))
      return readCache.get(agent)
    }
    const pending = fresh.filter(item => !isRead(item.recipient).has(String(item.message?.id ?? '')))
    const wanted = wakeAll
      ? pending
      : pending.filter(
          item =>
            wakeTypes.has(String(item.message?.type ?? '')) ||
            wakeExpect.has(String(item.message?.expect ?? '')),
        )
    if (wanted.length === 0) return

    const byAgent = new Map()
    for (const item of wanted) {
      const list = byAgent.get(item.recipient) ?? []
      list.push(item.message)
      byAgent.set(item.recipient, list)
    }

    const live = liveAgents()
    const routes = []
    for (const [agent, messages] of byAgent) {
      const { targets, reason } = resolveTargets(agent, live)
      routes.push({
        agent,
        ids: messages.map(message => String(message?.id ?? '')),
        resolve: reason,
        sessions: targets.map(target => String(target?.id ?? '')),
      })
      if (targets.length === 0) {
        ctx.logger?.warn?.('aw-wake: 跳过 ' + agent + ' 的 ' + messages.length + ' 条消息（' + reason + '）')
        continue
      }
      const lines = messages
        .slice(0, 5)
        .map(message => {
          const expect = message?.expect ? '/' + message.expect : ''
          const subject = message?.subject ? ' ' + message.subject : ''
          return '- ' + String(message?.id ?? '') + ' ' + (message?.from ?? '') + ' ' + (message?.type ?? '') + expect + subject
        })
        .join('\n')
      const text =
        '[bus] 收到 ' + messages.length + ' 条消息（' + agent + '）：\n' + lines + '\n\n请用 msg_inbox 拉取；纯 fyi 可只确认、不展开。'
      for (const target of targets) {
        const key = String(target?.id ?? '')
        if (Date.now() - (lastWakeAt.get(key) ?? 0) < minIntervalMs) continue
        try {
          target.followup({ content: [{ type: 'text', text }], source: { kind: 'user' } })
          lastWakeAt.set(key, Date.now())
          ctx.logger?.info?.(
            'aw-wake: woke ' + key + ' for ' + messages.length + ' message(s) of ' + agent + ' [' + reason + ']',
          )
        } catch (error) {
          ctx.logger?.error?.('aw-wake: followup 失败 ' + String(error))
        }
      }
    }
    writeDebug({ routes })
  }

  const timer = setInterval(tick, pollMs)
  timer.unref?.()
  ctx.effect(() => () => clearInterval(timer))
  ctx.logger?.info?.(
    'aw-wake: watching ' + (multi ? wakeDir : wakePathFor(rawAgentId)) + ' (' + (multi ? 'multi' : 'single') + ', wakeAll=' + wakeAll + ')',
  )
  writeDebug({ resolve: 'startup' })
}
