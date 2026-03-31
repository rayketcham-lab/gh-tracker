import { useQuery } from '@tanstack/react-query'
import { GitBranch, Shield, ShieldOff } from 'lucide-react'

interface Branch { repo_name: string; name: string; protected: number; protection_json: string }

export default function BranchList({ owner, repo }: { owner: string; repo: string }) {
  const { data: branches = [], isLoading } = useQuery<Branch[]>({
    queryKey: ['branches', owner, repo],
    queryFn: () => fetch(`/api/repos/${owner}/${repo}/branches`).then(r => r.json()),
    enabled: !!owner,
  })

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <GitBranch size={16} color="var(--text-muted)" />
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          Branches
        </h3>
        <span style={{
          fontSize: 10, color: 'var(--text-muted)',
          background: 'rgba(255,255,255,0.05)', borderRadius: 10, padding: '2px 8px',
        }}>{branches.length}</span>
      </div>
      {isLoading && <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>Loading...</div>}
      {!isLoading && branches.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>
          No branch data collected
        </div>
      )}
      {branches.map(b => (
        <div key={b.name} style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
          borderBottom: '1px solid rgba(255,255,255,0.04)',
        }}>
          {b.protected ? <Shield size={14} color="#10b981" /> : <ShieldOff size={14} color="#6b7280" />}
          <span style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 }}>{b.name}</span>
          {b.protected ? (
            <span style={{
              fontSize: 10, color: '#10b981', background: 'rgba(16,185,129,0.1)',
              borderRadius: 4, padding: '1px 6px',
            }}>protected</span>
          ) : (
            <span style={{
              fontSize: 10, color: '#6b7280', background: 'rgba(107,114,128,0.1)',
              borderRadius: 4, padding: '1px 6px',
            }}>unprotected</span>
          )}
        </div>
      ))}
    </div>
  )
}
