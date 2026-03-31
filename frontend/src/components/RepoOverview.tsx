import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Star, GitFork, AlertCircle, ArrowUpDown } from 'lucide-react'

interface RepoMeta {
  repo_name: string
  description: string
  language: string
  stars: number
  forks: number
  open_issues_count: number
  pushed_at: string
  license: string
  topics: string
}

type SortKey = 'repo_name' | 'stars' | 'forks' | 'open_issues_count' | 'pushed_at'

const langColors: Record<string, string> = {
  Python: '#3572A5', TypeScript: '#3178c6', JavaScript: '#f1e05a',
  Rust: '#dea584', Go: '#00ADD8', Java: '#b07219', C: '#555555',
  'C++': '#f34b7d', Ruby: '#701516', Shell: '#89e051', HTML: '#e34c26',
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return 'never'
  const diff = Date.now() - new Date(dateStr).getTime()
  const days = Math.floor(diff / 86400000)
  if (days < 1) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  return `${months}mo ago`
}

export default function RepoOverview({ onSelectRepo }: { onSelectRepo: (repo: string) => void }) {
  const [sortKey, setSortKey] = useState<SortKey>('stars')
  const [sortAsc, setSortAsc] = useState(false)

  const { data: repos = [], isLoading } = useQuery<RepoMeta[]>({
    queryKey: ['all-metadata'],
    queryFn: () => fetch('/api/metadata').then(r => r.json()),
  })

  const sorted = [...repos].sort((a, b) => {
    const av = a[sortKey] ?? '', bv = b[sortKey] ?? ''
    if (typeof av === 'number' && typeof bv === 'number') return sortAsc ? av - bv : bv - av
    return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av))
  })

  const totals = repos.reduce((acc, r) => ({
    stars: acc.stars + (r.stars || 0),
    forks: acc.forks + (r.forks || 0),
    issues: acc.issues + (r.open_issues_count || 0),
  }), { stars: 0, forks: 0, issues: 0 })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(false) }
  }

  const SortHeader = ({ label, field }: { label: string; field: SortKey }) => (
    <th
      onClick={() => handleSort(field)}
      style={{
        padding: '10px 12px', textAlign: field === 'repo_name' ? 'left' : 'right',
        cursor: 'pointer', userSelect: 'none', fontSize: 11, fontWeight: 600,
        color: sortKey === field ? '#22d3ee' : 'var(--text-muted)',
        borderBottom: '1px solid var(--border-color)',
      }}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        {label}
        {sortKey === field && <ArrowUpDown size={10} />}
      </span>
    </th>
  )

  return (
    <div className="card" style={{ padding: 20, marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BarChart3 size={16} color="var(--text-muted)" />
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
            Repository Overview
          </h3>
          <span style={{
            fontSize: 10, color: 'var(--text-muted)',
            background: 'rgba(255,255,255,0.05)', borderRadius: 10, padding: '2px 8px',
          }}>
            {repos.length} repos
          </span>
        </div>
        <div style={{ display: 'flex', gap: 16, fontSize: 11 }}>
          <span style={{ color: '#eab308' }}><Star size={11} /> {totals.stars}</span>
          <span style={{ color: '#8b5cf6' }}><GitFork size={11} /> {totals.forks}</span>
          <span style={{ color: '#f97316' }}><AlertCircle size={11} /> {totals.issues}</span>
        </div>
      </div>

      {isLoading ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>Loading...</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <SortHeader label="Repository" field="repo_name" />
                <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', borderBottom: '1px solid var(--border-color)' }}>Language</th>
                <SortHeader label="Stars" field="stars" />
                <SortHeader label="Forks" field="forks" />
                <SortHeader label="Issues" field="open_issues_count" />
                <SortHeader label="Last Push" field="pushed_at" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr
                  key={r.repo_name}
                  onClick={() => onSelectRepo(r.repo_name)}
                  style={{ cursor: 'pointer', transition: 'background 0.15s' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'rgba(6,182,212,0.05)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <td style={{ padding: '10px 12px', fontSize: 13, color: '#22d3ee', fontWeight: 500 }}>
                    {r.repo_name}
                    {r.description && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400, marginTop: 2 }}>
                        {r.description.length > 80 ? r.description.slice(0, 80) + '...' : r.description}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    {r.language && (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        fontSize: 11, color: 'var(--text-secondary)',
                      }}>
                        <span style={{
                          width: 8, height: 8, borderRadius: '50%',
                          background: langColors[r.language] || '#6b7280',
                        }} />
                        {r.language}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontSize: 12, color: 'var(--text-secondary)' }}>
                    {r.stars || 0}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontSize: 12, color: 'var(--text-secondary)' }}>
                    {r.forks || 0}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontSize: 12, color: 'var(--text-secondary)' }}>
                    {r.open_issues_count || 0}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontSize: 11, color: 'var(--text-muted)' }}>
                    {timeAgo(r.pushed_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
