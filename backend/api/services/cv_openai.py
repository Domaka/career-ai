import json
import os
import urllib.error
import urllib.request
from typing import Any

from .cv_learning import apply_safe_learning_updates

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")

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


class OpenAIReviewError(Exception):
    pass


def run_openai_extraction_review(
    clean_text: str,
    target_role: str | None,
    heuristic_structured: dict[str, Any],
    auto_learn: bool,
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "enabled": False,
            "reason": "OPENAI_API_KEY is not configured",
        }

    llm_structured = _call_openai_json(_build_extraction_prompt(clean_text, target_role), api_key)
    review = _call_openai_json(_build_review_prompt(heuristic_structured, llm_structured), api_key)

    learning_update = {
        "rules_updated": False,
        "applied_updates": {},
        "skipped_updates": [],
    }
    if auto_learn:
        learning_update = apply_safe_learning_updates(review.get("safe_rule_updates"))

    return {
        "enabled": True,
        "provider": "openai",
        "model": os.getenv("OPENAI_MODEL", OPENAI_MODEL),
        "llm_structured_cv": llm_structured,
        "review": review,
        "learning_update": learning_update,
    }


def _call_openai_json(prompt: str, api_key: str) -> dict[str, Any]:
    payload = {
        "model": os.getenv("OPENAI_MODEL", OPENAI_MODEL),
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON with no markdown or extra prose.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    request = urllib.request.Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_build_openai_headers(api_key),
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise OpenAIReviewError(_format_openai_http_error(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise OpenAIReviewError(f"OpenAI connection error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise OpenAIReviewError("OpenAI request timed out") from exc

    text = _extract_response_text(body)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenAIReviewError("OpenAI returned invalid JSON") from exc

    if not isinstance(parsed, dict):
        raise OpenAIReviewError("OpenAI returned non-object JSON")

    return parsed


def _extract_response_text(body: dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise OpenAIReviewError("OpenAI returned no choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OpenAIReviewError("OpenAI returned empty text")

    return content


def _build_openai_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    org_id = os.getenv("OPENAI_ORG_ID")
    project_id = os.getenv("OPENAI_PROJECT_ID")
    if org_id:
        headers["OpenAI-Organization"] = org_id
    if project_id:
        headers["OpenAI-Project"] = project_id

    return headers


def _format_openai_http_error(status_code: int, detail: str) -> str:
    code = None
    message = None
    try:
        parsed = json.loads(detail)
        error_obj = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(error_obj, dict):
            code = error_obj.get("code")
            message = error_obj.get("message")
    except json.JSONDecodeError:
        pass

    if code == "insufficient_quota":
        return (
            "OpenAI API key is valid but the account/project has no usable API quota. "
            "Check billing, credits, and project limits in platform.openai.com."
        )
    if code == "invalid_api_key":
        return "OpenAI API key is invalid for this request."
    if code == "model_not_found":
        return "Configured OPENAI_MODEL is unavailable for this account/project."
    if status_code == 401:
        return "OpenAI authentication failed. Check OPENAI_API_KEY, OPENAI_ORG_ID, and OPENAI_PROJECT_ID."
    if status_code == 429:
        return "OpenAI rate limit or quota exceeded."

    if message:
        return f"OpenAI HTTP error {status_code}: {message}"
    return f"OpenAI HTTP error {status_code}"


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
Output B is OpenAI extraction.

Return strict JSON only using this schema:
{json.dumps(REVIEW_SCHEMA, indent=2)}

Rules:
- Only propose safe rule updates, never source code edits.
- Safe rule updates may include section aliases, technology aliases, leadership verbs, ownership verbs, and metric terms.
- Do not propose anything that would execute code or change control flow.
- Risky changes should be listed under risky_changes.

Heuristic output:
{json.dumps(heuristic_structured, indent=2)}

OpenAI output:
{json.dumps(llm_structured, indent=2)}
""".strip()
