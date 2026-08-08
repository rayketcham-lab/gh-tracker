import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DashboardOverview from './DashboardOverview'
import type { DashboardData } from '../api'

// Mock recharts to avoid SVG rendering issues in jsdom
vi.mock('recharts', () => ({
  AreaChart: ({ children }: { children: React.ReactNode }) => <div data-testid="area-chart">{children}</div>,
  Area: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}))

const mockDashboardData: DashboardData = {
  total_repos: 5,
  total_views: 12500,
  total_unique_visitors: 3200,
  total_clones: 480,
  total_stars: 342,
  total_forks: 87,
  top_referrer: 'github.com',
  repos: [
    {
      repo_name: 'owner/repo-alpha',
      views_30d: 5000,
      unique_visitors_30d: 1200,
      clones_30d: 200,
      stars: 150,
      forks: 40,
      trend: 12.5,
    },
    {
      repo_name: 'owner/repo-beta',
      views_30d: 3000,
      unique_visitors_30d: 800,
      clones_30d: 150,
      stars: 100,
      forks: 30,
      trend: -5.2,
    },
    {
      repo_name: 'owner/repo-gamma',
      views_30d: 4500,
      unique_visitors_30d: 1200,
      clones_30d: 130,
      stars: 92,
      forks: 17,
      trend: null,
    },
  ],
  daily_totals: [
    { date: '2026-03-01', views: 400, clones: 15 },
    { date: '2026-03-02', views: 600, clones: 20 },
    { date: '2026-03-03', views: 550, clones: 18 },
  ],
}

const emptyDashboardData: DashboardData = {
  total_repos: 0,
  total_views: 0,
  total_unique_visitors: 0,
  total_clones: 0,
  total_stars: 0,
  total_forks: 0,
  top_referrer: null,
  repos: [],
  daily_totals: [],
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
}

function renderWithQuery(ui: React.ReactElement) {
  const client = makeQueryClient()
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('DashboardOverview', () => {
  it('renders loading state initially', () => {
    // fetch never resolves during this test
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}))
    renderWithQuery(<DashboardOverview />)
    expect(screen.getByTestId('dashboard-loading')).toBeInTheDocument()
  })

  it('renders KPI cards with data', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => mockDashboardData,
    } as Response)

    renderWithQuery(<DashboardOverview />)

    await waitFor(() => {
      expect(screen.getByTestId('kpi-total-views')).toBeInTheDocument()
    })

    expect(screen.getByTestId('kpi-total-clones')).toBeInTheDocument()
    expect(screen.getByTestId('kpi-total-stars')).toBeInTheDocument()
    expect(screen.getByTestId('kpi-total-forks')).toBeInTheDocument()
    expect(screen.getByTestId('kpi-total-repos')).toBeInTheDocument()

    // Verify values are displayed
    expect(screen.getByTestId('kpi-total-views')).toHaveTextContent('12.5K')
    expect(screen.getByTestId('kpi-total-clones')).toHaveTextContent('480')
    expect(screen.getByTestId('kpi-total-stars')).toHaveTextContent('342')
    expect(screen.getByTestId('kpi-total-forks')).toHaveTextContent('87')
    expect(screen.getByTestId('kpi-total-repos')).toHaveTextContent('5')
  })

  it('renders repo table with trend arrows', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => mockDashboardData,
    } as Response)

    renderWithQuery(<DashboardOverview />)

    await waitFor(() => {
      expect(screen.getByTestId('repos-table')).toBeInTheDocument()
    })

    // Repos should be listed
    expect(screen.getByText('owner/repo-alpha')).toBeInTheDocument()
    expect(screen.getByText('owner/repo-beta')).toBeInTheDocument()
    expect(screen.getByText('owner/repo-gamma')).toBeInTheDocument()

    // Positive trend: green up arrow
    const positiveTrend = screen.getByTestId('trend-owner/repo-alpha')
    expect(positiveTrend).toHaveTextContent('↑')
    expect(positiveTrend).toHaveTextContent('12.5%')

    // Negative trend: red down arrow
    const negativeTrend = screen.getByTestId('trend-owner/repo-beta')
    expect(negativeTrend).toHaveTextContent('↓')
    expect(negativeTrend).toHaveTextContent('5.2%')

    // Null trend: dash
    const nullTrend = screen.getByTestId('trend-owner/repo-gamma')
    expect(nullTrend).toHaveTextContent('—')
  })

  it('renders top referrer', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => mockDashboardData,
    } as Response)

    renderWithQuery(<DashboardOverview />)

    await waitFor(() => {
      expect(screen.getByTestId('top-referrer')).toBeInTheDocument()
    })

    expect(screen.getByTestId('top-referrer')).toHaveTextContent('github.com')
  })

  it('handles empty dashboard gracefully', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => emptyDashboardData,
    } as Response)

    renderWithQuery(<DashboardOverview />)

    await waitFor(() => {
      expect(screen.getByTestId('kpi-total-views')).toBeInTheDocument()
    })

    expect(screen.getByTestId('kpi-total-views')).toHaveTextContent('0')
    expect(screen.getByTestId('kpi-total-repos')).toHaveTextContent('0')
    expect(screen.getByTestId('repos-table')).toBeInTheDocument()
    // No repos rows
    expect(screen.queryByRole('row', { name: /owner/ })).not.toBeInTheDocument()
  })

  it('renders aggregate traffic chart', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => mockDashboardData,
    } as Response)

    renderWithQuery(<DashboardOverview />)

    await waitFor(() => {
      expect(screen.getByTestId('dashboard-traffic-chart')).toBeInTheDocument()
    })

    // The recharts mock renders data-testid="area-chart" inside
    expect(screen.getByTestId('area-chart')).toBeInTheDocument()
  })
})
