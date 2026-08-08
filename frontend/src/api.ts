// API client for gh-tracker backend

export interface TrafficDay {
  date: string;
  views: number;
  unique_visitors: number;
  clones: number;
  unique_cloners: number;
}

export interface Referrer {
  referrer: string;
  views: number;
  unique_visitors: number;
}

export interface PopularPath {
  path: string;
  title: string;
  views: number;
  unique_visitors: number;
}

export interface HealthResponse {
  status: string;
}

const BASE = '/api';

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return fetchJSON<HealthResponse>(`${BASE}/health`);
}

export async function fetchRepos(): Promise<string[]> {
  return fetchJSON<string[]>(`${BASE}/repos`);
}

export async function fetchTraffic(owner: string, repo: string): Promise<TrafficDay[]> {
  return fetchJSON<TrafficDay[]>(`${BASE}/repos/${owner}/${repo}/traffic`);
}

export async function fetchReferrers(owner: string, repo: string): Promise<Referrer[]> {
  return fetchJSON<Referrer[]>(`${BASE}/repos/${owner}/${repo}/referrers`);
}

export async function fetchPaths(owner: string, repo: string): Promise<PopularPath[]> {
  return fetchJSON<PopularPath[]>(`${BASE}/repos/${owner}/${repo}/paths`);
}

// Parse "owner/repo" string
export function parseRepo(fullName: string): { owner: string; repo: string } {
  const parts = fullName.split('/');
  if (parts.length !== 2) {
    throw new Error(`Invalid repo format: ${fullName}`);
  }
  return { owner: parts[0], repo: parts[1] };
}

export interface DashboardRepo {
  repo_name: string;
  views_30d: number;
  unique_visitors_30d: number;
  clones_30d: number;
  stars: number;
  forks: number;
  trend: number | null;
}

export interface DashboardDayTotal {
  date: string;
  views: number;
  clones: number;
}

export interface DashboardData {
  total_repos: number;
  total_views: number;
  total_unique_visitors: number;
  total_clones: number;
  total_stars: number;
  total_forks: number;
  top_referrer: string | null;
  repos: DashboardRepo[];
  daily_totals: DashboardDayTotal[];
}

export async function fetchDashboard(): Promise<DashboardData> {
  const resp = await fetch('/api/dashboard');
  if (!resp.ok) throw new Error('Failed to fetch dashboard');
  return resp.json();
}
