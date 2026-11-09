from __future__ import annotations

import html
from datetime import datetime, timezone
from urllib.parse import quote

from lib.jira_client import get_jira_client
from lib.report_utils import iter_status_changes, parse_jira_datetime


def get_field_id(config, field_name):
    if not field_name:
        return None
    client = get_jira_client(config)
    url = config.server.rstrip("/") + "/rest/api/3/field"
    response = client._session.get(url)
    response.raise_for_status()
    for field in response.json():
        if field.get("name") == field_name:
            return field.get("id")
    return None


def normalize_field_values(value):
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    normalized = []
    for item in values:
        if isinstance(item, str):
            normalized.append(item)
        else:
            item_value = getattr(item, "value", None)
            item_name = getattr(item, "name", None)
            if item_value:
                normalized.append(item_value)
            elif item_name:
                normalized.append(item_name)
    return normalized


def extract_need_info_from_names(issue, field_id):
    """Comma-separated displayName values for a multi-user picker (customfield_…)."""
    if not field_id:
        return ""
    raw = getattr(issue.fields, field_id, None)
    if raw is None:
        return ""
    items = raw if isinstance(raw, list) else [raw]
    names = []
    for item in items:
        if isinstance(item, str):
            if item.strip():
                names.append(item.strip())
            continue
        dn = getattr(item, "displayName", None) or getattr(item, "display_name", None)
        if dn:
            names.append(dn)
    return ", ".join(names)


def extract_qe_contact_users(issue, field_id):
    """
    Users from QE Contact (single or multi user picker). Each entry is
    (account_id_or_none, display_name_or_empty). Empty list if field unset.
    """
    if not field_id:
        return []
    raw = getattr(issue.fields, field_id, None)
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out = []
    for item in items:
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append((None, s))
            continue
        aid = getattr(item, "accountId", None) or getattr(item, "account_id", None)
        dn = (
            getattr(item, "displayName", None)
            or getattr(item, "display_name", None)
            or ""
        )
        if aid or (isinstance(dn, str) and dn.strip()):
            out.append((aid, (dn or "").strip()))
    return out


def extract_target_version(issue, field_name, field_id):
    if not field_name:
        return ""
    if field_name in {"fixVersion", "Fix Version/s"}:
        fix_versions = getattr(issue.fields, "fixVersions", []) or []
        return ", ".join([v.name for v in fix_versions if getattr(v, "name", "")])
    if field_id:
        raw_value = getattr(issue.fields, field_id, None)
        values = normalize_field_values(raw_value)
        return ", ".join(values)
    return ""


def issue_link_html(issue_key, server):
    safe_key = html.escape(issue_key)
    safe_url = html.escape(server.rstrip("/") + f"/browse/{issue_key}")
    return f'<a href="{safe_url}">{safe_key}</a>'


def issue_link_formula(issue_key, server):
    safe_url = server.rstrip("/") + f"/browse/{issue_key}"
    return f'=HYPERLINK("{safe_url}", "{issue_key}")'


# Match cephQeInfra/test_on_qa.py and last_24_hour_bugs mail heading links
_ACTION_ITEM_TITLE_LINK_STYLE = ' style="color:#090;text-decoration:underline"'


def issues_navigator_url(config, jql: str) -> str:
    """Jira Issue Navigator URL for the given JQL (same pattern as Test on QA cell links)."""
    return f'{config.server.rstrip("/")}/issues/?jql={quote(jql)}'


def issues_navigator_hyperlink_formula(config, jql: str, display_label) -> str:
    """Google Sheets =HYPERLINK(...) opening Issue Navigator; display_label is usually the count."""
    url = issues_navigator_url(config, jql)
    safe_url = url.replace('"', '""')
    safe_label = str(display_label).replace('"', '""')
    return f'=HYPERLINK("{safe_url}","{safe_label}")'


def status_age_days(issue, status_name, now=None):
    """Days since the first status transition to ``status_name`` in changelog order (legacy)."""
    now = now or datetime.now(timezone.utc)
    for changed_at, to_status in iter_status_changes(issue):
        if to_status == status_name:
            if changed_at is None:
                return None
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            return (now - changed_at).days
    return None


def latest_status_age_days(issue, status_name, now=None):
    """Days since the most recent transition to ``status_name`` (current stint in that status)."""
    now = now or datetime.now(timezone.utc)
    latest = None
    for changed_at, to_status in iter_status_changes(issue):
        if to_status != status_name or changed_at is None:
            continue
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        if latest is None or changed_at > latest:
            latest = changed_at
    if latest is None:
        return None
    return (now - latest).days


def status_age_days_for_statuses(issue, statuses, now=None):
    now = now or datetime.now(timezone.utc)
    status_set = set(statuses or [])
    for changed_at, to_status in iter_status_changes(issue):
        if to_status in status_set:
            if changed_at is None:
                return None
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            return (now - changed_at).days
    return None


def _changelog_item_to_string(item):
    return (
        getattr(item, "toString", None)
        or getattr(item, "to", None)
        or ""
    )


def _changelog_item_matches_field(item, field_id: str | None, field_display_name: str) -> bool:
    fld = getattr(item, "field", None) or ""
    fid = getattr(item, "fieldId", None) or ""
    if field_id and (fld == field_id or fid == field_id):
        return True
    if field_display_name and fld == field_display_name:
        return True
    return False


def need_info_from_field_age_days(
    issue,
    field_id: str | None,
    field_display_name: str = "Need Info From",
    now=None,
):
    """
    Days since the Need Info From field was last updated to a non-empty value (from changelog).
    Returns None if no matching history exists.
    """
    now = now or datetime.now(timezone.utc)
    changelog = getattr(issue, "changelog", None)
    if not changelog:
        return None
    histories = getattr(changelog, "histories", None) or []
    latest = None
    for history in histories:
        created = parse_jira_datetime(getattr(history, "created", None))
        if created is None:
            continue
        for item in getattr(history, "items", None) or []:
            if not _changelog_item_matches_field(item, field_id, field_display_name):
                continue
            to_val = _changelog_item_to_string(item)
            if not str(to_val).strip():
                continue
            if latest is None or created > latest:
                latest = created
    if latest is None:
        return None
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return (now - latest).days


def build_html_table(title, columns, rows, row_tr_attrs=None, title_issues_url=None):
    """
    row_tr_attrs: optional callable(row_dict) -> str with leading space + HTML attributes
    for each cell in the row (e.g. ' style="background-color:#ffcccc"'). Applied per <td>
    so mail clients (Outlook/Gmail) still show row shading.

    title_issues_url: when set, the section heading links to Jira Issue Navigator with that URL.
    """
    if title_issues_url:
        safe_url = html.escape(title_issues_url, quote=True)
        heading = (
            f'<h3><a href="{safe_url}"{_ACTION_ITEM_TITLE_LINK_STYLE}>'
            f"{html.escape(title)}</a></h3>"
        )
    else:
        heading = f"<h3>{html.escape(title)}</h3>"
    header = "".join([f"<th>{html.escape(label)}</th>" for _, label, _ in columns])
    body_rows = []
    for row in rows:
        td_extra = row_tr_attrs(row) if row_tr_attrs else ""
        if td_extra is None:
            td_extra = ""
        cells = []
        for key, _, is_html in columns:
            value = row.get(key, "")
            if value is None:
                value = ""
            if is_html:
                cells.append(f"<td{td_extra}>{value}</td>")
            else:
                cells.append(f"<td{td_extra}>{html.escape(str(value))}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    table = (
        heading
        + "<table border='1' cellpadding='4' cellspacing='0'>"
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )
    return table
