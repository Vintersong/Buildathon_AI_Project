import { Candidate, CandidateDetail, JobRequirement, ShortlistCandidate, ReviewTask, AuditEvent } from './types';

const BASE = '/api';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function fetchCandidates(): Promise<Candidate[]> {
  return request<Candidate[]>(`${BASE}/candidates`);
}

export function fetchCandidateDetail(id: string): Promise<CandidateDetail> {
  return request<CandidateDetail>(`${BASE}/candidates/${id}`);
}

export function ingestCandidate(file: File): Promise<Candidate> {
  const form = new FormData();
  form.append('file', file);
  return request<Candidate>(`${BASE}/candidates/ingest`, { method: 'POST', body: form });
}

/**
 * Re-ingest an existing candidate by ID.
 * Accepts either a new CV file OR a LinkedIn URL string — not both.
 * Endpoint: POST /api/candidates/:id/reingest
 */
export function reingestCandidate(id: string, source: File | string): Promise<Candidate> {
  if (source instanceof File) {
    const form = new FormData();
    form.append('file', source);
    return request<Candidate>(`${BASE}/candidates/${id}/reingest`, { method: 'POST', body: form });
  }
  // LinkedIn URL path
  return request<Candidate>(`${BASE}/candidates/${id}/reingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ linkedinUrl: source }),
  });
}

export function patchCandidateStatus(
  id: string,
  complianceStatus: Candidate['complianceStatus']
): Promise<Candidate> {
  return request<Candidate>(`${BASE}/candidates/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ complianceStatus }),
  });
}

export function fetchJobs(): Promise<JobRequirement[]> {
  return request<JobRequirement[]>(`${BASE}/jobs`);
}

export function createJob(
  job: Omit<JobRequirement, 'id' | 'candidatesProcessed' | 'shortlist'> & {
    must_have?: string[];
    nice_to_have?: string[];
  }
): Promise<JobRequirement> {
  return request<JobRequirement>(`${BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(job),
  });
}

export function runShortlist(reqId: string): Promise<ShortlistCandidate[]> {
  return request<ShortlistCandidate[]>(`${BASE}/jobs/${reqId}/shortlist`, { method: 'POST' });
}

export function fetchReviewTasks(): Promise<ReviewTask[]> {
  return request<ReviewTask[]>(`${BASE}/review`);
}

export function resolveTask(caseId: string, resolution: string): Promise<void> {
  return request<void>(`${BASE}/review/${caseId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolution, reviewer: 'human_operator' }),
  });
}

export function fetchAuditEvents(): Promise<AuditEvent[]> {
  return request<AuditEvent[]>(`${BASE}/audit`);
}

export interface AppConfig {
  model: string;
  confidence_threshold: number;
  sovereign_cloud: boolean;
}

export function fetchConfig(): Promise<AppConfig> {
  return request<AppConfig>(`${BASE}/config`);
}

export function saveConfig(cfg: AppConfig): Promise<AppConfig> {
  return request<AppConfig>(`${BASE}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  });
}
