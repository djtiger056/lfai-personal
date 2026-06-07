from typing import Any


LEGACY_LINYU_TARGET_FIELDS = {
    "target_user_id",
    "target_user_account",
    "auto_bind_first_user",
}


def sanitize_adapters_config(adapters: Any) -> Any:
    """Remove Linyu target fields now managed by the account registry."""
    if not isinstance(adapters, dict):
        return adapters

    cleaned = dict(adapters)
    linyu = cleaned.get("linyu")
    if isinstance(linyu, dict):
        cleaned_linyu = dict(linyu)
        for field in LEGACY_LINYU_TARGET_FIELDS:
            cleaned_linyu.pop(field, None)
        cleaned["linyu"] = cleaned_linyu
    return cleaned
