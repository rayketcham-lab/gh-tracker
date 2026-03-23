import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Eye, Users, Download, TrendingUp, Calendar, ChevronDown,
  GitBranch, Activity, ExternalLink,
} from 'lucide-react'
import { fetchRepos, fetchTraffic, fetchReferrers, fetchPaths, parseRepo } from './api'
import type { TrafficDay } from './api'
import KpiCard from './components/KpiCard'
import TrafficChart from './components/TrafficChart'
import ReferrersChart from './components/ReferrersChart'
import PopularPaths from './components/PopularPaths'
import VisitorsTable from './components/VisitorsTable'

interface VisitorSummary {
  repo_name: string
  total_unique_visitors: number
  total_views: number
  days_with_traffic: number
}

function App() {
  const [selectedRepo, setSelectedRepo] = useState<string>('')

  const { data: repos = [], isLoading: reposLoading } = useQuery({
    queryKey: ['repos'],
    queryFn: fetchRepos,
  })

  const activeRepo = selectedRepo || repos[0] || ''
  const parsed = activeRepo ? parseRepo(activeRepo) : { owner: '', repo: '' }

  const { data: traffic = [], isLoading: trafficLoading } = useQuery({
    queryKey: ['traffic', parsed.owner, parsed.repo],
    queryFn: () => fetchTraffic(parsed.owner, parsed.repo),
    enabled: !!parsed.owner,
  })

  const { data: referrers = [], isLoading: referrersLoading } = useQuery({
    queryKey: ['referrers', parsed.owner, parsed.repo],
    queryFn: () => fetchReferrers(parsed.owner, parsed.repo),
    enabled: !!parsed.owner,
  })

  const { data: paths = [], isLoading: pathsLoading } = useQuery({
    queryKey: ['paths', parsed.owner, parsed.repo],
    queryFn: () => fetchPaths(parsed.owner, parsed.repo),
    enabled: !!parsed.owner,
  })

  const { data: visitorSummary = [], isLoading: visitorsLoading } = useQuery<VisitorSummary[]>({
    queryKey: ['visitors-summary'],
    queryFn: () => fetch('/api/visitors/summary').then(r => r.json()),
  })

  const kpis = computeKpis(traffic)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      {/* Header */}
      <header style={{
        borderBottom: '1px solid var(--border-color)',
        padding: '16px 32px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(12px)',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'linear-gradient(135deg, #06b6d4, #10b981)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Activity size={20} color="white" />
          </div>
          <div>
            <h1 className="gradient-text" style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>
              gh-tracker
            </h1>
            <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0 }}>
              GitHub Analytics Dashboard
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ position: 'relative' }}>
            <select
              value={activeRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              style={{
                appearance: 'none',
                background: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: 10,
                padding: '8px 36px 8px 14px',
                color: 'var(--text-primary)',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
                minWidth: 220,
                outline: 'none',
              }}
            >
              {reposLoading && <option>Loading...</option>}
              {repos.length === 0 && !reposLoading && <option>No repos tracked</option>}
              {repos.map(r => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
            <ChevronDown size={14} style={{
              position: 'absolute', right: 12, top: '50%',
              transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none',
            }} />
          </div>

          {activeRepo && (
            <a
              href={`https://github.com/${activeRepo}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                background: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: 10, padding: '8px 14px',
                color: 'var(--text-secondary)',
                fontSize: 12, fontWeight: 500,
                textDecoration: 'none',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.borderColor = 'rgba(6, 182, 212, 0.4)';
                (e.currentTarget as HTMLAnchorElement).style.color = '#22d3ee';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--border-color)';
                (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-secondary)';
              }}
            >
              <ExternalLink size={13} />
              Open on GitHub
            </a>
          )}

          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'rgba(16, 185, 129, 0.1)',
            border: '1px solid rgba(16, 185, 129, 0.2)',
            borderRadius: 20, padding: '6px 12px',
          }}>
            <div className="pulse-dot" style={{
              width: 6, height: 6, borderRadius: '50%', background: '#10b981',
            }} />
            <span style={{ fontSize: 11, color: '#34d399', fontWeight: 500 }}>Live</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main style={{ padding: '24px 32px', maxWidth: 1400, margin: '0 auto' }}>

        {/* Row 1: KPI Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}>
          <KpiCard title="Views (14d)" value={kpis.views14d} trend={kpis.viewsTrend}
            icon={<Eye size={20} />} color="cyan" loading={trafficLoading} animClass="fade-in-up-1" />
          <KpiCard title="Unique Visitors" value={kpis.uniques14d} trend={kpis.uniquesTrend}
            icon={<Users size={20} />} color="emerald" loading={trafficLoading} animClass="fade-in-up-2" />
          <KpiCard title="Clones (14d)" value={kpis.clones14d} trend={kpis.clonesTrend}
            icon={<Download size={20} />} color="violet" loading={trafficLoading} animClass="fade-in-up-3" />
          <KpiCard title="All-Time Views" value={kpis.totalViews}
            subtitle={`${traffic.length} days archived`}
            icon={<TrendingUp size={20} />} color="amber" loading={trafficLoading} animClass="fade-in-up-4" />
          <KpiCard title="Days Archived" value={traffic.length}
            subtitle="Preserved from 14d expiry"
            icon={<Calendar size={20} />} color="rose" loading={trafficLoading} animClass="fade-in-up-5" />
        </div>

        {/* Row 2: Traffic Chart (full width) */}
        <div style={{ marginBottom: 24 }}>
          <TrafficChart data={traffic} loading={trafficLoading} />
        </div>

        {/* Row 3: Visitors Table + Referrers side by side */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 16,
          marginBottom: 24,
        }}>
          <VisitorsTable
            data={visitorSummary}
            loading={visitorsLoading}
            selectedRepo={activeRepo}
            onSelectRepo={(repo) => setSelectedRepo(repo)}
          />
          <ReferrersChart data={referrers} loading={referrersLoading} />
        </div>

        {/* Row 4: Popular Paths (full width) */}
        <div style={{ marginBottom: 24 }}>
          <PopularPaths data={paths} loading={pathsLoading} />
        </div>

        {/* Footer */}
        <footer style={{
          marginTop: 24, paddingTop: 24,
          borderTop: '1px solid var(--border-color)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: 12 }}>
            <GitBranch size={14} />
            <span>gh-tracker v0.1.0</span>
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            Archiving GitHub analytics since day one
          </div>
        </footer>
      </main>
    </div>
  )
}

interface Kpis {
  views14d: number
  uniques14d: number
  clones14d: number
  totalViews: number
  viewsTrend: number
  uniquesTrend: number
  clonesTrend: number
}

function computeKpis(traffic: TrafficDay[]): Kpis {
  const last14 = traffic.slice(-14)
  const prev14 = traffic.slice(-28, -14)

  const sum = (arr: TrafficDay[], key: keyof TrafficDay) =>
    arr.reduce((s, d) => s + (Number(d[key]) || 0), 0)

  const views14d = sum(last14, 'views')
  const uniques14d = sum(last14, 'unique_visitors')
  const clones14d = sum(last14, 'clones')

  const prevViews = sum(prev14, 'views')
  const prevUniques = sum(prev14, 'unique_visitors')
  const prevClones = sum(prev14, 'clones')

  const trend = (cur: number, prev: number) =>
    prev > 0 ? ((cur - prev) / prev) * 100 : 0

  return {
    views14d,
    uniques14d,
    clones14d,
    totalViews: sum(traffic, 'views'),
    viewsTrend: trend(views14d, prevViews),
    uniquesTrend: trend(uniques14d, prevUniques),
    clonesTrend: trend(clones14d, prevClones),
  }
}

export default App
