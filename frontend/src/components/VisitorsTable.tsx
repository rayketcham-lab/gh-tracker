import { Users, ExternalLink } from 'lucide-react';

interface VisitorSummary {
  repo_name: string;
  total_unique_visitors: number;
  total_views: number;
  days_with_traffic: number;
}

interface VisitorsTableProps {
  data: VisitorSummary[];
  loading?: boolean;
  selectedRepo?: string;
  onSelectRepo?: (repo: string) => void;
}

export default function VisitorsTable({ data, loading = false, selectedRepo, onSelectRepo }: VisitorsTableProps) {
  return (
    <div
      className="fade-in-up card-glow"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderRadius: '16px',
        padding: '24px',
      }}
    >
      <div style={{ marginBottom: '20px' }}>
        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
          Unique Visitors by Repository
        </h3>
        <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
          Click a repo to view its details &middot; click the arrow to open on GitHub
        </p>
      </div>

      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="skeleton" style={{ width: '100%', height: '44px', borderRadius: '8px' }} />
          ))}
        </div>
      ) : data.length === 0 ? (
        <div
          style={{
            padding: '48px 0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-muted)',
            fontSize: '14px',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          <Users size={28} style={{ opacity: 0.4 }} />
          <span>No visitor data yet</span>
        </div>
      ) : (
        <div style={{ overflowX: 'auto', maxHeight: '400px', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Repository', 'Visitors', 'Views', 'Days', ''].map((h, i) => (
                  <th
                    key={h || `action-${i}`}
                    style={{
                      textAlign: h === 'Repository' ? 'left' : 'right',
                      padding: '8px 12px',
                      fontSize: '11px',
                      fontWeight: 600,
                      color: 'var(--text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      borderBottom: '1px solid var(--border-color)',
                      position: 'sticky',
                      top: 0,
                      background: 'var(--bg-card)',
                      width: h === '' ? '40px' : undefined,
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row, idx) => {
                const isSelected = selectedRepo === row.repo_name;
                return (
                  <tr
                    key={row.repo_name}
                    style={{
                      borderBottom: idx < data.length - 1 ? '1px solid rgba(51,65,85,0.5)' : 'none',
                      cursor: 'pointer',
                      transition: 'background 0.15s',
                      background: isSelected ? 'rgba(6, 182, 212, 0.08)' : 'transparent',
                      borderLeft: isSelected ? '3px solid #06b6d4' : '3px solid transparent',
                    }}
                    onClick={() => {
                      onSelectRepo?.(row.repo_name);
                      // Scroll to top so user sees the updated charts
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) {
                        (e.currentTarget as HTMLTableRowElement).style.background = 'rgba(255,255,255,0.04)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLTableRowElement).style.background = isSelected
                        ? 'rgba(6, 182, 212, 0.08)'
                        : 'transparent';
                    }}
                  >
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{
                          width: '24px',
                          height: '24px',
                          borderRadius: '6px',
                          background: isSelected ? 'rgba(6, 182, 212, 0.15)' : 'rgba(16, 185, 129, 0.1)',
                          border: `1px solid ${isSelected ? 'rgba(6, 182, 212, 0.3)' : 'rgba(16, 185, 129, 0.2)'}`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                        }}>
                          <span style={{
                            fontSize: '10px',
                            fontWeight: 700,
                            color: isSelected ? '#06b6d4' : '#10b981',
                          }}>
                            {idx + 1}
                          </span>
                        </div>
                        <span style={{
                          fontSize: '13px',
                          color: isSelected ? '#22d3ee' : 'var(--text-primary)',
                          fontFamily: 'monospace',
                          fontWeight: isSelected ? 600 : 400,
                        }}>
                          {row.repo_name}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px' }}>
                        <Users size={12} style={{ color: '#10b981' }} />
                        <span style={{ fontSize: '14px', fontWeight: 700, color: '#34d399' }}>
                          {row.total_unique_visitors.toLocaleString()}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                      <span style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                        {row.total_views.toLocaleString()}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                      <span style={{
                        fontSize: '12px',
                        color: 'var(--text-muted)',
                        background: 'rgba(100, 116, 139, 0.1)',
                        padding: '2px 8px',
                        borderRadius: '10px',
                      }}>
                        {row.days_with_traffic}d
                      </span>
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'right' }}>
                      <a
                        href={`https://github.com/${row.repo_name}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: '28px',
                          height: '28px',
                          borderRadius: '6px',
                          background: 'rgba(100, 116, 139, 0.1)',
                          color: 'var(--text-muted)',
                          transition: 'all 0.15s',
                          textDecoration: 'none',
                        }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(6, 182, 212, 0.15)';
                          (e.currentTarget as HTMLAnchorElement).style.color = '#22d3ee';
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(100, 116, 139, 0.1)';
                          (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-muted)';
                        }}
                        title={`Open ${row.repo_name} on GitHub`}
                      >
                        <ExternalLink size={13} />
                      </a>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
