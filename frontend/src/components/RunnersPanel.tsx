import { useEffect, useState } from 'react'
import { Server, AlertTriangle, CheckCircle2, XCircle, Clock } from 'lucide-react'

interface ProcInfo {
  pid: number
  ageSec: number
  cpu: number
  rssKb: number
}

interface StuckInfo {
  flagged: boolean
  reasons: string[]
  status: string
}

interface RunnerState {
  name: string
  kind: string
  host: string
  runner_dir?: string
  service?: string | null
  updated_at?: string
  reachable: boolean
  error?: string | null
  svc_state?: string
  listener?: ProcInfo | null
  worker?: ProcInfo | null
  latest_worker_log?: string | null
  last_line?: string
  last_line_age_sec?: number
  current_step?: string | null
  log_tail?: string
  stuck: StuckInfo
}

interface StatePayload {
  runners: RunnerState[]
  rules?: { workerAgeMinutes: number; logSilenceSeconds: number; lowCpuPercent: number }
  pollIntervalMs?: number
}

function fmtAge(sec?: number): string {
  if (sec === undefined || sec === null || sec < 0) return '—'
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function fmtRss(kb?: number): string {
  if (!kb) return '—'
  if (kb < 1024) return `${kb} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

function statusColor(r: RunnerState): string {
  if (!r.reachable) return '#ef4444'
  if (r.stuck.flagged) return '#f59e0b'
  if (r.stuck.status === 'busy') return '#10b981'
  if (r.stuck.status === 'idle') return '#22d3ee'
  if (r.stuck.status === 'offline') return '#64748b'
  return '#64748b'
}

function StatusPill({ r }: { r: RunnerState }) {
  const color = statusColor(r)
  const label = !r.reachable ? 'unreachable' : r.stuck.flagged ? 'STUCK' : r.stuck.status
  const Icon = !r.reachable
    ? XCircle
    : r.stuck.flagged
    ? AlertTriangle
    : r.stuck.status === 'busy'
    ? Clock
    : CheckCircle2
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 10px', borderRadius: 999,
      background: `${color}22`, color, border: `1px solid ${color}55`,
      fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5,
    }}>
      <Icon size={12} /> {label}
    </span>
  )
}

function RunnerCard({ r }: { r: RunnerState }) {
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: `1px solid ${r.stuck.flagged ? 'rgba(245,158,11,0.5)' : 'var(--border-color)'}`,
      borderRadius: 12, padding: 18, marginBottom: 14,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Server size={16} color="#22d3ee" />
            <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{r.name}</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              {r.kind === 'ssh' ? `ssh · ${r.host}` : 'local'}
            </span>
          </div>
          {r.service && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, fontFamily: 'monospace' }}>
              {r.service} · svc={r.svc_state || 'unknown'}
            </div>
          )}
        </div>
        <StatusPill r={r} />
      </div>

      {r.error && (
        <div style={{
          padding: '8px 12px', background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8,
          color: '#fca5a5', fontSize: 12, fontFamily: 'monospace', marginBottom: 10,
        }}>{r.error}</div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 12 }}>
        <Metric label="listener" value={r.listener ? `pid ${r.listener.pid}` : '—'}
          sub={r.listener ? fmtAge(r.listener.ageSec) : undefined} />
        <Metric label="worker" value={r.worker ? `pid ${r.worker.pid}` : '—'}
          sub={r.worker ? `${fmtAge(r.worker.ageSec)} · ${r.worker.cpu}% cpu` : undefined} />
        <Metric label="rss" value={fmtRss(r.worker?.rssKb)} />
        <Metric label="log age" value={fmtAge(r.last_line_age_sec)} />
      </div>

      {r.current_step && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
            Current step
          </div>
          <div style={{ fontSize: 13, color: '#22d3ee', fontWeight: 500 }}>{r.current_step}</div>
        </div>
      )}

      {r.stuck.flagged && r.stuck.reasons.length > 0 && (
        <div style={{
          padding: '8px 12px', background: 'rgba(245,158,11,0.08)',
          border: '1px solid rgba(245,158,11,0.3)', borderRadius: 8, marginBottom: 10,
        }}>
          <div style={{ fontSize: 10, color: '#f59e0b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
            Stuck reasons
          </div>
          {r.stuck.reasons.map((reason, i) => (
            <div key={i} style={{ fontSize: 12, color: '#fbbf24' }}>· {reason}</div>
          ))}
        </div>
      )}

      {r.log_tail && (
        <details>
          <summary style={{ fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer', textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Worker log tail ({r.latest_worker_log?.split('/').pop()})
          </summary>
          <pre style={{
            marginTop: 8, padding: 10, background: '#0b1220',
            border: '1px solid var(--border-color)', borderRadius: 8,
            fontSize: 11, color: '#cbd5e1', maxHeight: 220, overflow: 'auto',
          }}>{r.log_tail}</pre>
        </details>
      )}
    </div>
  )
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500, fontFamily: 'monospace' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

export default function RunnersPanel() {
  const [state, setState] = useState<StatePayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const es = new EventSource('/api/runners/stream')
    es.onmessage = (ev) => {
      try {
        setState(JSON.parse(ev.data))
        setError(null)
      } catch (e) { setError(String(e)) }
    }
    es.onerror = () => {
      setError('stream disconnected, retrying...')
      // Browser auto-reconnects EventSource.
    }
    return () => es.close()
  }, [])

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>Self-hosted runners</h2>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '4px 0 0' }}>
            Live view of GitHub Actions runner state. {state?.rules && (
              <>stuck after worker age ≥ {state.rules.workerAgeMinutes}m or log silent ≥ {state.rules.logSilenceSeconds}s.</>
            )}
          </p>
        </div>
        {error && <span style={{ fontSize: 12, color: '#fca5a5' }}>{error}</span>}
      </div>
      {!state && <div style={{ color: 'var(--text-muted)', padding: 24 }}>Connecting...</div>}
      {state?.runners.map((r) => <RunnerCard key={r.name} r={r} />)}
      {state && state.runners.length === 0 && (
        <div style={{ color: 'var(--text-muted)', padding: 24 }}>No runners configured.</div>
      )}
    </div>
  )
}
