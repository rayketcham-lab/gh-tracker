import { useQuery } from '@tanstack/react-query'
import { Play, CheckCircle2, XCircle, Clock, Loader2, Ban } from 'lucide-react'

interface WorkflowRun {
  repo_name: string
  run_id: number
  workflow_name: string
  status: string
  conclusion: string
  event: string
  branch: string
  created_at: string
  duration_seconds: number
}

const statusConfig: Record<string, { icon: typeof CheckCircle2; color: string }> = {
  success: { icon: CheckCircle2, color: '#10b981' },
  failure: { icon: XCircle, color: '#ef4444' },
  in_progress: { icon: Loader2, color: '#eab308' },
  cancelled: { icon: Ban, color: '#6b7280' },
  queued: { icon: Clock, color: '#64748b' },
}

function formatDuration(secs: number): string {
  if (!secs) return '-'
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60), s = secs % 60
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const hrs = Math.floor(diff / 3600000)
  if (hrs < 1) return `${Math.floor(diff / 60000)}m ago`
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function WorkflowRuns({ owner, repo }: { owner: string; repo: string }) {
  const { data: runs = [], isLoading } = useQuery<WorkflowRun[]>({
    queryKey: ['workflow-runs', owner, repo],
    queryFn: () => fetch(`/api/repos/${owner}/${repo}/workflow-runs`).then(r => r.json()),
    enabled: !!owner,
  })

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Play size={16} color="var(--text-muted)" />
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          CI / Actions
        </h3>
        <span style={{
          fontSize: 10, color: 'var(--text-muted)',
          background: 'rgba(255,255,255,0.05)', borderRadius: 10, padding: '2px 8px',
        }}>
          {runs.length} runs
        </span>
      </div>

      {isLoading && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>Loading...</div>
      )}

      {!isLoading && runs.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>
          No workflow runs collected
        </div>
      )}

      <div style={{ maxHeight: 350, overflowY: 'auto' }}>
        {runs.slice(0, 30).map((run) => {
          const cfg = statusConfig[run.conclusion || run.status] || statusConfig.queued
          const Icon = cfg.icon
          return (
            <div key={run.run_id} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.04)',
            }}>
              <Icon size={14} color={cfg.color} style={run.status === 'in_progress' ? { animation: 'spin 1s linear infinite' } : {}} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 }}>
                  {run.workflow_name}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                  {run.branch} · {run.event} · {formatDuration(run.duration_seconds)}
                </div>
              </div>
              <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>
                {timeAgo(run.created_at)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
