"""Minimal password gate for the hosted app.

Set the `APP_PASSWORD` secret (Streamlit Cloud Secrets or env var) and
callers invoke `require_auth()` at the top of the page. If no password
is configured, the gate is disabled and the app runs open — useful
for local development.

Uses hmac.compare_digest for constant-time comparison. Password is not
persisted: only a boolean `authed` flag in st.session_state.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st


def _configured_password() -> str | None:
    try:
        pw = st.secrets.get("APP_PASSWORD")  # type: ignore[attr-defined]
        if pw:
            return str(pw)
    except (FileNotFoundError, KeyError, AttributeError):
        pass
    return os.getenv("APP_PASSWORD")


def require_auth() -> None:
    """Block the script until the correct password is entered.

    No-op if APP_PASSWORD is not set (local dev convenience).
    """
    expected = _configured_password()
    if not expected:
        return  # gate disabled

    if st.session_state.get("authed") is True:
        return

    st.title("Trading Chart Analyzer")
    st.caption("This app is password-protected.")

    with st.form("login", clear_on_submit=True):
        entered = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        if hmac.compare_digest(entered, expected):
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()


def sign_out_button() -> None:
    """Optional sign-out affordance; call from a sidebar."""
    if st.session_state.get("authed") is True and st.button("Sign out"):
        st.session_state.pop("authed", None)
        st.rerun()
