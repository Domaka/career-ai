from typing import Any

from .cv_gemini import GeminiReviewError, run_gemini_profile_analysis


REQUIRED_ANALYSIS_KEYS = {
    "summary",
    "strengths",
    "weaknesses",
    "talent_gaps",
    "general_recommendations",
}


def build_profile_analysis(
    structured_cv: dict[str, Any],
    derived_metrics: dict[str, Any],
    target_role: str | None,
    use_llm: bool = True,
) -> dict[str, Any]:
    rules_analysis = _build_rules_analysis(structured_cv, derived_metrics, target_role)

    if not use_llm:
        return {
            "analysis": rules_analysis,
            "source": "rules",
            "fallback_reason": "AI analysis disabled by request",
        }

    try:
        llm_result = run_gemini_profile_analysis(structured_cv, derived_metrics, target_role)
    except GeminiReviewError as exc:
        return {
            "analysis": rules_analysis,
            "source": "rules",
            "fallback_reason": str(exc),
        }

    if not llm_result.get("enabled"):
        return {
            "analysis": rules_analysis,
            "source": "rules",
            "fallback_reason": llm_result.get("reason", "Gemini analysis unavailable"),
        }

    llm_analysis = llm_result.get("analysis") or {}
    if not _valid_analysis_payload(llm_analysis):
        return {
            "analysis": rules_analysis,
            "source": "rules",
            "fallback_reason": "Gemini returned invalid analysis shape",
        }

    normalized_llm = _normalize_analysis_payload(llm_analysis)
    return {
        "analysis": normalized_llm,
        "source": "gemini",
        "fallback_reason": "",
    }


def _build_rules_analysis(
    structured_cv: dict[str, Any],
    derived_metrics: dict[str, Any],
    target_role: str | None,
) -> dict[str, Any]:
    strengths = list(structured_cv.get("core_strengths") or [])
    weaknesses = list(structured_cv.get("potential_weaknesses") or [])
    missing_signals = list(structured_cv.get("missing_signals") or [])

    skill_groups = structured_cv.get("skills", {})
    unique_skills = sorted({skill for group in skill_groups.values() for skill in group})

    if derived_metrics.get("projects_with_metrics", 0) > 0 and "Evidence of measurable outcomes" not in strengths:
        strengths.append("Evidence of measurable outcomes")

    if derived_metrics.get("leadership_signal_count", 0) == 0 and "Limited leadership evidence" not in weaknesses:
        weaknesses.append("Limited leadership evidence")

    if derived_metrics.get("unique_skill_count", 0) < 6 and "Technical depth appears limited" not in weaknesses:
        weaknesses.append("Technical depth appears limited")

    talent_gaps = []
    for signal in missing_signals:
        if signal not in talent_gaps:
            talent_gaps.append(signal)

    if not talent_gaps and target_role:
        talent_gaps.append(f"No major gaps detected for target role: {target_role}")

    summary = structured_cv.get("summary") or "CV processed and baseline profile generated."
    summary = (
        f"{summary} Candidate appears {structured_cv.get('career_level_estimate', 'unknown')} level with "
        f"{derived_metrics.get('unique_skill_count', 0)} unique detected skills."
    )

    recommendations = _build_general_recommendations(weaknesses, talent_gaps)

    return {
        "summary": summary,
        "strengths": sorted(set(strengths)),
        "weaknesses": sorted(set(weaknesses)),
        "talent_gaps": sorted(set(talent_gaps)),
        "general_recommendations": recommendations,
        "detected_skills": unique_skills,
    }


def _build_general_recommendations(weaknesses: list[str], talent_gaps: list[str]) -> list[str]:
    recommendations = []
    if any("metrics" in entry.lower() for entry in weaknesses + talent_gaps):
        recommendations.append("Add quantified impact metrics to work and project bullets")
    if any("github" in entry.lower() for entry in weaknesses + talent_gaps):
        recommendations.append("Include GitHub links for major projects to improve proof-of-work")
    if any("leadership" in entry.lower() for entry in weaknesses + talent_gaps):
        recommendations.append("Highlight mentoring, ownership, or team leadership experiences")

    if not recommendations:
        recommendations.append("Maintain momentum by shipping consistent portfolio updates")

    return recommendations


def _valid_analysis_payload(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    return REQUIRED_ANALYSIS_KEYS.issubset(payload.keys())


def _normalize_analysis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": str(payload.get("summary", "")).strip(),
        "strengths": _to_str_list(payload.get("strengths")),
        "weaknesses": _to_str_list(payload.get("weaknesses")),
        "talent_gaps": _to_str_list(payload.get("talent_gaps")),
        "general_recommendations": _to_str_list(payload.get("general_recommendations")),
    }


def _to_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
