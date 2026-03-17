import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from .cv_openai import OpenAIReviewError, run_openai_extraction_review
from .cv_learning import load_learning_rules

MAX_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx"}

SECTION_ALIASES = {
    "experience": ["professional experience", "work experience", "career history", "experience"],
    "projects": ["projects", "portfolio", "personal projects"],
    "skills": ["skills", "technical skills", "core competencies"],
    "education": ["education", "academic background"],
    "certifications": ["certifications", "training"],
    "summary": ["summary", "professional summary", "profile"],
}

SKILL_BUCKETS = {
    "frameworks": {"django", "flask", "fastapi", "react", "next.js", "express", "spring", "laravel", "drf"},
    "databases": {"postgresql", "postgres", "mysql", "sqlite", "mongodb", "redis", "sql server", "oracle"},
    "devops": {"docker", "kubernetes", "aws", "azure", "gcp", "terraform", "github actions", "ci/cd", "jenkins"},
    "tools": {"git", "jira", "postman", "figma", "linux", "vscode", "notion", "slack"},
    "technical": {"python", "javascript", "typescript", "java", "c#", "c++", "go", "rust", "sql", "html", "css"},
}

SOFT_SKILL_KEYWORDS = {
    "communication",
    "collaboration",
    "leadership",
    "problem solving",
    "adaptability",
    "mentoring",
    "time management",
    "ownership",
}

TECH_ALIASES = {
    "js": "JavaScript",
    "ts": "TypeScript",
    "node": "Node.js",
    "postgresql": "Postgres",
    "django rest framework": "DRF",
    "ci cd": "CI/CD",
}


class CVExtractionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class CVEngineResult:
    raw_text: str
    clean_text: str
    page_count: int | None
    structured_cv: dict[str, Any]
    derived_metrics: dict[str, Any]
    llm_structured_cv: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    extraction_mode: str = "heuristic"


def extract_cv_intelligence(
    cv_file: Any,
    target_role: str | None = None,
    use_llm: bool = True,
    auto_learn: bool = True,
) -> CVEngineResult:
    _validate_file(cv_file)
    extension = _get_extension(cv_file.name)
    raw_text, page_count = _extract_raw_text(cv_file, extension)

    if not raw_text.strip():
        raise CVExtractionError("Empty extraction output", status_code=422)

    clean_text = _clean_text(raw_text)
    sections = _detect_sections(clean_text)
    structured = _build_structured_output(clean_text, sections, target_role)
    structured = _normalize_output(structured)
    metrics = _derive_metrics(structured)

    llm_structured = None
    comparison = _default_comparison()
    extraction_mode = "heuristic"

    if use_llm:
        try:
            llm_review = run_openai_extraction_review(clean_text, target_role, structured, auto_learn)
            if llm_review.get("enabled"):
                llm_structured = _normalize_output(llm_review.get("llm_structured_cv") or {})
                comparison = _compare_extraction_outputs(
                    structured,
                    llm_structured,
                    llm_review.get("review") or {},
                    llm_review.get("provider", "openai"),
                    llm_review.get("model", "unknown"),
                    llm_review.get("learning_update") or {},
                )
                extraction_mode = "heuristic_with_openai_review"
            else:
                comparison = {
                    **_default_comparison(),
                    "llm_available": False,
                    "fallback_reason": llm_review.get("reason", "OpenAI review unavailable"),
                }
        except OpenAIReviewError as exc:
            comparison = {
                **_default_comparison(),
                "llm_available": False,
                "fallback_reason": str(exc),
            }

    return CVEngineResult(
        raw_text=raw_text,
        clean_text=clean_text,
        page_count=page_count,
        structured_cv=structured,
        derived_metrics=metrics,
        llm_structured_cv=llm_structured,
        comparison=comparison,
        extraction_mode=extraction_mode,
    )


def _validate_file(cv_file: Any) -> None:
    extension = _get_extension(cv_file.name)
    if extension not in ALLOWED_EXTENSIONS:
        raise CVExtractionError("Unsupported format. Only PDF and DOCX are allowed.", status_code=400)

    if cv_file.size > MAX_FILE_SIZE:
        raise CVExtractionError("File too large. Maximum size is 5MB.", status_code=400)


