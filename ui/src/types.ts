/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface Candidate {
  id: string; // e.g. 'BLD-9021-X'
  name: string;
  imageInitials: string;
  seniority: string;
  topSkills: string[];
  matchScore: number; // e.g. 0.94
  complianceStatus: 'COMPLIANT' | 'PENDING REVIEW' | 'EXPIRING (14D)';
  actionsRequired?: boolean;
}

/** Extended candidate with all extracted profile fields — loaded on demand for the detail drawer. */
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

export interface ReviewTask {
  id: string; // e.g., 'ID-9921-X', 'CPL-402'
  type: 'IDENTITY_CONFLICT' | 'COMPLIANCE_FLAG' | 'OUTREACH_DRAFT';
  title: string;
  timestamp: string;
  timeAgo: string;
  confidence: number;
  status: 'pending' | 'resolved' | 'purged';
  
  // For Identity Conflict
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

  // For Compliance Flag
  complianceDetails?: {
    candidateName: string;
    reason: string;
    quarantineValue: string;
    details: string;
  };

  // For Outreach Draft
  outreachDetails?: {
    targetName: string;
    subject: string;
    draftBody: string;
    signals: string[];
  };
}

export interface AuditEvent {
  id: string;
  timestamp: string; // formatted date-time
  action: string; // e.g. record_ingest
  actor: 'SYS' | 'HUMAN' | 'SEC';
  payloadSummary: string;
  confidence: number;
}
