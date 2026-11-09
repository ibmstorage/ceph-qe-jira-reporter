import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.jira_queries import get_rbd_action_items, jql_rbd_action_items
from lib.jira_user_lookup import resolve_identifier_to_account_id
from lib.team_members import load_qe_team_members
from cephQeInfra.action_items_utils import (
    build_html_table,
    issues_navigator_url,
    extract_target_version,
    get_field_id,
    issue_link_html,
)


class RbdBugsCls:
    def get_rbd_bugs(self, spreadsheet_name=None, config=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if config is None:
            if not spreadsheet_name:
                raise ValueError("spreadsheet_name is required")
            config = load_config(spreadsheet_name)
        spreadsheet_name = config.spreadsheet_name
        target_field_name = config.proposed_version_field
        target_field_id = get_field_id(config, target_field_name)
        severity_field = getattr(config, "severity_field", None)
        severity_field_id = (
            get_field_id(config, severity_field) if severity_field else None
        )

        raw_members = load_qe_team_members(spreadsheet_name)
        qe_account_ids = set()
        qe_label_lowers = set()
        qe_emails_lower: set[str] = set()
        for raw in raw_members:
            label = (raw or "").strip()
            if not label:
                continue
            qe_label_lowers.add(label.lower())
            if "@" in label:
                qe_emails_lower.add(label.lower())
            aid = resolve_identifier_to_account_id(config, label)
            if aid:
                qe_account_ids.add(aid)

        def _reporter_is_qe(rep) -> bool:
            if not rep:
                return False
            aid = getattr(rep, "accountId", None)
            if aid and aid in qe_account_ids:
                return True
            dn = (getattr(rep, "displayName", None) or "").strip().lower()
            if dn and dn in qe_label_lowers:
                return True
            em = (getattr(rep, "emailAddress", None) or "").strip().lower()
            if em and em in qe_emails_lower:
                return True
            return False

        issues = get_rbd_action_items(config)
        rows = []
        for issue in issues:
            reporter = getattr(issue.fields, "reporter", None)
            if _reporter_is_qe(reporter):
                continue
            components = getattr(issue.fields, "components", []) or []
            component = components[0].name if components else ""
            priority = getattr(issue.fields, "priority", None)
            priority_name = getattr(priority, "name", "") if priority else ""
            reporter_name = (
                reporter.displayName
                if reporter and getattr(reporter, "displayName", None)
                else ""
            )
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
            rows.append(
                {
                    "bug_id": issue.key,
                    "bug_link": issue_link_html(issue.key, config.server),
                    "summary": getattr(issue.fields, "summary", ""),
                    "status": issue.fields.status.name
                    if getattr(issue.fields, "status", None)
                    else "",
                    "component": component,
                    "reporter": reporter_name,
                    "severity": severity_val,
                    "priority": priority_name,
                    "target_release": target_release,
                }
            )

        if not rows:
            return ""

        columns = [
            ("bug_link", "Bug", True),
            ("summary", "Summary", False),
            ("status", "Status", False),
            ("component", "Component", False),
            ("reporter", "Reporter", False),
            ("severity", "Severity", False),
            ("priority", "Priority", False),
            ("target_release", "Target Version", False),
        ]
        title_jql = jql_rbd_action_items(
            config, exclude_reporter_account_ids=sorted(qe_account_ids)
        )
        return build_html_table(
            "RBD Bugs",
            columns,
            rows,
            title_issues_url=issues_navigator_url(config, title_jql),
        )


if __name__ == "__main__":
    obj = RbdBugsCls()
    html_out = obj.get_rbd_bugs(sys.argv[1] if len(sys.argv) > 1 else None)
    sys.stdout.write(html_out)
