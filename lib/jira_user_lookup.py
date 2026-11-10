"""Resolve QE sheet entries (emails or Jira Cloud account IDs) to accountId for JQL."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lib.jira_client import get_jira_client

if TYPE_CHECKING:
    from config.settings import JiraConfig

# Jira Cloud accountId values look like 712020:xxxxxxxx-xxxx-...
_ACCOUNT_ID_RE = re.compile(r"^\d+:[0-9a-f-]{36}$", re.I)


def _is_account_id(value: str) -> bool:
    return bool(value and _ACCOUNT_ID_RE.match(value.strip()))


def resolve_identifiers_to_account_ids(config: JiraConfig, identifiers: list[str]) -> list[str]:
    """
    Map each non-empty identifier to a Jira accountId.
    Values that already look like Cloud account IDs are passed through.
    Otherwise the value is treated as an email (or search string) via user/search.
    """
    client = get_jira_client(config)
    url = config.server.rstrip("/") + "/rest/api/3/user/search"
    seen: set[str] = set()
    out: list[str] = []

    for raw in identifiers:
        s = (raw or "").strip()
        if not s:
            continue
        if _is_account_id(s):
            if s not in seen:
                seen.add(s)
                out.append(s)
            continue

        response = client._session.get(url, params={"query": s})
        response.raise_for_status()
        users = response.json()
        match = None
        if "@" in s:
            lower = s.lower()
            for u in users:
                em = (u.get("emailAddress") or "").lower()
                if em == lower:
                    match = u
                    break
        if not match and users:
            match = users[0]
        aid = (match or {}).get("accountId")
        if aid and aid not in seen:
            seen.add(aid)
            out.append(aid)
    return out


def resolve_identifier_to_account_id(config, identifier: str) -> str | None:
    """Resolve a single sheet entry (email, account id, or search string) to accountId, or None."""
    ids = resolve_identifiers_to_account_ids(config, [identifier])
    return ids[0] if ids else None
