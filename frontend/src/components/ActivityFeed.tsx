import { useQuery } from '@tanstack/react-query'
import { Star, GitFork, AlertCircle, GitPullRequest, Clock } from 'lucide-react'

interface WebhookEvent {
  id: number
  delivery_id: string
  event_type: string
  action: string
  repo_name: string
  sender: string
  received_at: string
}

const eventConfig: Record<string, { icon: typeof Star; color: string; label: string }> = {
  star: { icon: Star, color: '#eab308', label: 'Star' },
  fork: { icon: GitFork, color: '#8b5cf6', label: 'Fork' },
  issues: { icon: AlertCircle, color: '#f97316', label: 'Issue' },
  pull_request: { icon: GitPullRequest, color: '#22d3ee', label: 'PR' },
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function ActivityFeed() {
  const { data: events = [], isLoading } = useQuery<WebhookEvent[]>({
    queryKey: ['webhook-events'],
    queryFn: () => fetch('/api/webhooks/events').then(r => r.json()),
    refetchInterval: 30000,
  })

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Clock size={16} color="var(--text-muted)" />
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          Activity Feed
        </h3>
        <span style={{
          fontSize: 10, color: 'var(--text-muted)',
          background: 'rgba(255,255,255,0.05)', borderRadius: 10, padding: '2px 8px',
        }}>
          {events.length} events
        </span>
      </div>

      {isLoading && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>
          Loading events...
        </div>
      )}

      {!isLoading && events.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>
          No webhook events yet. Configure a GitHub webhook pointing to /api/webhooks/github
        </div>
      )}

      <div style={{ maxHeight: 400, overflowY: 'auto' }}>
        {events.slice(0, 50).map((evt) => {
          const cfg = eventConfig[evt.event_type] || { icon: AlertCircle, color: '#64748b', label: evt.event_type }
          const Icon = cfg.icon
          return (
            <div key={evt.id} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 0',
              borderBottom: '1px solid rgba(255,255,255,0.04)',
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: 8,
                background: `${cfg.color}15`,
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
              }}>
                <Icon size={14} color={cfg.color} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>
                  <a href={`https://github.com/${evt.sender}`} target="_blank" rel="noopener noreferrer"
                    style={{ color: '#22d3ee', textDecoration: 'none', fontWeight: 500 }}>
                    {evt.sender}
                  </a>
                  {' '}{evt.action || cfg.label.toLowerCase()}{evt.action ? 'd' : ''}{' '}
                  <span style={{ color: 'var(--text-muted)' }}>{evt.repo_name}</span>
                </div>
              </div>
              <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>
                {evt.received_at ? timeAgo(evt.received_at) : ''}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
