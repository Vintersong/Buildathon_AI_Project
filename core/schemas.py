from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime

class Identity(BaseModel):
    primary_name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    linkedin_url: Optional[str] = None

class Profile(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    seniority: Optional[str] = None
    years_of_experience: Optional[int] = None
    study_degrees: List[str] = Field(default_factory=list)
    technologies_used: List[str] = Field(default_factory=list)
    languages_spoken: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    previous_jobs: List[str] = Field(default_factory=list)
    projects_developed: List[str] = Field(default_factory=list)

class State(BaseModel):
    status: str = "new"
    tags: List[str] = Field(default_factory=list)
    stale: bool = False
    duplicate_of: Optional[str] = None
    archived: bool = False
    last_refreshed_at: Optional[str] = None

class Compliance(BaseModel):
    consent_basis: Optional[str] = None
    source: Optional[str] = None
    retention_until: Optional[str] = None
    data_region: str = "EEA"
    sensitive_data_detected: List[str] = Field(default_factory=list)
    redaction_required: bool = False
    human_review_required: bool = False

class Scores(BaseModel):
    extraction_confidence: Optional[float] = None
    identity_confidence: Optional[float] = None
    freshness_score: Optional[float] = None
    last_match_score: Optional[float] = None
    review_risk: Optional[float] = None

class CandidateRecord(BaseModel):
    schema_version: str = "1.0"
    created_at: str
    updated_at: str
    identity: Identity = Field(default_factory=Identity)
    profile: Profile = Field(default_factory=Profile)
    state: State = Field(default_factory=State)
    compliance: Compliance = Field(default_factory=Compliance)
    scores: Scores = Field(default_factory=Scores)
    provenance: List[Dict[str, Any]] = Field(default_factory=list)

class CandidateExtraction(BaseModel):
    name: Optional[str]
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    linkedin_url: Optional[str]
    seniority: Optional[str]
    years_of_experience: Optional[int]
    study_degrees: List[str] = Field(default_factory=list)
    technologies_used: List[str] = Field(default_factory=list)
    languages_spoken: List[str] = Field(default_factory=list)
    location: Optional[str]
    previous_jobs: List[str] = Field(default_factory=list)
    projects_developed: List[str] = Field(default_factory=list)
    summary: Optional[str]
    extraction_confidence: float
    review_flags: List[str] = Field(default_factory=list)

class ProvenanceEvent(BaseModel):
    event_id: str
    event_type: str
    timestamp: str
    source: Dict[str, str]
    actor: Dict[str, str]
    model: Optional[Dict[str, str]] = None
    changes: List[Dict[str, Any]] = Field(default_factory=list)
    review: Dict[str, Any] = Field(default_factory=dict)

class RequirementCriteria(BaseModel):
    must_have: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    language: List[str] = Field(default_factory=list)
    category: Optional[str] = None

class RequirementRecord(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    requirements: RequirementCriteria = Field(default_factory=RequirementCriteria)
    scoring: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    created_at: str
    updated_at: str

