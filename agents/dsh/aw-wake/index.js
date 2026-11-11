import fs from 'node:fs'
import path from 'node:path'

export const name = 'aw-wake'
export const inject = ['agents']

const DEFAULT_TYPES = ['question', 'blocker', 'handoff', 'decision', 'contract-change']
const DEFAULT_EXPECT = ['reply', 'ack']
const SESSION_TTL_MS = 120 * 60 * 1000
const MAX_PARENT_LOOKUP = 6

/**
 * Wakes DSH sessions when an agent-workspace bus has messages for them.
 *
 * Repositories are discovered from the live sessions: take each session cwd,
 * walk up at most MAX_PARENT_LOOKUP levels and use the nearest directory that
 * contains .aw/ (so sessions opened in <repo>/code/ work too). One DSH host can
 * therefore serve several workspaces at once; nothing is pinned to one repo.
 * cfg.repoRoot / cfg.repoRoots optionally restrict the set.
 *
 * Two routing modes:
 *   single  cfg.agentId set -> only <agentId>.json; cwd fallback allowed
 *   multi   cfg.agentId unset -> every <agent>.json, routed per (repo, agent)
 *           through <repo>/.aw/sessions/<agent>.map.json; never guess by cwd
 *           unless the allowlist names exactly one agent (bootstrap).
 *
 * Session resolution per (repo, agent):
 *   1. <repo>/.aw/sessions/<agent>.map.json, session_authoritative !== false,
 *      exactly one fresh session id inside the TTL
 *   2. <repo>/.aw/sessions/<agent>.json with session_authoritative === true
 *   3. cfg.sessionId (pin)
 *   4. single mode: cwd match when exactly one live session is in that repo
 *   5. multi mode + one-entry allowlist: same, as a bootstrap
 *   6. anything else -> refuse and log; never wake another agent's session.
 */
