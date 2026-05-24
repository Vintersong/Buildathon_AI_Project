import {
  AuditEvent,
  BulkRefreshResult,
  Candidate,
  CandidateDetail,
  CandidatePreview,
  JobRequirement,
  ReviewTask,
  ShortlistCandidate,
  StaleCandidate,
} from './types';

const BASE = '/api';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let message = text || `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(text);
      const detail = parsed.detail || parsed.error;
      if (detail) {
        message = String(detail);
      }
    } catch {
      // Keep the original body text when the response is not JSON.
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

function json(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export function fetchCandidates(): Promise<Candidate[]> {
  return request<Candidate[]>(`${BASE}/candidates`);
}

export function fetchCandidateDetail(id: string): Promise<CandidateDetail> {
  return request<CandidateDetail>(`${BASE}/candidates/${id}`);
}

export function previewCV(resumeText: string): Promise<{ candidate: CandidatePreview }> {
  return request<{ candidate: CandidatePreview }>(`${BASE}/gemini/parse-cv`, json('POST', { resumeText }));
}

export function previewLinkedIn(linkedinUrl: string): Promise<{ candidate: CandidatePreview }> {
  return request<{ candidate: CandidatePreview }>(`${BASE}/gemini/parse-linkedin`, json('POST', { linkedinUrl }));
}

export function ingestCandidate(file: File): Promise<Candidate> {
  const form = new FormData();
  form.append('file', file);
  return request<Candidate>(`${BASE}/candidates/ingest`, { method: 'POST', body: form });
}

export function ingestLinkedInCandidate(linkedinUrl: string): Promise<Candidate> {
  return request<Candidate>(`${BASE}/candidates/ingest/linkedin`, json('POST', { linkedinUrl }));
}

export function reingestCandidate(id: string, source: File | string): Promise<Candidate> {
  if (source instanceof File) {
    const form = new FormData();
    form.append('file', source);
    return request<Candidate>(`${BASE}/candidates/${id}/reingest`, { method: 'POST', body: form });
  }
  return request<Candidate>(`${BASE}/candidates/${id}/reingest/linkedin`, json('POST', { linkedinUrl: source }));
}

export function patchCandidateStatus(
  id: string,
  complianceStatus: Candidate['complianceStatus'],
): Promise<Candidate> {
  return request<Candidate>(`${BASE}/candidates/${id}/status`, json('PATCH', { complianceStatus }));
}

export function clearCandidateReviewFlag(id: string): Promise<Candidate> {
  return request<Candidate>(`${BASE}/candidates/${id}/clear-review-flag`, { method: 'POST' });
}

export interface IntakeProcessResult {
  processed: number;
  skipped: number;
  failed: number;
  errors: { file: string; error: string }[];
  total_intake: number;
  attempted: number;
}

export function processIntake(limit = 25): Promise<IntakeProcessResult> {
  return request<IntakeProcessResult>(`${BASE}/intake/process?limit=${limit}`, { method: 'POST' });
}

export function bulkRefreshCandidates(ids: string[]): Promise<BulkRefreshResult> {
  return request<BulkRefreshResult>(`${BASE}/maintenance/bulk-refresh`, json('POST', { ids }));
}

export function fetchStaleCandidates(months = 6): Promise<{ months: number; candidates: StaleCandidate[] }> {
  return request<{ months: number; candidates: StaleCandidate[] }>(`${BASE}/maintenance/stale?months=${months}`);
}

export function fetchJobs(): Promise<JobRequirement[]> {
  return request<JobRequirement[]>(`${BASE}/jobs`);
}

export function createJob(
  job: Omit<JobRequirement, 'id' | 'candidatesProcessed' | 'shortlist'> & {
    must_have?: string[];
    nice_to_have?: string[];
  },
): Promise<JobRequirement> {
  return request<JobRequirement>(`${BASE}/jobs`, json('POST', job));
}

export function deleteJob(reqId: string): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(`${BASE}/jobs/${reqId}`, { method: 'DELETE' });
}

export function runShortlist(reqId: string, topN = 5): Promise<ShortlistCandidate[]> {
  return request<ShortlistCandidate[]>(`${BASE}/jobs/${reqId}/shortlist?top_n=${topN}`, { method: 'POST' });
}

export function fetchReviewTasks(): Promise<ReviewTask[]> {
  return request<ReviewTask[]>(`${BASE}/review`);
}

export function resolveTask(caseId: string, resolution: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`${BASE}/review/${caseId}/resolve`, json('POST', {
    resolution,
    reviewer: 'human_operator',
  }));
}

export function createOutreachDraft(
  candidateId: string,
  jobId: string,
  candidateName: string,
  jobTitle: string,
): Promise<ReviewTask> {
  return request<ReviewTask>(`${BASE}/review/outreach-draft`, json('POST', {
    candidateId,
    jobId,
    candidateName,
    jobTitle,
  }));
}

export function fetchAuditEvents(): Promise<AuditEvent[]> {
  return request<AuditEvent[]>(`${BASE}/audit`);
}

export interface AppConfig {
  model: string;
  confidence_threshold: number;
  sovereign_cloud: boolean;
  use_local_llm: boolean;
  gemini_api_key_set: boolean;
  gemini_api_key_last4: string | null;
}

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
  return request<AppConfig>(`${BASE}/config`, json('POST', cfg));
}

export interface AssistantMessage {
  role: 'user' | 'assistant';
  content: string;
}

export function sendAssistantMessage(
  messages: AssistantMessage[],
  context: { candidates: Candidate[]; jobs: JobRequirement[]; reviewTasks: ReviewTask[] },
): Promise<{ text: string; actions: Array<{ type: string; data?: unknown }> }> {
  return request<{ text: string; actions: Array<{ type: string; data?: unknown }> }>(
    `${BASE}/gemini/chat`,
    json('POST', { messages, context }),
  );
}

// ---------------------------------------------------------------------------
// CSV bulk ingest
// ---------------------------------------------------------------------------

export interface CSVIngestProgress {
  total: number;
  processed: number;
  skipped: number;
  failed: number;
  errors: { row: number; error: string }[];
  done: boolean;
  started_at: string;
  finished_at: string | null;
}

export async function startCSVIngest(file: File): Promise<{ task_id: string }> {
  const form = new FormData();
  form.append('file', file);
  return request<{ task_id: string }>(`${BASE}/intake/csv`, { method: 'POST', body: form });
}

export function pollCSVIngest(taskId: string): Promise<CSVIngestProgress> {
  return request<CSVIngestProgress>(`${BASE}/intake/csv/${taskId}`);
}
