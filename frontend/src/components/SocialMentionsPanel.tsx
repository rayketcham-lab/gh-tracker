import { useQuery } from '@tanstack/react-query';
import { ExternalLink } from 'lucide-react';

interface Mention {
  id: number;
  repo_name: string;
  platform: string;
  url: string;
  title: string;
  score: number | null;
  author: string | null;
  discovered_at: string;
}

interface SocialMentionsPanelProps {
  repoName: string;
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / (1000 * 60));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

interface PlatformBadgeProps {
  platform: string;
}

function PlatformBadge({ platform }: PlatformBadgeProps) {
  const configs: Record<string, { label: string; bg: string; color: string; border: string }> = {
    hackernews: {
      label: 'HN',
      bg: 'rgba(255, 102, 0, 0.12)',
      color: '#ff6600',
      border: 'rgba(255, 102, 0, 0.25)',
    },
    reddit: {
      label: 'Reddit',
      bg: 'rgba(59, 130, 246, 0.12)',
      color: '#60a5fa',
      border: 'rgba(59, 130, 246, 0.25)',
    },
    devto: {
      label: 'Dev.to',
      bg: 'rgba(15, 15, 15, 0.5)',
      color: '#e5e7eb',
      border: 'rgba(255, 255, 255, 0.1)',
    },
  };

  const cfg = configs[platform.toLowerCase()] ?? {
    label: platform,
    bg: 'rgba(100, 116, 139, 0.12)',
    color: 'var(--text-muted)',
    border: 'rgba(100, 116, 139, 0.25)',
  };

  return (
    <span style={{
      fontSize: '10px',
      fontWeight: 600,
      padding: '2px 7px',
      borderRadius: '8px',
      background: cfg.bg,
      color: cfg.color,
      border: `1px solid ${cfg.border}`,
      flexShrink: 0,
      letterSpacing: '0.02em',
    }}>
      {cfg.label}
    </span>
  );
}

export default function SocialMentionsPanel({ repoName }: SocialMentionsPanelProps) {
  const [owner, repo] = repoName.split('/');

  const { data: mentions = [], isLoading } = useQuery<Mention[]>({
    queryKey: ['mentions', owner, repo],
    queryFn: () =>
      fetch(`/api/repos/${owner}/${repo}/mentions`).then(r => r.json()),
    enabled: !!owner && !!repo,
  });

  return (
    <div className="fade-in-up card-glow" style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-color)',
      borderRadius: '16px',
      padding: '24px',
    }}>
      {/* Panel header */}
      <div style={{ marginBottom: '16px' }}>
        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
          Social Mentions
        </h3>
        <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
          {repoName}
        </p>
      </div>

      {/* Loading skeleton */}
      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {[1, 2, 3].map(i => (
            <div key={i} className="skeleton" style={{ width: '100%', height: '52px', borderRadius: '8px' }} />
          ))}
        </div>
      ) : mentions.length === 0 ? (
        /* Empty state */
        <div style={{
          padding: '40px 16px',
          textAlign: 'center',
          color: 'var(--text-muted)',
          fontSize: '13px',
        }}>
          No mentions found
        </div>
      ) : (
        /* Mentions list */
        <div style={{ maxHeight: '350px', overflowY: 'auto' }}>
          {mentions.map((mention) => (
            <a
              key={mention.id}
              href={mention.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
                padding: '10px 12px',
                borderRadius: '8px',
                textDecoration: 'none',
                transition: 'background 0.15s',
                marginBottom: '2px',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(255,255,255,0.03)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.background = 'transparent';
              }}
            >
              {/* Platform badge */}
              <div style={{ paddingTop: '2px' }}>
                <PlatformBadge platform={mention.platform} />
              </div>

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: '13px',
                  color: 'var(--text-primary)',
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  marginBottom: '3px',
                }}>
                  {mention.title}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {mention.score !== null && (
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {mention.score} pts
                    </span>
                  )}
                  {mention.author && (
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      by {mention.author}
                    </span>
                  )}
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {timeAgo(mention.discovered_at)}
                  </span>
                </div>
              </div>

              <ExternalLink size={11} style={{ color: 'var(--text-muted)', flexShrink: 0, marginTop: '3px' }} />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
