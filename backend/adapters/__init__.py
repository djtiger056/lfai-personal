from __future__ import annotations

from importlib import import_module
from typing import Any


__all__ = ["ConsoleAdapter", "QQAdapter", "LinyuAdapter"]


def __getattr__(name: str) -> Any:
    if name == "ConsoleAdapter":
        return import_module(".console", __name__).ConsoleAdapter
    if name == "QQAdapter":
        return import_module(".qq", __name__).QQAdapter
    if name == "LinyuAdapter":
        return import_module(".linyu", __name__).LinyuAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
