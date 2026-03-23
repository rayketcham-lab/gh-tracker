import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

interface CommitWeek {
  week_timestamp: number;
  days: number[];
}

interface CommitHeatmapProps {
  owner: string;
  repo: string;
}

const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function intensityColor(count: number, max: number): string {
  if (count === 0 || max === 0) return 'rgba(255,255,255,0.05)';
  const ratio = count / max;
  if (ratio < 0.25) return '#0e4429';
  if (ratio < 0.50) return '#006d32';
  if (ratio < 0.75) return '#26a641';
  return '#39d353';
}

function formatDate(weekTimestamp: number, dayIndex: number): string {
  const d = new Date((weekTimestamp + dayIndex * 86400) * 1000);
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

export default function CommitHeatmap({ owner, repo }: CommitHeatmapProps) {
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null);

  const { data = [], isLoading } = useQuery<CommitWeek[]>({
    queryKey: ['commit-activity', owner, repo],
    queryFn: () => fetch(`/api/repos/${owner}/${repo}/commit-activity`).then(r => r.json()),
    enabled: !!owner && !!repo,
  });

  const maxCount = data.length > 0
    ? Math.max(...data.flatMap(w => w.days))
    : 0;

  return (
    <div className="fade-in-up card-glow" style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-color)',
      borderRadius: '16px',
      padding: '24px',
      position: 'relative',
    }}>
      <div style={{ marginBottom: '16px' }}>
        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
          Commit Activity
        </h3>
        <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
          Weekly commit heatmap
        </p>
      </div>

      {isLoading ? (
        <div className="skeleton" style={{ width: '100%', height: '120px', borderRadius: '8px' }} />
      ) : data.length === 0 ? (
        <div style={{
          height: '120px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
          fontSize: '13px',
        }}>
          No commit activity data
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <div style={{ display: 'flex', gap: '4px', alignItems: 'flex-start' }}>
            {/* Day labels column */}
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '2px',
              paddingTop: '0px',
              flexShrink: 0,
            }}>
              {DAY_LABELS.map((label) => (
                <div key={label} style={{
                  height: '12px',
                  fontSize: '9px',
                  color: 'var(--text-muted)',
                  display: 'flex',
                  alignItems: 'center',
                  paddingRight: '4px',
                  width: '24px',
                }}>
                  {label}
                </div>
              ))}
            </div>

            {/* Week columns */}
            {data.map((week) => (
              <div key={week.week_timestamp} style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '2px',
              }}>
                {week.days.map((count, dayIdx) => (
                  <div
                    key={dayIdx}
                    style={{
                      width: '12px',
                      height: '12px',
                      borderRadius: '2px',
                      background: intensityColor(count, maxCount),
                      cursor: count > 0 ? 'pointer' : 'default',
                    }}
                    onMouseEnter={(e) => {
                      const rect = (e.target as HTMLDivElement).getBoundingClientRect();
                      setTooltip({
                        text: `${formatDate(week.week_timestamp, dayIdx)}: ${count} commit${count !== 1 ? 's' : ''}`,
                        x: rect.left + rect.width / 2,
                        y: rect.top - 8,
                      });
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tooltip */}
      {tooltip && (
        <div style={{
          position: 'fixed',
          left: tooltip.x,
          top: tooltip.y,
          transform: 'translate(-50%, -100%)',
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '8px',
          padding: '6px 10px',
          fontSize: '12px',
          color: 'var(--text-primary)',
          whiteSpace: 'nowrap',
          pointerEvents: 'none',
          zIndex: 100,
          boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
        }}>
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
