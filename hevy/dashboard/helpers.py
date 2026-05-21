"""Shared UI helpers for dashboard pages."""

from __future__ import annotations

import streamlit as st
import plotly.express as px

_COLOR_SEQ = px.colors.qualitative.Vivid
_COLOR_MAP = px.colors.qualitative.Prism


def insight(title: str, body: str, icon: str = "💡") -> None:
    """Render a styled insight callout box."""
    st.markdown(
        f"<div style='background:#f0f2f6; padding:16px; border-radius:10px; "
        f"border-left:4px solid #FF6B6B; margin:12px 0;'>"
        f"<strong>{icon} {title}</strong><br>{body}</div>",
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, delta: str | None = None) -> None:
    """Render a metric card."""
    st.metric(label=label, value=value, delta=delta)
