import { useQuery } from '@tanstack/react-query'
import { GitPullRequest, ExternalLink } from 'lucide-react'

interface PR {
  repo_name: string; number: number; title: string; state: string
  author: string; labels: string; created_at: string; is_pr: number
}

function timeAgo(d: string): string {
  if (!d) return ''
  const diff = Date.now() - new Date(d).getTime()
  const days = Math.floor(diff / 86400000)
  if (days < 1) return 'today'
  if (days === 1) return 'yesterday'
  return `${days}d ago`
}

export default function PRCenter({ repoFilter }: { repoFilter?: string }) {
  const { data: prs = [], isLoading } = useQuery<PR[]>({
    queryKey: ['open-prs', repoFilter],
    queryFn: () => fetch(`/api/prs${repoFilter ? `?repo=${repoFilter}` : ''}`).then(r => r.json()),
  })

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <GitPullRequest size={16} color="#22d3ee" />
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          Open Pull Requests
        </h3>
        <span style={{
          fontSize: 10, color: 'var(--text-muted)',
          background: 'rgba(255,255,255,0.05)', borderRadius: 10, padding: '2px 8px',
        }}>{prs.length}</span>
      </div>
      {isLoading && <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>Loading...</div>}
      {!isLoading && prs.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>No open PRs</div>
      )}
      <div style={{ maxHeight: 350, overflowY: 'auto' }}>
        {prs.map(pr => (
          <div key={`${pr.repo_name}-${pr.number}`} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
            borderBottom: '1px solid rgba(255,255,255,0.04)',
          }}>
            <GitPullRequest size={14} color="#22d3ee" />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 }}>
                {pr.title}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                {pr.repo_name}#{pr.number} by {pr.author} · {timeAgo(pr.created_at)}
                {pr.labels && ` · ${pr.labels}`}
              </div>
            </div>
            <a href={`https://github.com/${pr.repo_name}/pull/${pr.number}`}
              target="_blank" rel="noopener noreferrer"
              style={{ color: 'var(--text-muted)', flexShrink: 0 }}
              onClick={e => e.stopPropagation()}>
              <ExternalLink size={12} />
            </a>
          </div>
        ))}
      </div>
    </div>
  )
}
