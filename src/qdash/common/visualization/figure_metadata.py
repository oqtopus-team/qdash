"""Helpers for figure metadata shared by artifact producers and savers."""

from typing import Any

FIGURE_ROLE_META_KEY = "qdash_figure_role"
ALLOWED_FIGURE_ROLES = {"raw", "marked"}


def set_figure_role(fig: Any, role: str) -> Any:
    """Annotate a Plotly figure with a stable artifact role."""
    meta = getattr(getattr(fig, "layout", None), "meta", None)
    next_meta = dict(meta) if isinstance(meta, dict) else {}
    next_meta[FIGURE_ROLE_META_KEY] = role
    fig.update_layout(meta=next_meta)
    return fig


def figure_role_suffix(fig: Any) -> str:
    """Return a safe filename suffix from figure role metadata."""
    meta = getattr(getattr(fig, "layout", None), "meta", None)
    if not isinstance(meta, dict):
        return ""

    role = meta.get(FIGURE_ROLE_META_KEY)
    if not isinstance(role, str):
        return ""

    normalized = role.strip().lower().replace(" ", "_")
    if normalized in ALLOWED_FIGURE_ROLES:
        return normalized
    return ""
