import json
import os
import urllib.error
import urllib.request
from typing import Any

from .cv_learning import apply_safe_learning_updates

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

EXTRACTION_SCHEMA = {
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

REVIEW_SCHEMA = {
    "differences_summary": [],
    "heuristic_misses": [],
    "llm_misses": [],
    "improvement_suggestions": [],
    "safe_rule_updates": {
        "section_aliases": {},
        "tech_aliases": {},
        "leadership_verbs": [],
        "ownership_verbs": [],
        "metric_terms": [],
    },
    "risky_changes": [],
}


class GeminiReviewError(Exception):
    pass


def run_gemini_extraction_review(
    clean_text: str,
    target_role: str | None,
    heuristic_structured: dict[str, Any],
    auto_learn: bool,
) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "enabled": False,
            "reason": "GEMINI_API_KEY is not configured",
        }

    llm_structured = _call_gemini_json(_build_extraction_prompt(clean_text, target_role), EXTRACTION_SCHEMA, api_key)
    review = _call_gemini_json(
        _build_review_prompt(heuristic_structured, llm_structured),
        REVIEW_SCHEMA,
        api_key,
    )

    learning_update = {
        "rules_updated": False,
        "applied_updates": {},
        "skipped_updates": [],
    }
    if auto_learn:
        learning_update = apply_safe_learning_updates(review.get("safe_rule_updates"))

    return {
        "enabled": True,
        "provider": "gemini",
        "model": os.getenv("GEMINI_MODEL", GEMINI_MODEL),
        "llm_structured_cv": llm_structured,
        "review": review,
        "learning_update": learning_update,
    }


def _call_gemini_json(prompt: str, schema: dict[str, Any], api_key: str) -> dict[str, Any]:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    request = urllib.request.Request(
        GEMINI_API_URL.format(model=os.getenv("GEMINI_MODEL", GEMINI_MODEL), api_key=api_key),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GeminiReviewError(f"Gemini HTTP error: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise GeminiReviewError(f"Gemini connection error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise GeminiReviewError("Gemini request timed out") from exc

    text = _extract_response_text(body)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiReviewError("Gemini returned invalid JSON") from exc

    if not isinstance(parsed, dict):
        raise GeminiReviewError("Gemini returned non-object JSON")

    return parsed


def _extract_response_text(body: dict[str, Any]) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        raise GeminiReviewError("Gemini returned no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise GeminiReviewError("Gemini returned no text parts")

    text = parts[0].get("text")
    if not isinstance(text, str) or not text.strip():
        raise GeminiReviewError("Gemini returned empty text")
    return text


def _build_extraction_prompt(clean_text: str, target_role: str | None) -> str:
    return f"""
You are an advanced CV intelligence engine.

Read the CV text and return strict JSON only.

Rules:
- Never hallucinate.
- Extract only what is present.
- If uncertain, use null or empty arrays.
- Normalize skill capitalization.
- Deduplicate skills.
- Follow this exact top-level schema:
{json.dumps(EXTRACTION_SCHEMA, indent=2)}

Target role: {target_role or 'null'}

CV text:
{clean_text[:20000]}
""".strip()


def _build_review_prompt(heuristic_structured: dict[str, Any], llm_structured: dict[str, Any]) -> str:
    return f"""
You are reviewing two CV extraction outputs.

Output A is the current heuristic extractor.
Output B is Gemini's extraction.

Return strict JSON only using this schema:
{json.dumps(REVIEW_SCHEMA, indent=2)}

Rules:
- Only propose safe rule updates, never source code edits.
- Safe rule updates may include section aliases, technology aliases, leadership verbs, ownership verbs, and metric terms.
- Do not propose anything that would execute code or change control flow.
- Risky changes should be listed under risky_changes.

Heuristic output:
{json.dumps(heuristic_structured, indent=2)}

Gemini output:
{json.dumps(llm_structured, indent=2)}
""".strip()