def _get_extension(name: str) -> str:
    dot_index = name.rfind(".")
    return name[dot_index:].lower() if dot_index >= 0 else ""


def _extract_raw_text(cv_file: Any, extension: str) -> tuple[str, int | None]:
    if extension == ".pdf":
        return _extract_pdf_text(cv_file)
    if extension == ".docx":
        return _extract_docx_text(cv_file)
    raise CVExtractionError("Unsupported format", status_code=400)


def _extract_pdf_text(cv_file: Any) -> tuple[str, int | None]:
    payload = cv_file.read()
    cv_file.seek(0)

    try:
        import pdfplumber  # type: ignore

        text_parts = []
        extracted_links: list[str] = []
        with pdfplumber.open(io.BytesIO(payload)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
                extracted_links.extend(_extract_pdfplumber_page_links(page))

            return _append_links_to_text("\n".join(text_parts), extracted_links), len(pdf.pages)
    except ImportError:
        pass
    except Exception as exc:  # pragma: no cover - depends on file content
        raise CVExtractionError(f"Corrupt PDF file: {exc}", status_code=400) from exc

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(payload))
        text_parts = [page.extract_text() or "" for page in reader.pages]
        extracted_links = _extract_pypdf_links(reader)
        return _append_links_to_text("\n".join(text_parts), extracted_links), len(reader.pages)
    except ImportError as exc:
        raise CVExtractionError(
            "PDF extraction dependencies missing. Install pdfplumber or pypdf.", status_code=500
        ) from exc
    except Exception as exc:  # pragma: no cover - depends on file content
        raise CVExtractionError(f"Corrupt PDF file: {exc}", status_code=400) from exc


def _extract_docx_text(cv_file: Any) -> tuple[str, int | None]:
    payload = cv_file.read()
    cv_file.seek(0)

    try:
        from docx import Document  # type: ignore
        from docx.opc.constants import RELATIONSHIP_TYPE as RT  # type: ignore

        document = Document(io.BytesIO(payload))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        links = []
        for rel in document.part.rels.values():
            if rel.reltype == RT.HYPERLINK and rel.target_ref:
                links.append(rel.target_ref.strip())

        return _append_links_to_text(text, links), None
    except ImportError as exc:
        raise CVExtractionError("DOCX extraction dependency missing. Install python-docx.", status_code=500) from exc
    except Exception as exc:  # pragma: no cover - depends on file content
        raise CVExtractionError(f"Corrupt DOCX file: {exc}", status_code=400) from exc


