from __future__ import annotations
from uuid import UUID
from typing import Any, Iterable, Optional, Tuple

def _is_guid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except Exception:
        return False

def _normalize_guid(value: Any) -> str:
    if isinstance(value, UUID):
        return str(value)
    # force lowercase
    return str(UUID(str(value)))

def _find_case_insensitive(target: str, items: Iterable[str]) -> Tuple[Optional[Any], Optional[str]]:
        """
        Search `items` case-insensitively and return the original (case-sensitive) match.
        Returns None if not found.

        :param target: Search parameter
        :type target: str
        :param items: Iterable strings
        :type items: Iterable[str]
        :return: The original (case-sensitive) match or None if not found
        :rtype: str | None
        """
        if target is None:
            return None

        target_lower = target.lower()
        if isinstance(items, dict):
            for item_name, item in items.items():
                if isinstance(item_name, str) and item_name.lower() == target_lower:
                    return item, item_name
        else:
            for item in items:
                if isinstance(item, str) and item.lower() == target_lower:
                    return item, None
        return None, None