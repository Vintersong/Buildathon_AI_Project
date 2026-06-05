export interface Candidate {
  id: string;
  name: string;
  imageInitials: string;
  seniority: string;
  topSkills: string[];
  matchScore: number;
  complianceStatus: 'COMPLIANT' | 'PENDING REVIEW' | 'EXPIRING (14D)';
  actionsRequired?: boolean;
}

export interface CandidateDetail extends Candidate {
  headline: string;
  summary: string;
  location: string;
  yearsOfExperience: number | null;
  studyDegrees: string[];
  languagesSpoken: string[];
  previousJobs: string[];
  projectsDeveloped: string[];
  allSkills: string[];
  linkedinUrl: string;
  emails: string[];
  consentBasis: string;
  dataRegion: string;
  retentionUntil: string;
  extractionConfidence: number | null;
  lastMatchScore: number | null;
  updatedAt: string;
  createdAt: string;
}

export interface CandidatePreview {
  name: string;
  seniority: string;
  topSkills: string[];
  matchScore: number;
  complianceStatus: Candidate['complianceStatus'];
}

export interface StaleCandidate extends Candidate {
  lastRefreshedAt: string;
  updatedAt: string;
  linkedinUrl: string;
}

export interface ShortlistCandidate {
  id: string;
  name: string;
  confidence: number;
  explanation: string;
  status: 'drafted' | 'pending_review' | 'active';
  initials: string;
}

export interface JobRequirement {
  id: string;
  title: string;
  department: string;
  location: string;
  status: 'MATCHING' | 'STALLED' | 'ARCHIVED' | 'VALIDATING';
  tags: string[];
  candidatesProcessed: number;
  shortlist: ShortlistCandidate[];
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export interface ProjectProspect {
  id: string;
  title: string;
  client: string | null;
  domain: string | null;
  status: 'DRAFT' | 'MATCHING' | 'SHORTLISTED' | 'ARCHIVED';
  tags: string[];
  brief: string;
  requiredSkills: string[];
  niceToHaveSkills: string[];
  minSeniority: string | null;
  locations: string[];
  languages: string[];
  constraintsSummary: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectMatchCandidate {
  id: string;
  name: string;
  confidence: number;
  explanation: string;
  status: 'drafted' | 'shortlisted' | 'discarded';
  initials: string;
}

// ---------------------------------------------------------------------------
// Review / Audit
// ---------------------------------------------------------------------------

export interface ReviewTask {
  id: string;
  type: 'IDENTITY_CONFLICT' | 'COMPLIANCE_FLAG' | 'OUTREACH_DRAFT';
  title: string;
  timestamp: string;
  timeAgo: string;
  confidence: number;
  status: 'pending' | 'resolved' | 'purged';
  existingRecord?: {
    uuid: string;
    name: string;
    currentRole: string;
    location: string;
    linkedin: string;
  };
  proposedRecord?: {
    source: string;
    name: string;
    currentRole: string;
    location: string;
    linkedin: string;
    addedRole?: string;
    removedRole?: string;
  };
  recommendation?: string;
  complianceDetails?: {
    candidateName: string;
    reason: string;
    quarantineValue: string;
    details: string;
  };
  outreachDetails?: {
    targetName: string;
    subject: string;
    draftBody: string;
    signals: string[];
  };
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  action: string;
  actor: 'SYS' | 'HUMAN' | 'SEC';
  payloadSummary: string;
  confidence: number;
}

export interface BulkRefreshResult {
  success: number;
  failed: number;
  errors: { record_id?: string; error: string }[];
}
