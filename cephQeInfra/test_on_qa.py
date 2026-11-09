from __future__ import annotations

import html
import os
import sys
from collections import defaultdict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.jira_queries import (
    _exclude_components_clause,
    get_test_on_qa_bugs,
    jql_test_on_qa_matrix_bugs,
)
from lib.jira_user_lookup import resolve_identifier_to_account_id
from lib.team_members import load_qe_team_members
from cephQeInfra.action_items_utils import (
    extract_qe_contact_users,
    extract_target_version,
    get_field_id,
    issues_navigator_url,
)

_LINK_STYLE = ' style="color:#090;text-decoration:underline"'


def _contact_person_display(label: str) -> str:
    """Mail column A often has work email; show username (part before @) in the report."""
    s = (label or "").strip()
    if "@" in s:
        return s.split("@", 1)[0].strip()
    return s


def _escape_jql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _join_jql(clauses):
    return " and ".join(c for c in clauses if c)


def _jql_base_on_qa_parts(config):
    return [
        f'project = "{config.jira_project}"',
        'issuetype = Bug',
        f'status = "{config.qe_status}"',
        _exclude_components_clause(config),
    ]


def _jql_clause_field_for_target_version(config, proposed_field_name: str) -> str:
    """
    Jira Cloud often rejects customfield_… in Issue Navigator JQL for version pickers.
    Use the field label JQL expects, e.g. Target Version[Version Picker (multiple versions)].
    """
    override = (getattr(config, "jql_target_version_field", None) or "").strip()
    if override:
        return override
    name = (proposed_field_name or "").strip()
    if name.lower() == "target version":
        return "Target Version[Version Picker (multiple versions)]"
    return name or "Target Version"


def _qe_contact_field_for_jql(config) -> str:
    override = (getattr(config, "qe_contact_jql_field", None) or "").strip()
    if override:
        return override
    name = (getattr(config, "qe_contact_field", None) or "").strip() or "QE Contact"
    fid = get_field_id(config, name)
    # Jira Cloud Issue Navigator rejects customfield_… in URLs; use JQL autocomplete name.
    if fid and str(fid).startswith("customfield_") and name == "QE Contact":
        return f"{name}[User Picker (single user)]"
    return fid or name


def _version_clause(jql_version_field: str, version_key: str) -> str:
    """JQL clause matching target version OR fixVersion for a given version key."""
    if version_key == "Unspecified":
        return f'"{jql_version_field}" is EMPTY'
    v = _escape_jql_string(version_key)
    return f'("{jql_version_field}" = "{v}" OR fixVersion = "{v}")'


def _on_qa_total_row_jql(config, jql_version_field: str, version_key: str) -> str:
    """ON_QA + target version or fixVersion (all bugs for that release)."""
    parts = list(_jql_base_on_qa_parts(config))
    parts.append(_version_clause(jql_version_field, version_key))
    return _join_jql(parts)


def _on_qa_cell_jql_qe_contact(
    config,
    jql_version_field: str,
    version_key: str,
    qe_jql_field: str,
    qe_contact_account_id: str,
) -> str:
    parts = list(_jql_base_on_qa_parts(config))
    parts.append(_version_clause(jql_version_field, version_key))
    parts.append(
        f'"{_escape_jql_string(qe_jql_field)}" in ("{_escape_jql_string(qe_contact_account_id)}")'
    )
    return _join_jql(parts)


def _on_qa_cell_jql_qe_contact_empty(
    config, jql_version_field: str, version_key: str, qe_jql_field: str
) -> str:
    parts = list(_jql_base_on_qa_parts(config))
    parts.append(_version_clause(jql_version_field, version_key))
    parts.append(f'"{_escape_jql_string(qe_jql_field)}" is EMPTY')
    return _join_jql(parts)


