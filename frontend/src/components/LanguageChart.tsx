import { useQuery } from '@tanstack/react-query';

const LANGUAGE_COLORS: Record<string, string> = {
  Rust: '#dea584',
  Python: '#3572A5',
  JavaScript: '#f1e05a',
  TypeScript: '#3178c6',
  Go: '#00ADD8',
  Java: '#b07219',
  C: '#555555',
  'C++': '#f34b7d',
  Ruby: '#701516',
  Shell: '#89e051',
  HTML: '#e34c26',
  CSS: '#663399',
};

function getColor(lang: string): string {
  return LANGUAGE_COLORS[lang] ?? '#6b7280';
}

interface RepoMetadataSlim {
  languages_json: string;
}

interface LanguageChartProps {
  repoName: string;
}

export default function LanguageChart({ repoName }: LanguageChartProps) {
  const [owner, repo] = repoName.split('/');

  const { data: meta, isLoading } = useQuery<RepoMetadataSlim>({
    queryKey: ['metadata', owner, repo],
    queryFn: () => fetch(`/api/repos/${owner}/${repo}/metadata`).then(r => r.json()),
    enabled: !!owner && !!repo,
  });

  if (isLoading) {
    return (
      <div className="fade-in-up card-glow" style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderRadius: '16px',
        padding: '24px',
      }}>
        <div className="skeleton" style={{ width: '100%', height: '160px', borderRadius: '8px' }} />
      </div>
    );
  }

  let langs: Record<string, number> = {};
  try {
    langs = JSON.parse(meta?.languages_json ?? '{}');
  } catch {
    // ignore parse error
  }

  const entries = Object.entries(langs);

  if (entries.length === 0) {
    return (
      <div className="fade-in-up card-glow" style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderRadius: '16px',
        padding: '24px',
      }}>
        <h3 style={{ margin: '0 0 8px 0', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
          Languages
        </h3>
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-muted)' }}>
          No language data available
        </p>
      </div>
    );
  }

  const total = entries.reduce((s, [, v]) => s + v, 0);
  const sorted = [...entries].sort(([, a], [, b]) => b - a);

  return (
    <div className="fade-in-up card-glow" style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-color)',
      borderRadius: '16px',
      padding: '24px',
    }}>
      <div style={{ marginBottom: '16px' }}>
        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
          Languages
        </h3>
        <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
          Breakdown by bytes of code
        </p>
      </div>

      {/* Stacked horizontal bar */}
      <div style={{
        display: 'flex',
        height: '12px',
        borderRadius: '6px',
        overflow: 'hidden',
        marginBottom: '16px',
      }}>
        {sorted.map(([lang, bytes]) => (
          <div
            key={lang}
            title={`${lang}: ${((bytes / total) * 100).toFixed(1)}%`}
            style={{
              flex: bytes,
              background: getColor(lang),
            }}
          />
        ))}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {sorted.map(([lang, bytes]) => {
          const pct = ((bytes / total) * 100).toFixed(1);
          return (
            <div key={lang} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}>
              <div style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                background: getColor(lang),
                flexShrink: 0,
              }} />
              <span style={{
                fontSize: '13px',
                color: 'var(--text-secondary)',
                fontWeight: 500,
                flex: 1,
              }}>
                {lang}
              </span>
              <span style={{
                fontSize: '13px',
                color: 'var(--text-muted)',
                fontVariantNumeric: 'tabular-nums',
              }}>
                {pct}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