def _clean_text(text: str) -> str:
    normalized = text.replace("\u2022", "-")
    normalized = re.sub(r"\r\n?", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    return normalized.strip()


def _detect_sections(clean_text: str) -> dict[str, str]:
    lines = [line.strip() for line in clean_text.split("\n")]
    sections: dict[str, list[str]] = {}
    current_key = "_unclassified"
    sections[current_key] = []

    alias_lookup = {}
    learned_aliases = load_learning_rules().get("section_aliases", {})
    for key, aliases in SECTION_ALIASES.items():
        merged_aliases = list(aliases) + list(learned_aliases.get(key, []))
        for alias in merged_aliases:
            alias_lookup[alias] = key

    for line in lines:
        if not line:
            sections.setdefault(current_key, []).append("")
            continue

        candidate = line.lower().rstrip(":")
        if candidate in alias_lookup:
            current_key = alias_lookup[candidate]
            sections.setdefault(current_key, [])
            continue

        sections.setdefault(current_key, []).append(line)

    return {key: "\n".join(value).strip() for key, value in sections.items() if "\n".join(value).strip()}


def _build_structured_output(clean_text: str, sections: dict[str, str], target_role: str | None) -> dict[str, Any]:
    skills = _extract_skills(sections.get("skills", ""))
    experience = _extract_experience(sections.get("experience", ""), skills)
    projects = _extract_projects(sections.get("projects", ""), skills, clean_text)
    education = _extract_education(sections.get("education", ""))
    certifications = _extract_certifications(sections.get("certifications", ""))

    summary = sections.get("summary") or clean_text.split("\n\n", 1)[0][:500]
    core_strengths = _build_core_strengths(skills, experience, projects)
    potential_weaknesses = _build_potential_weaknesses(experience, projects)
    personality_indicators = _build_personality_indicators(clean_text, experience)
    career_level = _estimate_career_level(experience)
    trajectory = _career_trajectory(career_level, experience, target_role)
    cv_weaknesses = _build_cv_weaknesses(experience, projects)
    missing_signals = _build_missing_signals(skills, experience, projects)
    possible_missed = _possible_missed_information(clean_text, skills, experience)
    extractor_insights = _extractor_learning_insights(clean_text, sections)
    confidence = _confidence_score(sections, skills, experience, projects, education)

    return {
        "summary": summary,
        "skills": skills,
        "experience": experience,
        "projects": projects,
        "education": education,
        "certifications": certifications,
        "career_level_estimate": career_level,
        "core_strengths": core_strengths,
        "potential_weaknesses": potential_weaknesses,
        "personality_indicators": personality_indicators,
        "career_trajectory_analysis": trajectory,
        "cv_weaknesses": cv_weaknesses,
        "missing_signals": missing_signals,
        "possible_missed_information": possible_missed,
        "extractor_learning_insights": extractor_insights,
        "confidence_score": confidence,
    }


def _extract_skills(skills_text: str) -> dict[str, list[str]]:
    tokens = _tokenize_list(skills_text)
    soft = []
    categorized = {
        "technical": [],
        "frameworks": [],
        "databases": [],
        "devops": [],
        "tools": [],
        "soft_skills": [],
    }

    for token in tokens:
        normalized = _normalize_skill(token)
        lower = normalized.lower()

        if lower in SOFT_SKILL_KEYWORDS:
            soft.append(_title_case_skill(normalized))
            continue

        matched = False
        for bucket, options in SKILL_BUCKETS.items():
            if lower in options:
                categorized[bucket].append(_title_case_skill(normalized))
                matched = True
                break

        if not matched and normalized:
            categorized["technical"].append(_title_case_skill(normalized))

    categorized["soft_skills"] = soft
    for key in categorized:
        categorized[key] = sorted(set(categorized[key]))

    return categorized


def _extract_experience(experience_text: str, skills: dict[str, list[str]]) -> list[dict[str, Any]]:
    if not experience_text.strip():
        return []

    blocks = [b.strip() for b in re.split(r"\n\s*\n", experience_text) if b.strip()]
    known_tech = {skill.lower() for group in skills.values() for skill in group}
    learning_rules = load_learning_rules()
    leadership_pattern = _signal_pattern(
        ["led", "managed", "mentored", "supervised", "head"] + learning_rules.get("leadership_verbs", [])
    )
    ownership_pattern = _signal_pattern(
        ["owned", "ownership", "end-to-end", "spearheaded", "drove"] + learning_rules.get("ownership_verbs", [])
    )

    entries = []
    for block in blocks:
        lines = [line.strip("- ") for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        headline = lines[0]
        company, role = _split_company_role(headline)
        start_date, end_date = _extract_date_range(block)
        duration = _duration_in_months(start_date, end_date)

        responsibilities = [line for line in lines[1:] if not _looks_like_metric(line)][:6]
        achievements = [line for line in lines if _looks_like_metric(line)][:6]

        technologies_used = []
        for line in lines:
            line_lower = line.lower()
            for skill in known_tech:
                if skill and skill in line_lower:
                    technologies_used.append(_title_case_skill(skill))

        leadership = [line for line in lines if leadership_pattern.search(line)]
        ownership = [line for line in lines if ownership_pattern.search(line)]
        impact = [line for line in lines if _looks_like_metric(line)]

        entries.append(
            {
                "company": company,
                "role": role,
                "start_date": start_date,
                "end_date": end_date,
                "duration_months": duration,
                "key_responsibilities": responsibilities,
                "achievements": achievements,
                "technologies_used": sorted(set(technologies_used)),
                "leadership_indicators": leadership,
                "ownership_signals": ownership,
                "impact_signals": impact,
            }
        )

    return entries


def _extract_projects(projects_text: str, skills: dict[str, list[str]], clean_text: str) -> list[dict[str, Any]]:
    if not projects_text.strip():
        return []

    blocks = [b.strip() for b in re.split(r"\n\s*\n", projects_text) if b.strip()]
    known_tech = {skill.lower() for group in skills.values() for skill in group}
    global_github_links = re.findall(r"https?://github\.com/[^\s)]+", clean_text, flags=re.I)
    projects = []

    for block in blocks:
        lines = [line.strip("- ") for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        title = lines[0]
        description = " ".join(lines[1:]) if len(lines) > 1 else None

        technologies = []
        for line in lines:
            lower_line = line.lower()
            for skill in known_tech:
                if skill and skill in lower_line:
                    technologies.append(_title_case_skill(skill))

        metrics = [line for line in lines if _looks_like_metric(line)]
        github_links = re.findall(r"https?://github\.com/[^\s)]+", block, flags=re.I)

        relevance = "unknown"
        if github_links or metrics:
            relevance = "high"
        elif technologies:
            relevance = "medium"
        elif description:
            relevance = "low"

        projects.append(
            {
                "title": title,
                "description": description,
                "technologies_used": sorted(set(technologies)),
                "metrics": metrics,
                "github_links": github_links or global_github_links[:3],
                "portfolio_relevance": relevance,
            }
        )

    return projects


def _extract_education(education_text: str) -> list[dict[str, Any]]:
    if not education_text.strip():
        return []

    blocks = [b.strip() for b in re.split(r"\n\s*\n", education_text) if b.strip()]
    items = []
    for block in blocks:
        lines = [line.strip("- ") for line in block.split("\n") if line.strip()]
        full = " ".join(lines)
        years = [int(match) for match in re.findall(r"\b(19\d{2}|20\d{2})\b", full)]

        degree = None
        if re.search(r"\b(bachelor|b\.?sc|ba)\b", full, re.I):
            degree = "Bachelor"
        elif re.search(r"\b(master|m\.?sc|mba)\b", full, re.I):
            degree = "Master"
        elif re.search(r"\b(phd|doctorate)\b", full, re.I):
            degree = "PhD"

        field = None
        field_match = re.search(r"in\s+([A-Za-z &/-]+)", full)
        if field_match:
            field = field_match.group(1).strip()

        institution = lines[0] if lines else None

        items.append(
            {
                "institution": institution,
                "degree": degree,
                "field_of_study": field,
                "start_year": years[0] if len(years) >= 1 else None,
                "end_year": years[-1] if len(years) >= 2 else None,
                "academic_level": degree,
            }
        )

    return items


def _extract_certifications(certifications_text: str) -> list[str]:
    if not certifications_text.strip():
        return []
    return sorted(set(_tokenize_list(certifications_text)))


def _build_core_strengths(skills: dict[str, list[str]], experience: list[dict[str, Any]], projects: list[dict[str, Any]]) -> list[str]:
    strengths = []
    technical_count = len(skills.get("technical", [])) + len(skills.get("frameworks", []))
    if technical_count >= 6:
        strengths.append("Breadth of technical stack")
    if any(item.get("impact_signals") for item in experience):
        strengths.append("Evidence of measurable impact")
    if any(item.get("github_links") for item in projects):
        strengths.append("Portfolio evidence linked to GitHub")
    if any(item.get("leadership_indicators") for item in experience):
        strengths.append("Leadership exposure in delivery")
    return strengths


def _build_potential_weaknesses(experience: list[dict[str, Any]], projects: list[dict[str, Any]]) -> list[str]:
    weaknesses = []
    if experience and not any(item.get("impact_signals") for item in experience):
        weaknesses.append("Limited quantified outcomes in experience")
    if projects and not any(item.get("metrics") for item in projects):
        weaknesses.append("Projects lack measurable outcomes")
    if not projects:
        weaknesses.append("Limited project evidence")
    return weaknesses


def _build_personality_indicators(clean_text: str, experience: list[dict[str, Any]]) -> list[str]:
    indicators = []
    text = clean_text.lower()

    if re.search(r"\b(analyze|optimized|investigated|debugged)\b", text):
        indicators.append("analytical")
    if re.search(r"\b(collaborat|cross-functional|team)\b", text):
        indicators.append("collaborative")
    if any(item.get("leadership_indicators") for item in experience):
        indicators.append("leadership oriented")
    if re.search(r"\b(initiated|self-driven|independently|owned)\b", text):
        indicators.append("self driven")
    if re.search(r"\b(designed|created|built)\b", text):
        indicators.append("creative")
    if re.search(r"\b(process|framework|structured|methodology)\b", text):
        indicators.append("structured thinker")
    if re.search(r"\b(research|experiment|prototype)\b", text):
        indicators.append("research oriented")

    return sorted(set(indicators))


def _estimate_career_level(experience: list[dict[str, Any]]) -> str:
    total_months = 0
    leadership_count = 0
    for item in experience:
        total_months += item.get("duration_months") or 0
        leadership_count += len(item.get("leadership_indicators") or [])

    years = total_months / 12 if total_months else 0
    if years >= 7 or (years >= 5 and leadership_count >= 2):
        return "senior"
    if years >= 2:
        return "mid"
    if years > 0:
        return "junior"
    return "unknown"


def _career_trajectory(level: str, experience: list[dict[str, Any]], target_role: str | None) -> str:
    role_count = len([item for item in experience if item.get("role")])
    target = f" Target role focus: {target_role}." if target_role else ""

    if level == "unknown":
        return f"Career trajectory is unclear due to limited dated experience signals.{target}".strip()

    return (
        f"Candidate shows a {level} trajectory across {role_count} role entries, with evidence of evolving responsibilities "
        f"and technical maturity based on extracted experience signals.{target}"
    ).strip()


def _build_cv_weaknesses(experience: list[dict[str, Any]], projects: list[dict[str, Any]]) -> list[str]:
    weaknesses = []
    if experience and not any(item.get("impact_signals") for item in experience):
        weaknesses.append("Lack of quantified achievements in experience bullets")
    if projects and not any(item.get("github_links") for item in projects):
        weaknesses.append("Missing project links for verification")
    if projects and any(not item.get("technologies_used") for item in projects):
        weaknesses.append("Unclear technology usage in some project descriptions")
    if not experience:
        weaknesses.append("Work experience section missing or not clearly structured")
    return weaknesses


def _build_missing_signals(skills: dict[str, list[str]], experience: list[dict[str, Any]], projects: list[dict[str, Any]]) -> list[str]:
    missing = []
    if not any(item.get("github_links") for item in projects):
        missing.append("No GitHub links")
    if not any(item.get("metrics") for item in projects) and not any(item.get("impact_signals") for item in experience):
        missing.append("No measurable impact signals")
    if not projects:
        missing.append("No project evidence")
    if len(skills.get("frameworks", [])) == 0 and len(skills.get("databases", [])) == 0:
        missing.append("Unclear technical specialization")
    if not any(item.get("leadership_indicators") for item in experience):
        missing.append("No leadership evidence")
    return missing


def _possible_missed_information(clean_text: str, skills: dict[str, list[str]], experience: list[dict[str, Any]]) -> list[str]:
    notes = []
    if len(clean_text) > 2500 and not skills.get("tools"):
        notes.append("Potential tools hidden in narrative paragraphs")
    if experience and not any(item.get("technologies_used") for item in experience):
        notes.append("Technologies may be embedded in achievements rather than explicit lists")
    if any(item.get("achievements") for item in experience) and not any(item.get("leadership_indicators") for item in experience):
        notes.append("Leadership indicators may be implied in achievement statements")
    return notes


def _extractor_learning_insights(clean_text: str, sections: dict[str, str]) -> list[str]:
    insights = []
    if "skills" not in sections:
        insights.append("Many CVs embed skill signals inside experience bullets rather than a dedicated skills section")
    if re.search(r"\b(improved|increased|reduced|grew)\b[^\n]*\d+%", clean_text, re.I):
        insights.append("Metrics are often expressed as percentage improvements in achievement bullets")
    if re.search(r"https?://github\.com/", clean_text, re.I):
        insights.append("Project credibility signals often appear as inline GitHub URLs")
    insights.append("Leadership signals frequently use verbs like led, mentored, managed, and owned")
    return sorted(set(insights))


def _confidence_score(
    sections: dict[str, str],
    skills: dict[str, list[str]],
    experience: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    education: list[dict[str, Any]],
) -> int:
    score = 35
    score += 10 if "skills" in sections else 0
    score += 10 if "experience" in sections else 0
    score += 8 if "projects" in sections else 0
    score += 7 if "education" in sections else 0
    score += min(10, len([s for group in skills.values() for s in group]))
    score += 8 if any(item.get("duration_months") for item in experience) else 0
    score += 6 if any(item.get("metrics") for item in projects) else 0
    score += 6 if education else 0

    if not sections:
        score = 10

    return max(0, min(100, score))


def _normalize_output(payload: dict[str, Any]) -> dict[str, Any]:
    required = {
        "summary": "",
        "skills": {
            "technical": [],
            "frameworks": [],
            "databases": [],
            "devops": [],
            "tools": [],
            "soft_skills": [],
        },
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
        "career_level_estimate": "unknown",
        "core_strengths": [],
        "potential_weaknesses": [],
        "personality_indicators": [],
        "career_trajectory_analysis": "",
        "cv_weaknesses": [],
        "missing_signals": [],
        "possible_missed_information": [],
        "extractor_learning_insights": [],
        "confidence_score": 0,
    }

    normalized = {**required, **payload}

    for skill_bucket in required["skills"]:
        values = normalized["skills"].get(skill_bucket, [])
        normalized["skills"][skill_bucket] = sorted(set(_title_case_skill(v) for v in values if v))

    normalized["confidence_score"] = max(0, min(100, int(normalized.get("confidence_score", 0))))
    if normalized["career_level_estimate"] not in {"junior", "mid", "senior", "unknown"}:
        normalized["career_level_estimate"] = "unknown"

    return normalized


def _derive_metrics(structured: dict[str, Any]) -> dict[str, Any]:
    experience = structured.get("experience", [])
    projects = structured.get("projects", [])
    skill_groups = structured.get("skills", {})

    total_experience_months = sum(item.get("duration_months") or 0 for item in experience)
    unique_skills = {skill for values in skill_groups.values() for skill in values}
    leadership_signal_count = sum(len(item.get("leadership_indicators") or []) for item in experience)
    projects_with_metrics = sum(1 for item in projects if item.get("metrics"))

    return {
        "total_experience_months": total_experience_months,
        "total_projects": len(projects),
        "projects_with_metrics": projects_with_metrics,
        "unique_skill_count": len(unique_skills),
        "leadership_signal_count": leadership_signal_count,
    }


def _tokenize_list(raw: str) -> list[str]:
    if not raw.strip():
        return []

    tokens = re.split(r"[,|/\n;]", raw)
    cleaned = []
    for token in tokens:
        value = token.strip(" -:\t")
        if not value:
            continue
        cleaned.append(value)
    return cleaned


def _normalize_skill(skill: str) -> str:
    key = skill.strip().lower()
    key = re.sub(r"\s+", " ", key)
    learned_aliases = load_learning_rules().get("tech_aliases", {})
    return learned_aliases.get(key, TECH_ALIASES.get(key, key))


def _title_case_skill(skill: str) -> str:
    if skill.upper() in {"SQL", "AWS", "GCP", "DRF", "CI/CD"}:
        return skill.upper()
    if skill.lower() == "node.js":
        return "Node.js"
    if skill.lower() == "javascript":
        return "JavaScript"
    if skill.lower() == "typescript":
        return "TypeScript"
    if skill.lower() == "postgres":
        return "Postgres"
    return skill.title()


def _split_company_role(headline: str) -> tuple[str | None, str | None]:
    separators = [" - ", " | ", " @ ", " at "]
    for sep in separators:
        if sep in headline:
            left, right = headline.split(sep, 1)
            if sep == " at ":
                return right.strip() or None, left.strip() or None
            return right.strip() or None, left.strip() or None
    return None, headline.strip() or None


def _extract_date_range(text: str) -> tuple[str | None, str | None]:
    match = re.search(
        r"(\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}|\b\d{4})\s*[-to]+\s*(present|current|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}|\b\d{4})",
        text,
        re.I,
    )
    if not match:
        return None, None

    start = match.group(1)
    end = match.group(2)
    if re.match(r"present|current", end, re.I):
        end = "present"
    return start, end


def _duration_in_months(start_date: str | None, end_date: str | None) -> int | None:
    if not start_date or not end_date:
        return None

    start = _parse_date_token(start_date)
    end = date.today() if end_date == "present" else _parse_date_token(end_date)

    if not start or not end:
        return None

    return max(0, (end.year - start.year) * 12 + (end.month - start.month))


def _parse_date_token(token: str) -> date | None:
    token = token.strip().lower()
    month_map = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", token)
    if not year_match:
        return None
    year = int(year_match.group(1))

    month = 1
    for short, value in month_map.items():
        if token.startswith(short):
            month = value
            break

    return date(year=year, month=month, day=1)


def _looks_like_metric(line: str) -> bool:
    learning_rules = load_learning_rules()
    learned_metric_terms = learning_rules.get("metric_terms", [])
    base_match = bool(re.search(r"(\d+%|\$\d+|\b\d+\b\s*(users|clients|days|weeks|months|years|x))", line, re.I))
    term_match = any(term in line.lower() for term in learned_metric_terms)
    return base_match or term_match


def _append_links_to_text(text: str, links: list[str]) -> str:
    cleaned_links = sorted({link.strip() for link in links if link and link.strip()})
    if not cleaned_links:
        return text
    return f"{text}\n\nExtracted Links\n" + "\n".join(cleaned_links)


def _extract_pdfplumber_page_links(page: Any) -> list[str]:
    links = []
    hyperlink_items = getattr(page, "hyperlinks", None) or []
    for item in hyperlink_items:
        if isinstance(item, dict):
            uri = item.get("uri") or item.get("URI")
            if isinstance(uri, str) and uri.strip():
                links.append(uri.strip())
    return links


def _extract_pypdf_links(reader: Any) -> list[str]:
    links: list[str] = []
    for page in reader.pages:
        annotations = page.get("/Annots") or []
        for annotation in annotations:
            try:
                obj = annotation.get_object()
                action = obj.get("/A")
                if action and action.get("/URI"):
                    links.append(str(action.get("/URI")).strip())
            except Exception:
                continue
    return links


def _signal_pattern(terms: list[str]) -> re.Pattern[str]:
    escaped = [re.escape(term) for term in sorted(set(terms)) if term]
    return re.compile(rf"\b({'|'.join(escaped)})\b", re.I)


def _default_comparison() -> dict[str, Any]:
    return {
        "llm_available": False,
        "provider": None,
        "model": None,
        "differences_summary": [],
        "heuristic_misses": [],
        "llm_misses": [],
        "improvement_suggestions": [],
        "risky_changes": [],
        "learning_update": {
            "rules_updated": False,
            "applied_updates": {},
            "skipped_updates": [],
        },
        "field_differences": {},
        "fallback_reason": None,
    }


def _compare_extraction_outputs(
    heuristic_structured: dict[str, Any],
    llm_structured: dict[str, Any],
    review: dict[str, Any],
    provider: str,
    model: str,
    learning_update: dict[str, Any],
) -> dict[str, Any]:
    heuristic_skills = _flatten_skills(heuristic_structured.get("skills", {}))
    llm_skills = _flatten_skills(llm_structured.get("skills", {}))

    field_differences = {
        "skills_only_in_heuristic": sorted(heuristic_skills - llm_skills),
        "skills_only_in_llm": sorted(llm_skills - heuristic_skills),
        "experience_count_delta": len(llm_structured.get("experience", [])) - len(heuristic_structured.get("experience", [])),
        "project_count_delta": len(llm_structured.get("projects", [])) - len(heuristic_structured.get("projects", [])),
        "confidence_score_delta": int(llm_structured.get("confidence_score", 0)) - int(heuristic_structured.get("confidence_score", 0)),
    }

    return {
        "llm_available": True,
        "provider": provider,
        "model": model,
        "differences_summary": review.get("differences_summary", []),
        "heuristic_misses": review.get("heuristic_misses", []),
        "llm_misses": review.get("llm_misses", []),
        "improvement_suggestions": review.get("improvement_suggestions", []),
        "risky_changes": review.get("risky_changes", []),
        "learning_update": learning_update,
        "field_differences": field_differences,
        "fallback_reason": None,
    }


def _flatten_skills(skills: dict[str, list[str]]) -> set[str]:
    return {skill for entries in skills.values() for skill in entries}
