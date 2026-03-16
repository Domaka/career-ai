import json
import re
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).with_name("cv_learning_rules.json")
CANONICAL_SECTIONS = {"summary", "skills", "experience", "projects", "education", "certifications"}
SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9 .+#/\-]{1,60}$")
SAFE_VERB_PATTERN = re.compile(r"^[A-Za-z][A-Za-z\- ]{0,30}$")

DEFAULT_RULES = {
    "section_aliases": {},
    "tech_aliases": {},
    "leadership_verbs": [],
    "ownership_verbs": [],
    "metric_terms": [],
}


def load_learning_rules() -> dict[str, Any]:
    if not RULES_PATH.exists():
        return dict(DEFAULT_RULES)

    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_RULES)

    merged = dict(DEFAULT_RULES)
    for key, value in data.items():
        if key in merged and isinstance(value, type(merged[key])):
            merged[key] = value
    return merged


def apply_safe_learning_updates(proposed_updates: dict[str, Any] | None) -> dict[str, Any]:
    if not proposed_updates:
        return {"rules_updated": False, "applied_updates": {}, "skipped_updates": ["No rule updates proposed"]}

    rules = load_learning_rules()
    applied: dict[str, Any] = {}
    skipped: list[str] = []

    section_aliases = proposed_updates.get("section_aliases")
    if isinstance(section_aliases, dict):
        normalized_aliases: dict[str, list[str]] = {}
        for section, aliases in section_aliases.items():
            if section not in CANONICAL_SECTIONS or not isinstance(aliases, list):
                skipped.append(f"Invalid section alias group: {section}")
                continue

            safe_aliases = []
            for alias in aliases[:10]:
                normalized = _normalize_token(alias)
                if normalized:
                    safe_aliases.append(normalized)
                else:
                    skipped.append(f"Rejected unsafe section alias: {alias}")

            if safe_aliases:
                current = set(rules["section_aliases"].get(section, []))
                merged = sorted(current | set(safe_aliases))
                rules["section_aliases"][section] = merged
                normalized_aliases[section] = merged

        if normalized_aliases:
            applied["section_aliases"] = normalized_aliases

    tech_aliases = proposed_updates.get("tech_aliases")
    if isinstance(tech_aliases, dict):
        normalized_tech_aliases: dict[str, str] = {}
        for source, target in list(tech_aliases.items())[:20]:
            source_token = _normalize_token(source)
            target_token = _normalize_title_token(target)
            if not source_token or not target_token:
                skipped.append(f"Rejected unsafe tech alias: {source} -> {target}")
                continue
            rules["tech_aliases"][source_token] = target_token
            normalized_tech_aliases[source_token] = target_token

        if normalized_tech_aliases:
            applied["tech_aliases"] = normalized_tech_aliases

    for key in ("leadership_verbs", "ownership_verbs", "metric_terms"):
        proposed_list = proposed_updates.get(key)
        if not isinstance(proposed_list, list):
            continue

        validator = SAFE_VERB_PATTERN if key != "metric_terms" else SAFE_TOKEN_PATTERN
        current_values = set(rules.get(key, []))
        accepted_values = []
        for item in proposed_list[:20]:
            normalized = str(item).strip().lower()
            if validator.fullmatch(normalized):
                current_values.add(normalized)
                accepted_values.append(normalized)
            else:
                skipped.append(f"Rejected unsafe {key} value: {item}")

        if accepted_values:
            rules[key] = sorted(current_values)
            applied[key] = sorted(set(accepted_values))

    rules_updated = bool(applied)
    if rules_updated:
        RULES_PATH.write_text(json.dumps(rules, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "rules_updated": rules_updated,
        "applied_updates": applied,
        "skipped_updates": skipped,
    }


def _normalize_token(value: Any) -> str | None:
    token = str(value).strip().lower()
    token = re.sub(r"\s+", " ", token)
    if SAFE_TOKEN_PATTERN.fullmatch(token):
        return token
    return None


def _normalize_title_token(value: Any) -> str | None:
    token = str(value).strip()
    token = re.sub(r"\s+", " ", token)
    if SAFE_TOKEN_PATTERN.fullmatch(token):
        return token
    return None