export function apply(ctx, config) {
  const cfg = config ?? {}
  const rawAgentId = String(cfg.agentId ?? '').trim()
  const allow = new Set(
    (Array.isArray(cfg.agents) ? cfg.agents : []).map(v => String(v).trim()).filter(Boolean),
  )
  const singleAgent = Boolean(rawAgentId) && rawAgentId !== '*' && rawAgentId !== 'all'
  const multi = !singleAgent

  const pinRoots = []
  if (String(cfg.repoRoot ?? '').trim()) pinRoots.push(path.resolve(String(cfg.repoRoot).trim()))
  if (Array.isArray(cfg.repoRoots)) {
    for (const value of cfg.repoRoots) {
      const text = String(value ?? '').trim()
      if (text) pinRoots.push(path.resolve(text))
    }
  }

  const pollMs = Math.max(500, Number(cfg.pollMs ?? 2000))
  const minIntervalMs = Math.max(0, Number(cfg.minIntervalMs ?? 10000))
  const wakeAll = cfg.wakeAll !== false
  const wakeTypes = new Set((cfg.wakeTypes ?? DEFAULT_TYPES).map(String))
  const wakeExpect = new Set((cfg.wakeExpect ?? DEFAULT_EXPECT).map(String))
  const pinnedSession = String(cfg.sessionId ?? '').trim()
  const ttlMs = Math.max(1000, Number(cfg.sessionTtlMs ?? SESSION_TTL_MS))
  const STALE_MAP_MINUTES = 24 * 60

  const repos = new Map() // root -> { seen: Set<string> }
  const lastWakeAt = new Map() // session id -> ts

  const readJson = file => {
    try {
      return JSON.parse(fs.readFileSync(file, 'utf8'))
    } catch {
      return undefined
    }
  }

  const samePath = (a, b) => {
    try {
      return path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase()
    } catch {
      return false
    }
  }

  function repoRootOf(cwd) {
    if (!cwd) return ''
    let dir
    try {
      dir = path.resolve(cwd)
    } catch {
      return ''
    }
    for (let depth = 0; depth < MAX_PARENT_LOOKUP; depth += 1) {
      try {
        if (fs.statSync(path.join(dir, '.aw')).isDirectory()) return dir
      } catch {}
      const parent = path.dirname(dir)
      if (parent === dir) break
      dir = parent
    }
    return ''
  }

  function repoFor(cwd) {
    const root = repoRootOf(cwd)
    if (!root) return ''
    if (pinRoots.length && !pinRoots.some(pin => samePath(pin, root))) return ''
    return root
  }

  const at = (root, ...parts) => path.join(root, '.aw', ...parts)
  const wakeDirOf = root => at(root, 'wake')
  const sessionsDirOf = root => at(root, 'sessions')
  const readDirOf = root => at(root, 'msg-read')
  const seenPathOf = root => at(root, 'aw-wake-seen.json')
  const debugPathOf = root => at(root, 'aw-wake-debug.json')

  function repoState(root) {
    let state = repos.get(root)
    if (state) return state
    state = { seen: new Set() }
    const initial = readJson(seenPathOf(root))
    if (Array.isArray(initial?.ids)) for (const id of initial.ids) state.seen.add(String(id))
    for (const [, messages] of listWakeFiles(root)) {
      for (const message of messages) if (message?.id) state.seen.add(String(message.id))
    }
    repos.set(root, state)
    return state
  }

  function saveSeen(root) {
    const state = repos.get(root)
    if (!state) return
    try {
      fs.writeFileSync(seenPathOf(root), JSON.stringify({ ids: [...state.seen].slice(-2000) }, null, 2))
    } catch (error) {
      ctx.logger?.warn?.('aw-wake: 写 seen 失败 ' + root + ' ' + String(error))
    }
  }

  function listWakeFiles(root) {
    const dir = wakeDirOf(root)
    let names = []
    try {
      names = fs.readdirSync(dir)
    } catch {
      return []
    }
    const out = []
    for (const fileName of names) {
      if (!fileName.endsWith('.json')) continue
      const agent = fileName.slice(0, -'.json'.length)
      if (singleAgent && agent !== rawAgentId) continue
      const raw = readJson(path.join(dir, fileName))
      out.push([agent, Array.isArray(raw?.messages) ? raw.messages : []])
    }
    return out
  }

  function readIds(root, agent) {
    const raw = readJson(path.join(readDirOf(root), agent + '.json'))
    return new Set(Array.isArray(raw?.ids) ? raw.ids.map(String) : [])
  }

  function realId(value) {
    const id = String(value ?? '').trim()
    if (!id || id.startsWith('proc-')) return ''
    return id
  }

  function freshSessions(record) {
    const list = Array.isArray(record?.sessions) ? record.sessions : []
    const now = Date.now()
    const ids = new Set()
    for (const entry of list) {
      const id = realId(entry?.session_id)
      if (!id) continue
      const stamp = Date.parse(String(entry?.at ?? ''))
      if (Number.isFinite(stamp) && now - stamp > ttlMs) continue
      ids.add(id)
    }
    const main = realId(record?.session_id)
    if (main) ids.add(main)
    return ids
  }

  function claimsBySession(root) {
    const out = new Map()
    let names = []
    try {
      names = fs.readdirSync(sessionsDirOf(root))
    } catch {
      return out
    }
    for (const fileName of names) {
      if (!fileName.endsWith('.map.json')) continue
      const agent = fileName.slice(0, -'.map.json'.length)
      const record = readJson(path.join(sessionsDirOf(root), fileName))
      if (!record || record.session_authoritative === false) continue
      for (const id of freshSessions(record)) {
        const list = out.get(id) ?? []
        if (!list.includes(agent)) list.push(agent)
        out.set(id, list)
      }
    }
    return out
  }

  // 手写的 map 也要过形状检查：缺字段/版本不对/agent 不符一律按 no-map 处理，
  // 不能因为「文件存在」就相信它（手写 map 没有节流，也没有后续刷新）。
  function mapProblem(record, agent) {
    if (!record || typeof record !== 'object') return 'map-invalid'
    if (Number(record.map_version) !== 2) return 'map-version'
    if (record.session_authoritative !== true) return 'map-not-authoritative'
    const recorded = String(record.agent_id ?? '').trim()
    if (recorded && recorded !== agent) return 'map-agent-mismatch'
    if (!realId(record.session_id)) return 'map-no-session'
    if (!String(record.host ?? '').trim()) return 'map-no-host'
    return ''
  }

  function mapDecision(root, agent) {
    const record = readJson(path.join(sessionsDirOf(root), agent + '.map.json'))
    if (record) {
      const problem = mapProblem(record, agent)
      if (problem) return { kind: 'refuse', reason: problem }
      const fresh = freshSessions(record)
      if (fresh.size > 1) return { kind: 'refuse', reason: 'map-ambiguous:' + fresh.size }
      const id = realId(record.session_id)
      if (id) return { kind: 'session', id, reason: 'map' }
    }
    const legacy = readJson(path.join(sessionsDirOf(root), agent + '.json'))
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

  function liveAgents() {
    try {
      return ctx.agents.list() ?? []
    } catch {
      return []
    }
  }

  function resolveTargets(root, agent, members) {
    const mapped = mapDecision(root, agent)
    if (mapped?.kind === 'refuse') return { targets: [], reason: mapped.reason }
    if (mapped?.kind === 'session') {
      const shared = claimsBySession(root).get(mapped.id) ?? []
      if (shared.length > 1) return { targets: [], reason: 'session-shared:' + shared.join(',') }
      const hit = members.find(item => String(item?.id ?? '') === mapped.id)
      if (hit) return { targets: [hit], reason: mapped.reason }
      return { targets: [], reason: mapped.reason + '-offline' }
    }
    const bootstrap = singleAgent || (allow.size === 1 && allow.has(agent))
    if (bootstrap && members.length === 1) {
      return { targets: members, reason: singleAgent ? 'cwd-unique' : 'cwd-bootstrap' }
    }
    if (members.length > 1) return { targets: [], reason: 'ambiguous-cwd' }
    return { targets: [], reason: 'no-map' }
  }

  function writeDebug(root, extra) {
    try {
      const maps = {}
      let names = []
      try {
        names = fs.readdirSync(sessionsDirOf(root))
      } catch {}
      for (const fileName of names) {
        if (!fileName.endsWith('.map.json')) continue
        const agent = fileName.slice(0, -'.map.json'.length)
        const record = readJson(path.join(sessionsDirOf(root), fileName))
        const updated = Date.parse(String(record?.updated_at ?? ''))
        maps[agent] = record
          ? {
              session_id: realId(record.session_id),
              session_authoritative: record.session_authoritative === true,
              fresh_sessions: [...freshSessions(record)],
              age_minutes: Number.isFinite(updated) ? Math.round((Date.now() - updated) / 60000) : null,
              // 只提示不拒绝：硬 TTL 会误伤长期没跑 agent/claim 的安静会话。
              stale_hours:
                Number.isFinite(updated) && Date.now() - updated > STALE_MAP_MINUTES * 60000
                  ? Math.round((Date.now() - updated) / 3600000)
                  : null,
            }
          : null
      }
      fs.writeFileSync(
        debugPathOf(root),
        JSON.stringify(
          {
            at: new Date().toISOString(),
            repo: root,
            config: {
              mode: multi ? 'multi' : 'single',
              agentId: singleAgent ? rawAgentId : '',
              agents: [...allow],
              repoRoots: pinRoots,
              wakeAll,
              sessionId: pinnedSession,
              pollMs,
              minIntervalMs,
              ttlMinutes: ttlMs / 60000,
            },
            map: maps,
            agents: liveAgents()
              .filter(item => repoFor(cwdOf(item)) === root)
              .map(item => ({
                id: String(item?.id ?? ''),
                cwd: cwdOf(item),
                status: item?.status ?? '',
              })),
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

  let lastRepos = []

  function tick() {
    const live = liveAgents()
    const members = new Map()
    for (const item of live) {
      const root = repoFor(cwdOf(item))
      if (!root) continue
      const list = members.get(root) ?? []
      list.push(item)
      members.set(root, list)
    }
    const roots = new Set([...members.keys(), ...pinRoots])
    if (roots.size === 0) return

    const fresh = []
    for (const root of roots) {
      const state = repoState(root)
      for (const [fileAgent, messages] of listWakeFiles(root)) {
        for (const message of messages) {
          const id = String(message?.id ?? '')
          if (!id || state.seen.has(id)) continue
          state.seen.add(id)
          const recipient = String(message?.agent ?? '').trim() || fileAgent
          if (singleAgent && recipient !== rawAgentId) continue
          if (multi && allow.size > 0 && !allow.has(recipient)) continue
          fresh.push({ root, recipient, message })
        }
      }
    }
    if (fresh.length === 0) return
    for (const root of roots) saveSeen(root)

    const readCache = new Map()
    const isRead = (root, agent) => {
      const key = root + '|' + agent
      if (!readCache.has(key)) readCache.set(key, readIds(root, agent))
      return readCache.get(key)
    }
    const pending = fresh.filter(item => !isRead(item.root, item.recipient).has(String(item.message?.id ?? '')))
    const wanted = wakeAll
      ? pending
      : pending.filter(
          item =>
            wakeTypes.has(String(item.message?.type ?? '')) ||
            wakeExpect.has(String(item.message?.expect ?? '')),
        )
    if (wanted.length === 0) return

    const groups = new Map()
    for (const item of wanted) {
      const key = item.root + '|' + item.recipient
      const group = groups.get(key) ?? { root: item.root, agent: item.recipient, messages: [] }
      group.messages.push(item.message)
      groups.set(key, group)
    }

    const routesByRepo = new Map()
    for (const group of groups.values()) {
      const groupMembers = members.get(group.root) ?? []
      const { targets, reason } = resolveTargets(group.root, group.agent, groupMembers)
      const route = {
        repo: group.root,
        agent: group.agent,
        ids: group.messages.map(message => String(message?.id ?? '')),
        resolve: reason,
        sessions: targets.map(target => String(target?.id ?? '')),
      }
      const routeList = routesByRepo.get(group.root) ?? []
      routeList.push(route)
      routesByRepo.set(group.root, routeList)
      if (reason === 'map' || reason === 'sessions-file') {
        const record = readJson(path.join(sessionsDirOf(group.root), group.agent + '.map.json'))
        const updated = Date.parse(String(record?.updated_at ?? ''))
        if (Number.isFinite(updated) && Date.now() - updated > STALE_MAP_MINUTES * 60000) {
          const hours = Math.round((Date.now() - updated) / 3600000)
          route.stale_hours = hours
          ctx.logger?.warn?.(
            'aw-wake: ' + group.agent + ' 的会话映射已 ' + hours + ' 小时未刷新（可能陈旧，仍未拒绝）',
          )
        }
      }
      if (targets.length === 0) {
        ctx.logger?.warn?.(
          'aw-wake: 跳过 ' + group.agent + ' 的 ' + group.messages.length + ' 条消息（' + group.root + ', ' + reason + '）' +
            (reason === 'no-map' || String(reason).startsWith('ambiguous-cwd')
              ? '：缺少 .aw/sessions/' + group.agent + '.map.json，需在该 agent 的会话里跑一次 aw.py agent whoami'
              : ''),
        )
        continue
      }
      const lines = group.messages
        .slice(0, 5)
        .map(message => {
          const expect = message?.expect ? '/' + message.expect : ''
          const subject = message?.subject ? ' ' + message.subject : ''
          return '- ' + String(message?.id ?? '') + ' ' + (message?.from ?? '') + ' ' + (message?.type ?? '') + expect + subject
        })
        .join('\n')
      const text =
        '[bus] 收到 ' + group.messages.length + ' 条消息（' + group.agent + '）：\n' +
        lines +
        '\n\n请用 msg_inbox 拉取；纯 fyi 可只确认、不展开。'
      for (const target of targets) {
        const key = String(target?.id ?? '')
        if (Date.now() - (lastWakeAt.get(key) ?? 0) < minIntervalMs) continue
        try {
          target.followup({ content: [{ type: 'text', text }], source: { kind: 'user' } })
          lastWakeAt.set(key, Date.now())
          ctx.logger?.info?.(
            'aw-wake: woke ' + key + ' for ' + group.messages.length + ' 条 ' + group.agent + ' [' + reason + ']',
          )
        } catch (error) {
          ctx.logger?.error?.('aw-wake: followup 失败 ' + String(error))
        }
      }
    }
    for (const [root, list] of routesByRepo) writeDebug(root, { routes: list })
    lastRepos = [...roots]
  }

  // Prime known repos at load: messages already on disk count as history, so a
  // plugin reload never replays them (same semantics as the old startup seed).
  for (const item of liveAgents()) {
    const root = repoFor(cwdOf(item))
    if (root) repoState(root)
  }
  for (const root of repos.keys()) writeDebug(root, { resolve: 'startup' })

  const timer = setInterval(tick, pollMs)
  timer.unref?.()
  ctx.effect(() => () => clearInterval(timer))
  ctx.logger?.info?.(
    'aw-wake: watching ' +
      (pinRoots.length ? pinRoots.join(', ') : 'auto-discovered workspaces') +
      ' (' + (multi ? 'multi' : 'single') + ', wakeAll=' + wakeAll + ')',
  )
}
