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

export interface IntakeProcessResult {
  processed: number;
  skipped: number;
  failed: number;
  errors: { file: string; error: string }[];
  total_intake: number;
  attempted: number;
}

/** Bulk-ingest everything in intake/cvs/. Capped server-side by `limit`. */
export function processIntake(limit = 25): Promise<IntakeProcessResult> {
  return request<IntakeProcessResult>(`${BASE}/intake/process?limit=${limit}`, { method: 'POST' });
}

export function ingestLinkedInCandidate(linkedinUrl: string): Promise<Candidate> {
  return request<Candidate>(`${BASE}/candidates/ingest/linkedin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ linkedinUrl }),
  });
}

/**
 * Re-ingest an existing candidate by ID.
 * - File source  → POST /api/candidates/:id/reingest          (multipart)
 * - URL source   → POST /api/candidates/:id/reingest/linkedin  (JSON)
 */
export function reingestCandidate(id: string, source: File | string): Promise<Candidate> {
  if (source instanceof File) {
    const form = new FormData();
    form.append('file', source);
    return request<Candidate>(`${BASE}/candidates/${id}/reingest`, { method: 'POST', body: form });
  }
  return request<Candidate>(`${BASE}/candidates/${id}/reingest/linkedin`, {
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

export function deleteJob(reqId: string): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(`${BASE}/jobs/${reqId}`, { method: 'DELETE' });
}

/**
 * Clear an orphaned PENDING REVIEW flag on a candidate when no pending
 * review tasks reference them. Backend refuses (409) if open cases still exist.
 */
export function clearCandidateReviewFlag(id: string): Promise<Candidate> {
  return request<Candidate>(`${BASE}/candidates/${id}/clear-review-flag`, { method: 'POST' });
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

/**
 * Ask the agent to generate a personalised outreach email draft for a
 * shortlisted candidate + job pairing.  The backend creates an
 * OUTREACH_DRAFT ReviewTask and returns it so the UI can immediately
 * open it in the ReviewQueue without a full page reload.
 *
 * Endpoint: POST /api/review/outreach-draft
 */
export function createOutreachDraft(
  candidateId: string,
  jobId: string,
  candidateName: string,
  jobTitle: string
): Promise<ReviewTask> {
  return request<ReviewTask>(`${BASE}/review/outreach-draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidateId, jobId, candidateName, jobTitle }),
  });
}

export function fetchAuditEvents(): Promise<AuditEvent[]> {
  return request<AuditEvent[]>(`${BASE}/audit`);
}

export interface AppConfig {
  model: string;
  confidence_threshold: number;
  sovereign_cloud: boolean;
  /** When true, the backend routes extract/match/outreach through LM Studio. */
  use_local_llm: boolean;
  /** True iff a user-supplied API key is stored in .secrets.json. */
  gemini_api_key_set: boolean;
  /** Last 4 chars of the stored key, or null if none. */
  gemini_api_key_last4: string | null;
}

/**
 * Write shape. `gemini_api_key` is optional:
 *  - omit / undefined → leave key as-is
 *  - ""               → clear stored key
 *  - non-empty        → save as new key
 */
export interface AppConfigUpdate {
  model: string;
  confidence_threshold: number;
  sovereign_cloud: boolean;
  use_local_llm: boolean;
  gemini_api_key?: string;
}

export interface LmStudioStatus {
  available: boolean;
  model: string;
  base_url: string;
}

export function fetchLmStudioStatus(): Promise<LmStudioStatus> {
  return request<LmStudioStatus>(`${BASE}/lm-studio/status`);
}

export function fetchConfig(): Promise<AppConfig> {
  return request<AppConfig>(`${BASE}/config`);
}

export function saveConfig(cfg: AppConfigUpdate): Promise<AppConfig> {
  return request<AppConfig>(`${BASE}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  });
}
