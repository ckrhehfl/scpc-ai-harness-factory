from __future__ import annotations

from typing import Any


def rule_guard_warnings(spec: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    rules = spec.get("rules", {})
    for key in ["external_api_allowed", "external_data_allowed", "pretrained_model_allowed", "internet_allowed"]:
        if rules.get(key) == "unknown":
            warnings.append(f"{key} is unknown. Do not enable this path in final config until confirmed.")
    if rules.get("leakage_policy") == "strict":
        warnings.append("Strict leakage policy: do not infer labels from test/eval data, manual labeling, or leaderboard pattern fitting.")
    return warnings
