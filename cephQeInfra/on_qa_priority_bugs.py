"""ON_QA bugs stale >2 weeks with QA Contact on the QE team (action items mail section)."""
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.jira_queries import (
    get_on_qa_priority_bugs as search_on_qa_priority_bugs,
    jql_on_qa_priority_bugs,
)
from lib.jira_user_lookup import resolve_identifiers_to_account_ids
from lib.team_members import load_qe_team_members
from cephQeInfra.action_items_utils import (
    build_html_table,
    extract_qe_contact_users,
    extract_target_version,
    get_field_id,
    issue_link_html,
    issues_navigator_url,
    latest_status_age_days,
)
from cephQeInfra.test_on_qa import _qe_contact_field_for_jql

# More than two weeks in ON_QA (strictly greater than 14 whole days).
ON_QA_STALE_MIN_DAYS = 14


def _qe_contact_names_on_qe_team(issue, qe_field_id, qe_account_ids, qe_label_lowers):
    """Display names for QA Contact users that match the QE team sheet."""
    names = []
    for aid, dn in extract_qe_contact_users(issue, qe_field_id):
        if aid and aid in qe_account_ids:
            names.append((dn or aid).strip())
            continue
        dnl = (dn or "").strip().lower()
        if dnl and dnl in qe_label_lowers:
            names.append((dn or "").strip())
    return ", ".join(n for n in names if n)


class OnQaPriorityBugsCls:
    def get_on_qa_priority_bugs(self, spreadsheet_name=None, config=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if config is None:
            if not spreadsheet_name:
                raise ValueError("spreadsheet_name is required")
            config = load_config(spreadsheet_name)
        spreadsheet_name = config.spreadsheet_name
        now = datetime.now(timezone.utc)

        members = load_qe_team_members(spreadsheet_name)
        qe_account_ids = set(resolve_identifiers_to_account_ids(config, members))
        if not qe_account_ids:
            return ""

        qe_label_lowers = {m.strip().lower() for m in members if (m or "").strip()}

        qe_field_name = (getattr(config, "qe_contact_field", None) or "").strip() or "QE Contact"
        qe_field_id = get_field_id(config, qe_field_name)
        qe_jql_field = _qe_contact_field_for_jql(config)
        target_field_name = config.proposed_version_field
        target_field_id = get_field_id(config, target_field_name)
        severity_field = (getattr(config, "severity_field", None) or "").strip() or None
        severity_field_id = (
            get_field_id(config, severity_field) if severity_field else None
        )

        issues = search_on_qa_priority_bugs(
            config, qe_jql_field, sorted(qe_account_ids)
        )
        rows = []
        qe_status = config.qe_status
        for issue in issues:
            age = latest_status_age_days(issue, qe_status, now=now)
            if age is None or age <= ON_QA_STALE_MIN_DAYS:
                continue
            qe_contact = _qe_contact_names_on_qe_team(
                issue, qe_field_id, qe_account_ids, qe_label_lowers
            )
            if not qe_contact:
                continue

            components = getattr(issue.fields, "components", []) or []
            component = components[0].name if components else ""
            severity_val = ""
            if severity_field_id or severity_field:
                sf = (
                    getattr(issue.fields, severity_field_id, None)
                    if severity_field_id
                    else getattr(issue.fields, severity_field, None)
                )
                if sf is not None:
                    severity_val = (
                        getattr(sf, "value", None)
                        or getattr(sf, "name", None)
                        or str(sf)
                    )
            target_release = extract_target_version(
                issue, target_field_name, target_field_id
            )
            fix_versions = getattr(issue.fields, "fixVersions", []) or []
            fix_version = ", ".join([v.name for v in fix_versions if getattr(v, "name", "")])

            rows.append(
                {
                    "bug_link": issue_link_html(issue.key, config.server),
                    "summary": getattr(issue.fields, "summary", ""),
                    "qe_contact": qe_contact,
                    "component": component,
                    "severity": severity_val,
                    "fix_version": fix_version,
                    "target_release": target_release,
                    "age": age,
                }
            )

        if not rows:
            return ""

        rows.sort(key=lambda r: r.get("age") or 0, reverse=True)

        title_jql = jql_on_qa_priority_bugs(
            config, qe_jql_field, sorted(qe_account_ids), for_navigator=True
        )
        columns = [
            ("bug_link", "Bug", True),
            ("summary", "Summary", False),
            ("qe_contact", "QE Contact", False),
            ("component", "Component", False),
            ("severity", "Severity", False),
            ("fix_version", "Fix Version", False),
            ("target_release", "Target Version", False),
            ("age", "Age (days)", False),
        ]
        return build_html_table(
            "ON_QA Aging Bugs (> 2weeks)",
            columns,
            rows,
            title_issues_url=issues_navigator_url(config, title_jql),
        )


if __name__ == "__main__":
    html_out = OnQaPriorityBugsCls().get_on_qa_priority_bugs(
        sys.argv[1] if len(sys.argv) > 1 else None
    )
    sys.stdout.write(html_out)
