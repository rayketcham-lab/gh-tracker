import { useQuery } from '@tanstack/react-query'
import { Bot, ShieldCheck, ShieldAlert } from 'lucide-react'

interface BotAnalysis {
  clone_view_ratio: number
  consistent_daily_clones: boolean
  single_cloner_volume: boolean
  referrer_absence: boolean
  weekend_weekday_ratio: number
  verdict: string
}

const verdictConfig: Record<string, { icon: typeof Bot; color: string; bg: string; label: string }> = {
  likely_automated: { icon: Bot, color: '#ef4444', bg: 'rgba(239,68,68,0.1)', label: 'Likely Automated' },
  likely_human: { icon: ShieldCheck, color: '#10b981', bg: 'rgba(16,185,129,0.1)', label: 'Likely Human' },
  mixed: { icon: ShieldAlert, color: '#eab308', bg: 'rgba(234,179,8,0.1)', label: 'Mixed Signals' },
}

export default function BotDetectionBadge({ owner, repo }: { owner: string; repo: string }) {
  const { data: analysis, isLoading } = useQuery<BotAnalysis>({
    queryKey: ['bot-analysis', owner, repo],
    queryFn: () => fetch(`/api/repos/${owner}/${repo}/bot-analysis`).then(r => r.json()),
    enabled: !!owner,
  })

  if (isLoading || !analysis || !analysis.verdict) return null

  const cfg = verdictConfig[analysis.verdict] || verdictConfig.mixed
  const Icon = cfg.icon

  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: cfg.bg,
      border: `1px solid ${cfg.color}30`,
      borderRadius: 8, padding: '4px 10px',
      fontSize: 11, fontWeight: 500, color: cfg.color,
      cursor: 'default',
    }}
    title={`Clone/View: ${(analysis.clone_view_ratio ?? 0).toFixed(2)} | Weekend/Weekday: ${(analysis.weekend_weekday_ratio ?? 0).toFixed(2)} | Consistent clones: ${analysis.consistent_daily_clones ? 'yes' : 'no'} | No referrers: ${analysis.referrer_absence ? 'yes' : 'no'}`}
    >
      <Icon size={12} />
      {cfg.label}
    </div>
  )
}
