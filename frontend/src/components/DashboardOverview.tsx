import { useQuery } from '@tanstack/react-query'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { Eye, Download, Star, GitFork, LayoutGrid } from 'lucide-react'
import { fetchDashboard } from '../api'
import type { DashboardRepo } from '../api'

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

interface TrendCellProps {
  repoName: string
  trend: number | null
}

function TrendCell({ repoName, trend }: TrendCellProps) {
  if (trend === null || trend === 0) {
    return (
      <span
        data-testid={`trend-${repoName}`}
        style={{ color: '#64748b', fontWeight: 500 }}
      >
        —
      </span>
    )
  }
  if (trend > 0) {
    return (
      <span
        data-testid={`trend-${repoName}`}
        style={{ color: '#10b981', fontWeight: 600 }}
      >
        ↑ {Math.abs(trend).toFixed(1)}%
      </span>
    )
  }
  return (
    <span
      data-testid={`trend-${repoName}`}
      style={{ color: '#f43f5e', fontWeight: 600 }}
    >
      ↓ {Math.abs(trend).toFixed(1)}%
    </span>
  )
}

interface KpiBlockProps {
  testId: string
  label: string
  value: number
  icon: React.ReactNode
  color: string
  borderColor: string
  iconColor: string
}

function KpiBlock({ testId, label, value, icon, color, borderColor, iconColor }: KpiBlockProps) {
  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: `1px solid ${borderColor}`,
        borderRadius: 12,
        padding: '20px 24px',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        flex: 1,
        minWidth: 0,
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: 10,
          background: color,
          border: `1px solid ${borderColor}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: iconColor,
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div>
        <div
          data-testid={testId}
          style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}
        >
          {formatNumber(value)}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
          {label}
        </div>
      </div>
    </div>
  )
}

export default function DashboardOverview() {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
  })

  if (isLoading || !data) {
    return (
      <div
        data-testid="dashboard-loading"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '48px 0',
          color: 'var(--text-muted)',
          fontSize: 14,
        }}
      >
        Loading dashboard...
      </div>
    )
  }

  const chartData = data.daily_totals.map((d) => ({
    date: formatDate(d.date),
    Views: d.views,
    Clones: d.clones,
  }))

  return (
    <div style={{ marginBottom: 32 }}>
      {/* Section header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <h2
          style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}
        >
          Cross-Repo Overview
        </h2>
        {data.top_referrer && (
          <span
            data-testid="top-referrer"
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: '#22d3ee',
              background: 'rgba(6, 182, 212, 0.12)',
              border: '1px solid rgba(6, 182, 212, 0.25)',
              borderRadius: 20,
              padding: '3px 10px',
            }}
          >
            Top referrer: {data.top_referrer}
          </span>
        )}
      </div>

      {/* KPI row */}
      <div
        style={{
          display: 'flex',
          gap: 12,
          marginBottom: 20,
          flexWrap: 'wrap',
        }}
      >
        <KpiBlock
          testId="kpi-total-views"
          label="Total Views"
          value={data.total_views}
          icon={<Eye size={18} />}
          color="rgba(6, 182, 212, 0.1)"
          borderColor="rgba(6, 182, 212, 0.2)"
          iconColor="#06b6d4"
        />
        <KpiBlock
          testId="kpi-total-clones"
          label="Total Clones"
          value={data.total_clones}
          icon={<Download size={18} />}
          color="rgba(139, 92, 246, 0.1)"
          borderColor="rgba(139, 92, 246, 0.2)"
          iconColor="#8b5cf6"
        />
        <KpiBlock
          testId="kpi-total-stars"
          label="Total Stars"
          value={data.total_stars}
          icon={<Star size={18} />}
          color="rgba(245, 158, 11, 0.1)"
          borderColor="rgba(245, 158, 11, 0.2)"
          iconColor="#f59e0b"
        />
        <KpiBlock
          testId="kpi-total-forks"
          label="Total Forks"
          value={data.total_forks}
          icon={<GitFork size={18} />}
          color="rgba(16, 185, 129, 0.1)"
          borderColor="rgba(16, 185, 129, 0.2)"
          iconColor="#10b981"
        />
        <KpiBlock
          testId="kpi-total-repos"
          label="Repos Tracked"
          value={data.total_repos}
          icon={<LayoutGrid size={18} />}
          color="rgba(244, 63, 94, 0.1)"
          borderColor="rgba(244, 63, 94, 0.2)"
          iconColor="#f43f5e"
        />
      </div>

      {/* Aggregate traffic chart */}
      <div
        data-testid="dashboard-traffic-chart"
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
          borderRadius: 16,
          padding: '20px 24px',
          marginBottom: 20,
        }}
      >
        <div style={{ marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
            Aggregate Traffic
          </h3>
          <p style={{ margin: '4px 0 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
            Daily views and clones across all repos
          </p>
        </div>

        {chartData.length === 0 ? (
          <div
            style={{
              height: 200,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-muted)',
              fontSize: 13,
            }}
          >
            No traffic data yet
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="dashViewsGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="dashClonesGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={{ stroke: '#334155' }} tickLine={false} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: 10,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12, color: '#94a3b8' }} />
              <Area type="monotone" dataKey="Views" stroke="#06b6d4" strokeWidth={2} fill="url(#dashViewsGrad)" dot={false} activeDot={{ r: 4, fill: '#06b6d4', strokeWidth: 0 }} />
              <Area type="monotone" dataKey="Clones" stroke="#8b5cf6" strokeWidth={2} fill="url(#dashClonesGrad)" dot={false} activeDot={{ r: 4, fill: '#8b5cf6', strokeWidth: 0 }} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Repos table */}
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
          borderRadius: 16,
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: '20px 24px 12px' }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
            Repositories
          </h3>
        </div>
        <table
          data-testid="repos-table"
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 13,
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: '1px solid var(--border-color)',
                background: 'rgba(15, 23, 42, 0.5)',
              }}
            >
              {['Repo', 'Views (30d)', 'Clones (30d)', 'Stars', 'Forks', 'Trend'].map((col) => (
                <th
                  key={col}
                  style={{
                    padding: '10px 16px',
                    textAlign: col === 'Repo' ? 'left' : 'right',
                    fontWeight: 600,
                    color: 'var(--text-muted)',
                    fontSize: 11,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.repos.map((repo: DashboardRepo, idx: number) => (
              <tr
                key={repo.repo_name}
                style={{
                  borderBottom: idx < data.repos.length - 1 ? '1px solid var(--border-color)' : 'none',
                }}
              >
                <td style={{ padding: '12px 16px', color: 'var(--text-primary)', fontWeight: 500 }}>
                  {repo.repo_name}
                </td>
                <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                  {formatNumber(repo.views_30d)}
                </td>
                <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                  {formatNumber(repo.clones_30d)}
                </td>
                <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                  {formatNumber(repo.stars)}
                </td>
                <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                  {formatNumber(repo.forks)}
                </td>
                <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                  <TrendCell repoName={repo.repo_name} trend={repo.trend} />
                </td>
              </tr>
            ))}
            {data.repos.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  style={{
                    padding: '32px 16px',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                    fontSize: 13,
                  }}
                >
                  No repositories tracked yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
