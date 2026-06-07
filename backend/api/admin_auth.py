"""Compatibility admin auth dependency for the personal edition."""

from __future__ import annotations

from backend.personal_auth import require_personal_auth


require_admin = require_personal_auth
