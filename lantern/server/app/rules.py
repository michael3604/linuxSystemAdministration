from __future__ import annotations

from typing import Any, Dict

STATE_NUMERIC = {
    "good": 0,
    "stale": 1,
    "unknown": 1,
    "bad": 2,
    "missing": 2,
    "invalid": 2,
}


def normalize_status(raw: object, config: Dict[str, Any]) -> str:
    text = str(raw or "unknown").strip().lower()
    values = config.get("statusValues", {})
    for state in ("good", "bad", "unknown"):
        if text in {str(x).lower() for x in values.get(state, [])}:
            return state
    if text in STATE_NUMERIC:
        return text
    return "unknown"


def numeric_state(state: str) -> int:
    return STATE_NUMERIC.get(state, 2)


def effective_state(base_state: str, age_seconds: float | None, max_age_seconds: float | None) -> str:
    if base_state in ("bad", "missing", "invalid"):
        return base_state
    if age_seconds is not None and max_age_seconds is not None and age_seconds > max_age_seconds:
        return "stale"
    return base_state


def service_rule(config: Dict[str, Any], host: str, service: str, source_type: str = "serviceJson") -> Dict[str, Any]:
    root_key = "successFiles" if source_type == "successFile" else "services"
    root = config.get(root_key, {})
    rule = dict(root.get("defaults", {}))
    per = root.get("perService", {}).get(host, {}).get(service, {})
    rule.update(per)
    return rule


def host_rule(config: Dict[str, Any], host: str) -> Dict[str, Any]:
    root = config.get("hosts", {})
    rule = dict(root.get("defaults", {}))
    rule.update(root.get("perHost", {}).get(host, {}))
    return rule
