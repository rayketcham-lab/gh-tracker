import { useQuery } from '@tanstack/react-query'
import { Shield, Package, TrendingUp } from 'lucide-react'

interface Enrichment {
  repo_name: string
  scorecard_score: number
  dependent_repos_count: number
  source_rank: number
}

function scoreColor(score: number): string {
  if (score >= 7) return '#10b981'
  if (score >= 4) return '#eab308'
  if (score >= 0) return '#ef4444'
  return 'var(--text-muted)'
}

export default function EnrichmentBadges({ owner, repo }: { owner: string; repo: string }) {
  const { data: enrichment } = useQuery<Enrichment>({
    queryKey: ['enrichment', owner, repo],
    queryFn: () => fetch(`/api/repos/${owner}/${repo}/enrichment`).then(r => r.json()),
    enabled: !!owner,
  })

  if (!enrichment) return null

  const badges = []

  if (enrichment.scorecard_score >= 0) {
    const color = scoreColor(enrichment.scorecard_score)
    badges.push(
      <div key="scorecard" style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        background: `${color}15`, border: `1px solid ${color}30`,
        borderRadius: 8, padding: '3px 8px', fontSize: 11, color,
      }} title="OpenSSF Scorecard">
        <Shield size={11} />
        {enrichment.scorecard_score.toFixed(1)}
      </div>
    )
  }

  if (enrichment.dependent_repos_count > 0) {
    badges.push(
      <div key="deps" style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.3)',
        borderRadius: 8, padding: '3px 8px', fontSize: 11, color: '#a78bfa',
      }} title="Dependent repos">
        <Package size={11} />
        {enrichment.dependent_repos_count} deps
      </div>
    )
  }

  if (enrichment.source_rank > 0) {
    badges.push(
      <div key="rank" style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        background: 'rgba(6,182,212,0.1)', border: '1px solid rgba(6,182,212,0.3)',
        borderRadius: 8, padding: '3px 8px', fontSize: 11, color: '#22d3ee',
      }} title="SourceRank">
        <TrendingUp size={11} />
        Rank {enrichment.source_rank}
      </div>
    )
  }

  if (badges.length === 0) return null

  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {badges}
    </div>
  )
}
