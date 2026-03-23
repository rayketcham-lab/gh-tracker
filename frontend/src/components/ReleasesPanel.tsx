import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Download, Tag } from 'lucide-react';

interface ReleaseAsset {
  release_tag: string;
  asset_name: string;
  download_count: number;
  size_bytes: number;
  created_at: string;
}

interface ReleaseGroup {
  tag: string;
  assets: ReleaseAsset[];
  totalDownloads: number;
}

interface ReleasesPanelProps {
  owner: string;
  repo: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function groupByRelease(assets: ReleaseAsset[]): ReleaseGroup[] {
  const map = new Map<string, ReleaseAsset[]>();
  for (const a of assets) {
    if (!map.has(a.release_tag)) map.set(a.release_tag, []);
    map.get(a.release_tag)!.push(a);
  }
  return Array.from(map.entries()).map(([tag, list]) => ({
    tag,
    assets: list,
    totalDownloads: list.reduce((s, a) => s + a.download_count, 0),
  }));
}

function ReleaseRow({ group, repoName }: { group: ReleaseGroup; repoName: string }) {
  const [open, setOpen] = useState(false);
  const ChevronIcon = open ? ChevronDown : ChevronRight;

  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.5)',
      borderRadius: '10px',
      border: '1px solid rgba(51, 65, 85, 0.5)',
      overflow: 'hidden',
      marginBottom: '8px',
    }}>
      {/* Release header — clickable to collapse */}
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '10px 14px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          color: 'var(--text-primary)',
          transition: 'background 0.15s',
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.03)'; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent'; }}
      >
        <ChevronIcon size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
        <Tag size={14} style={{ color: '#a78bfa', flexShrink: 0 }} />
        <span style={{ fontSize: '13px', fontWeight: 600, flex: 1 }}>
          {group.tag}
        </span>
        {/* Total downloads badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '5px',
          background: 'rgba(6, 182, 212, 0.1)',
          border: '1px solid rgba(6, 182, 212, 0.2)',
          borderRadius: '20px',
          padding: '3px 10px',
        }}>
          <Download size={11} style={{ color: '#22d3ee' }} />
          <span style={{ fontSize: '12px', fontWeight: 700, color: '#22d3ee' }}>
            {group.totalDownloads.toLocaleString()}
          </span>
        </div>
        <a
          href={`https://github.com/${repoName}/releases/tag/${group.tag}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          style={{
            fontSize: '11px',
            color: 'var(--text-muted)',
            textDecoration: 'none',
            padding: '2px 6px',
            borderRadius: '4px',
            border: '1px solid var(--border-color)',
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = '#22d3ee'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-muted)'; }}
        >
          GitHub
        </a>
      </button>

      {/* Expanded assets */}
      {open && (
        <div style={{ borderTop: '1px solid rgba(51, 65, 85, 0.5)' }}>
          {group.assets.map((asset) => (
            <div key={asset.asset_name} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '8px 14px 8px 38px',
              borderBottom: '1px solid rgba(51, 65, 85, 0.3)',
            }}>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)', flex: 1, fontFamily: 'monospace' }}>
                {asset.asset_name}
              </span>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                {formatBytes(asset.size_bytes)}
              </span>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}>
                <Download size={11} style={{ color: '#10b981' }} />
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#34d399' }}>
                  {asset.download_count.toLocaleString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ReleasesPanel({ owner, repo }: ReleasesPanelProps) {
  const repoName = `${owner}/${repo}`;

  const { data = [], isLoading } = useQuery<ReleaseAsset[]>({
    queryKey: ['releases', owner, repo],
    queryFn: () => fetch(`/api/repos/${owner}/${repo}/releases`).then(r => r.json()),
    enabled: !!owner && !!repo,
  });

  const groups = groupByRelease(data);
  const totalDownloads = groups.reduce((s, g) => s + g.totalDownloads, 0);

  return (
    <div className="fade-in-up card-glow" style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-color)',
      borderRadius: '16px',
      padding: '24px',
    }}>
      <div style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Releases &amp; Downloads
          </h3>
          {totalDownloads > 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.2)',
              borderRadius: '20px', padding: '4px 10px',
            }}>
              <Download size={12} style={{ color: '#10b981' }} />
              <span style={{ fontSize: '12px', fontWeight: 700, color: '#34d399' }}>
                {totalDownloads.toLocaleString()} total
              </span>
            </div>
          )}
        </div>
        <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-muted)' }}>
          {groups.length} release{groups.length !== 1 ? 's' : ''} tracked
        </p>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton" style={{ width: '100%', height: '44px', borderRadius: '10px' }} />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <div style={{
          padding: '32px',
          textAlign: 'center',
          color: 'var(--text-muted)',
          fontSize: '13px',
        }}>
          No release data tracked yet
        </div>
      ) : (
        <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
          {groups.map((group) => (
            <ReleaseRow key={group.tag} group={group} repoName={repoName} />
          ))}
        </div>
      )}
    </div>
  );
}
