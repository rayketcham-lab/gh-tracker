import { useQuery } from '@tanstack/react-query'
import { ShieldAlert, AlertTriangle, Info } from 'lucide-react'

interface Alert {
  id: number; repo_name: string; alert_type: string; severity: string
  state: string; package_name: string; description: string; url: string; created_at: string
}

interface Summary { repo_name: string; critical: number; high: number; medium: number; low: number; total: number }

const sevColor: Record<string, string> = {
  critical: '#dc2626', high: '#ef4444', medium: '#eab308', low: '#6b7280',
}

export default function SecurityAlerts({ owner, repo }: { owner: string; repo: string }) {
  const { data: alerts = [], isLoading } = useQuery<Alert[]>({
    queryKey: ['security-alerts', owner, repo],
    queryFn: () => fetch(`/api/repos/${owner}/${repo}/security/alerts`).then(r => r.json()),
    enabled: !!owner,
  })

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <ShieldAlert size={16} color="var(--text-muted)" />
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          Security Alerts
        </h3>
        {alerts.length > 0 && (
          <span style={{
            fontSize: 10, fontWeight: 600, color: '#ef4444',
            background: 'rgba(239,68,68,0.1)', borderRadius: 10, padding: '2px 8px',
          }}>{alerts.length}</span>
        )}
      </div>
      {isLoading && <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>Loading...</div>}
      {!isLoading && alerts.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>No security alerts</div>
      )}
      <div style={{ maxHeight: 300, overflowY: 'auto' }}>
        {alerts.map(a => (
          <a key={a.id} href={a.url} target="_blank" rel="noopener noreferrer"
            style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
              borderBottom: '1px solid rgba(255,255,255,0.04)', textDecoration: 'none' }}>
            <AlertTriangle size={14} color={sevColor[a.severity] || '#6b7280'} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>{a.description || a.package_name}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{a.alert_type} · {a.package_name}</div>
            </div>
            <span style={{
              fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
              color: sevColor[a.severity], background: `${sevColor[a.severity]}15`,
            }}>{a.severity}</span>
          </a>
        ))}
      </div>
    </div>
  )
}
