"""
Offline candidate-role matching helper used by the evaluation harness.

This module intentionally avoids production store/model dependencies. It turns
free-text candidate and role descriptions into a deterministic binary label so
the eval can run in CI and demos without API keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


VALID_LABELS = {"match", "no_match"}

_SENIORITY_RANK = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "middle": 2,
    "senior": 3,
    "lead": 4,
    "staff": 4,
    "principal": 5,
    "director": 5,
}

_SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "python": ("python",),
    "fastapi": ("fastapi", "fast api"),
    "django": ("django",),
    "flask": ("flask",),
    "java": ("java",),
    "spring": ("spring", "spring boot"),
    "javascript": ("javascript", "js"),
    "typescript": ("typescript", "ts"),
    "react": ("react", "react.js", "reactjs"),
    "vue": ("vue", "vue.js", "vuejs"),
    "angular": ("angular",),
    "node.js": ("node.js", "nodejs", "node"),
    "go": ("go", "golang"),
    "rust": ("rust",),
    "ruby": ("ruby",),
    "rails": ("rails", "ruby on rails"),
    "sql": ("sql",),
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
    "mongodb": ("mongodb", "mongo"),
    "redis": ("redis",),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure",),
    "gcp": ("gcp", "google cloud"),
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "terraform": ("terraform",),
    "linux": ("linux",),
    "spark": ("spark", "apache spark"),
    "airflow": ("airflow", "apache airflow"),
    "dbt": ("dbt",),
    "tableau": ("tableau",),
    "power bi": ("power bi", "powerbi"),
    "excel": ("excel",),
    "pytorch": ("pytorch", "py torch"),
    "tensorflow": ("tensorflow", "tensor flow"),
    "machine learning": ("machine learning", "ml"),
    "nlp": ("nlp", "natural language processing"),
    "llms": ("llm", "llms", "large language models"),
    "security": ("security", "cybersecurity", "cyber security"),
    "penetration testing": ("penetration testing", "pentesting"),
    "siem": ("siem",),
    "figma": ("figma",),
    "ux": ("ux", "user experience"),
    "product management": ("product management", "product manager"),
    "agile": ("agile", "scrum"),
    "salesforce": ("salesforce",),
    "hubspot": ("hubspot",),
}

_STOPWORDS = {
    "and", "are", "for", "from", "has", "have", "into", "must", "our",
    "role", "the", "this", "with", "years", "year", "experience", "engineer",
    "developer", "candidate", "seeking", "looking", "strong", "needs",
}


@dataclass(frozen=True)
class MatchSignals:
    skills: set[str]
    years: int | None
    seniority_rank: int | None
    keywords: set[str]


@dataclass(frozen=True)
class MatchDecision:
    label: str
    score: float
    skill_coverage: float
    years_ok: bool
    seniority_ok: bool
    matched_skills: list[str]
    missing_skills: list[str]


def normalize_match_label(value: object) -> str | None:
    """Normalize common label spellings to the eval label space."""
    if value is None:
        return None
    label = str(value).strip().lower()
    label = re.sub(r"[\s-]+", "_", label)
    label = label.replace("not_a_match", "no_match")
    label = label.replace("non_match", "no_match")
    if label in {"yes", "true", "1", "good_match"}:
        return "match"
    if label in {"no", "false", "0", "bad_match", "not_match"}:
        return "no_match"
    if label in VALID_LABELS:
        return label
    return None


def extract_match_signals(text: str) -> MatchSignals:
    text_l = text.lower()
    return MatchSignals(
        skills=_extract_skills(text_l),
        years=_extract_years(text_l),
        seniority_rank=_extract_seniority_rank(text_l),
        keywords=_extract_keywords(text_l),
    )


def match_candidate_to_role(candidate_profile: str, role_description: str) -> str:
    """Return the discrete eval label: 'match' or 'no_match'."""
    return score_candidate_role_match(candidate_profile, role_description).label


def score_candidate_role_match(candidate_profile: str, role_description: str) -> MatchDecision:
    candidate = extract_match_signals(candidate_profile)
    role = extract_match_signals(role_description)

    if role.skills:
        matched = candidate.skills & role.skills
        skill_coverage = len(matched) / len(role.skills)
    else:
        matched_keywords = candidate.keywords & role.keywords
        matched = set()
        skill_coverage = len(matched_keywords) / len(role.keywords) if role.keywords else 0.0

    years_ok = _years_ok(candidate.years, role.years)
    seniority_ok = _seniority_ok(candidate.seniority_rank, role.seniority_rank)

    score = skill_coverage
    if years_ok:
        score += 0.15
    if seniority_ok:
        score += 0.10
    score = min(score, 1.0)

    label = "match" if skill_coverage >= 0.60 and years_ok and seniority_ok else "no_match"
    missing = role.skills - candidate.skills

    return MatchDecision(
        label=label,
        score=round(score, 4),
        skill_coverage=round(skill_coverage, 4),
        years_ok=years_ok,
        seniority_ok=seniority_ok,
        matched_skills=sorted(matched),
        missing_skills=sorted(missing),
    )


def _extract_skills(text_l: str) -> set[str]:
    skills = set()
    for canonical, aliases in _SKILL_ALIASES.items():
        for alias in aliases:
            if re.search(r"(?<![a-z0-9+#.])" + re.escape(alias) + r"(?![a-z0-9+#.])", text_l):
                skills.add(canonical)
                break
    return skills


def _extract_years(text_l: str) -> int | None:
    patterns = [
        r"(\d+)\+?\s*(?:years|yrs)\s+(?:of\s+)?experience",
        r"(\d+)\+?\s*(?:years|yrs)\s+(?:in|with|building|as)",
        r"minimum\s+(\d+)\+?\s*(?:years|yrs)",
        r"at\s+least\s+(\d+)\+?\s*(?:years|yrs)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text_l)
        if match:
            return int(match.group(1))
    return None


def _extract_seniority_rank(text_l: str) -> int | None:
    for label, rank in sorted(_SENIORITY_RANK.items(), key=lambda item: item[1], reverse=True):
        if re.search(r"\b" + re.escape(label) + r"\b", text_l):
            return rank
    return None


def _extract_keywords(text_l: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9+#.]{2,}", text_l)
    return {word for word in words if word not in _STOPWORDS}


def _years_ok(candidate_years: int | None, role_years: int | None) -> bool:
    if role_years is None:
        return True
    if candidate_years is None:
        return False
    return candidate_years >= max(0, role_years - 1)


def _seniority_ok(candidate_rank: int | None, role_rank: int | None) -> bool:
    if role_rank is None:
        return True
    if candidate_rank is None:
        return False
    return candidate_rank >= max(0, role_rank - 1)
