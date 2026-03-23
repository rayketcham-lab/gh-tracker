import { useQuery } from '@tanstack/react-query';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface CodeFrequencyPoint {
  week_timestamp: number;
  additions: number;
  deletions: number;
}

interface CodeFrequencyChartProps {
  owner: string;
  repo: string;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: '#1e293b',
      border: '1px solid #334155',
      borderRadius: '10px',
      padding: '10px 14px',
      boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
    }}>
      <p style={{ color: '#94a3b8', fontSize: '11px', margin: '0 0 6px 0' }}>{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: '20px',
          fontSize: '12px',
          marginBottom: '2px',
        }}>
          <span style={{ color: entry.color, fontWeight: 500 }}>{entry.name}</span>
          <span style={{ color: '#f1f5f9', fontWeight: 700 }}>
            {entry.value > 0 ? '+' : ''}{entry.value.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}

function formatWeek(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export default function CodeFrequencyChart({ owner, repo }: CodeFrequencyChartProps) {
  const { data = [], isLoading } = useQuery<CodeFrequencyPoint[]>({
    queryKey: ['code-frequency', owner, repo],
    queryFn: () => fetch(`/api/repos/${owner}/${repo}/code-frequency`).then(r => r.json()),
    enabled: !!owner && !!repo,
  });

  const chartData = data.map((d) => ({
    week: formatWeek(d.week_timestamp),
    Additions: d.additions,
    Deletions: -Math.abs(d.deletions),
  }));

  return (
    <div className="fade-in-up card-glow" style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-color)',
      borderRadius: '16px',
      padding: '24px',
    }}>
      <div style={{ marginBottom: '16px' }}>
        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
          Code Frequency
        </h3>
        <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
          Weekly additions and deletions
        </p>
      </div>

      {isLoading ? (
        <div className="skeleton" style={{ width: '100%', height: '200px', borderRadius: '8px' }} />
      ) : data.length === 0 ? (
        <div style={{
          height: '200px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
          fontSize: '13px',
        }}>
          No code frequency data
        </div>
      ) : (
        <>
          {/* Legend */}
          <div style={{ display: 'flex', gap: '16px', marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#10b981' }} />
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Additions</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#f43f5e' }} />
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Deletions</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="addGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="delGrad" x1="0" y1="1" x2="0" y2="0">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="week"
                tick={{ fill: '#64748b', fontSize: 10 }}
                axisLine={{ stroke: '#334155' }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: '#64748b', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="Additions"
                stroke="#10b981"
                strokeWidth={1.5}
                fill="url(#addGrad)"
                dot={false}
                activeDot={{ r: 3, fill: '#10b981', strokeWidth: 0 }}
                baseValue={0}
              />
              <Area
                type="monotone"
                dataKey="Deletions"
                stroke="#f43f5e"
                strokeWidth={1.5}
                fill="url(#delGrad)"
                dot={false}
                activeDot={{ r: 3, fill: '#f43f5e', strokeWidth: 0 }}
                baseValue={0}
              />
            </AreaChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  );
}