def _build_on_qa_matrix_html(
    title: str,
    columns: list[str],
    contact_rows: list[tuple[str, str | None]],
    keys_by_account: dict[str, dict[str, list[str]]],
    keys_by_display_lower: dict[str, dict[str, list[str]]],
    display_to_account: dict[str, str],
    keys_empty_qe_contact: dict[str, list[str]],
    totals_by_version: dict[str, list[str]],
    config,
    jql_version_field: str,
    qe_jql_field: str,
    title_issues_url: str,
):
    thead = "<th>Contact Person</th>" + "".join(
        f"<th>{html.escape(c)}</th>" for c in columns
    )
    body_rows = []

    total_cells = []
    for col in columns:
        keys = totals_by_version.get(col, [])
        if keys:
            jql = _on_qa_total_row_jql(config, jql_version_field, col)
            url = issues_navigator_url(config, jql)
            total_cells.append(
                f'<td><a href="{html.escape(url)}"{_LINK_STYLE}>{len(keys)}</a></td>'
            )
        else:
            total_cells.append("<td>--</td>")
    body_rows.append(
        "<tr><td><strong>Total</strong></td>" + "".join(total_cells) + "</tr>"
    )

    for label, account_id in contact_rows:
        row_cells = []
        eff_aid = account_id or display_to_account.get(label.strip().lower())
        by_ver = None
        if account_id:
            by_ver = keys_by_account.get(account_id)
        if by_ver is None:
            by_ver = keys_by_display_lower.get(label.strip().lower())
        if by_ver is None:
            by_ver = {}
        if not any(by_ver.get(col, []) for col in columns):
            continue
        display_name = _contact_person_display(label)
        for col in columns:
            keys = by_ver.get(col, [])
            if keys and eff_aid:
                jql = _on_qa_cell_jql_qe_contact(
                    config, jql_version_field, col, qe_jql_field, eff_aid
                )
                url = issues_navigator_url(config, jql)
                row_cells.append(
                    f'<td><a href="{html.escape(url)}"{_LINK_STYLE}>{len(keys)}</a></td>'
                )
            elif keys and not eff_aid:
                row_cells.append(f"<td>{len(keys)}</td>")
            else:
                row_cells.append("<td>--</td>")
        name_td = f"<td>{html.escape(display_name)}</td>"
        body_rows.append("<tr>" + name_td + "".join(row_cells) + "</tr>")

    if any(keys_empty_qe_contact.get(col, []) for col in columns):
        dash_cells = []
        for col in columns:
            keys = keys_empty_qe_contact.get(col, [])
            if keys:
                jql = _on_qa_cell_jql_qe_contact_empty(
                    config, jql_version_field, col, qe_jql_field
                )
                url = issues_navigator_url(config, jql)
                dash_cells.append(
                    f'<td><a href="{html.escape(url)}"{_LINK_STYLE}>{len(keys)}</a></td>'
                )
            else:
                dash_cells.append("<td>--</td>")
        body_rows.append(
            "<tr><td><strong>Unassigned</strong></td>" + "".join(dash_cells) + "</tr>"
        )

    safe_title_url = html.escape(title_issues_url, quote=True)
    return (
        f'<h3><a href="{safe_title_url}"{_LINK_STYLE}>{html.escape(title)}</a></h3>'
        "<table border='1' cellpadding='4' cellspacing='0'>"
        f"<thead><tr>{thead}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )


class TestOnQaCls:
    def get_test_on_qa_bugs(self, spreadsheet_name=None, config=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if config is None:
            if not spreadsheet_name:
                raise ValueError("spreadsheet_name is required")
            config = load_config(spreadsheet_name)
        spreadsheet_name = config.spreadsheet_name
        target_field_name = config.proposed_version_field or "Target Version"
        target_field_id = get_field_id(config, target_field_name)
        jql_version_field = _jql_clause_field_for_target_version(
            config, target_field_name
        )
        qe_jql_field = _qe_contact_field_for_jql(config)
        qe_field_name = (getattr(config, "qe_contact_field", None) or "").strip()
        qe_field_name = qe_field_name or "QE Contact"
        qe_field_id = get_field_id(config, qe_field_name)

        raw_members = load_qe_team_members(spreadsheet_name)
        contact_rows: list[tuple[str, str | None]] = []
        for raw in raw_members:
            label = (raw or "").strip()
            if not label:
                continue
            aid = resolve_identifier_to_account_id(config, label)
            contact_rows.append((label, aid))

        qe_account_ids = {aid for _, aid in contact_rows if aid}
        qe_label_lowers = {label.strip().lower() for label, _ in contact_rows}

        issues = get_test_on_qa_bugs(config)
        if not issues:
            return ""

        keys_by_account: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        keys_by_display_lower: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        display_to_account: dict[str, str] = {}
        keys_empty_qe_contact: dict[str, list[str]] = defaultdict(list)
        totals_by_version: dict[str, list[str]] = defaultdict(list)

        for issue in issues:
            key = issue.key
            target_release = extract_target_version(
                issue, target_field_name, target_field_id
            )
            if not target_release:
                # Fall back to fixVersion if target version is not set
                fix_versions = getattr(issue.fields, "fixVersions", []) or []
                fix_version_names = [v.name for v in fix_versions if getattr(v, "name", "")]
                target_release = ", ".join(fix_version_names) if fix_version_names else "Unspecified"

            totals_by_version[target_release].append(key)

            qe_users = extract_qe_contact_users(issue, qe_field_id)
            if not qe_users:
                keys_empty_qe_contact[target_release].append(key)
                continue

            # One matrix row per bug: first QE Contact user who matches the QE sheet.
            for aid, dn in qe_users:
                if aid and aid in qe_account_ids:
                    keys_by_account[aid][target_release].append(key)
                    break
                dnl = (dn or "").strip().lower()
                if dnl and dnl in qe_label_lowers:
                    keys_by_display_lower[dnl][target_release].append(key)
                    if aid:
                        display_to_account.setdefault(dnl, aid)
                    break
            # Else: orphan — QE Contact set but not on QE sheet; counts only in Total row.

        # Version columns: only releases that have at least one bug (no all-empty columns).
        all_versions = set(totals_by_version.keys())
        rest = sorted(v for v in all_versions if v != "Unspecified")
        columns = rest + (["Unspecified"] if "Unspecified" in all_versions else []) 

        on_qa_title_url = issues_navigator_url(
            config, jql_test_on_qa_matrix_bugs(config)
        )

        return _build_on_qa_matrix_html(
            "On QA list of bugs",
            columns,
            contact_rows,
            dict(keys_by_account),
            dict(keys_by_display_lower),
            display_to_account,
            dict(keys_empty_qe_contact),
            dict(totals_by_version),
            config,
            jql_version_field,
            qe_jql_field,
            on_qa_title_url,
        )


if __name__ == "__main__":
    obj = TestOnQaCls()
    html_out = obj.get_test_on_qa_bugs(sys.argv[1] if len(sys.argv) > 1 else None)
    sys.stdout.write(html_out)
