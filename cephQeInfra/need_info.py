import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.gsheets import GoogleSheet
from lib.jira_queries import get_needinfo_bugs, jql_needinfo_bugs
from cephQeInfra.action_items_utils import (
    build_html_table,
    issues_navigator_url,
    extract_need_info_from_names,
    extract_target_version,
    get_field_id,
    issue_link_formula,
    issue_link_html,
    need_info_from_field_age_days,
    status_age_days_for_statuses,
)


def _need_info_row_tr_attrs(row):
    """Highlight stale Need Info rows in mail HTML (inline style for email clients)."""
    raw = row.get("age")
    if raw is None or raw == "":
        return ""
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return ""
    if days > 5:
        return ' style="background-color:#ffcccc"'
    return ""


class NeedInfoCls:
    def get_need_info_bugs(self, spreadsheet_name=None, update_sheet=True, config=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if config is None:
            if not spreadsheet_name:
                raise ValueError("spreadsheet_name is required")
            config = load_config(spreadsheet_name)
        spreadsheet_name = config.spreadsheet_name
        now = datetime.now(timezone.utc)
        target_field_name = config.proposed_version_field
        target_field_id = get_field_id(config, target_field_name)
        nif_spec = (getattr(config, "need_info_from_field", None) or "").strip()
        if nif_spec.startswith("customfield_"):
            need_info_from_field_id = nif_spec
        elif nif_spec:
            need_info_from_field_id = get_field_id(config, nif_spec)
        else:
            need_info_from_field_id = get_field_id(config, "Need Info From")

        nif_changelog_name = (
            nif_spec
            if nif_spec and not nif_spec.startswith("customfield_")
            else "Need Info From"
        )

        issues = get_needinfo_bugs(config)
        rows = []
        for issue in issues:
            components = getattr(issue.fields, "components", []) or []
            component = components[0].name if components else ""
            priority = getattr(issue.fields, "priority", None)
            priority_name = getattr(priority, "name", "") if priority else ""
            need_info_from = extract_need_info_from_names(issue, need_info_from_field_id)

            versions = getattr(issue.fields, "versions", []) or []
            affected_version = ", ".join(
                [v.name for v in versions if getattr(v, "name", "")]
            )
            fix_versions = getattr(issue.fields, "fixVersions", []) or []
            fix_version = ", ".join([v.name for v in fix_versions if getattr(v, "name", "")])
            target_release = extract_target_version(
                issue, target_field_name, target_field_id
            )
            age = need_info_from_field_age_days(
                issue,
                need_info_from_field_id,
                field_display_name=nif_changelog_name,
                now=now,
            )
            if age is None:
                age = status_age_days_for_statuses(
                    issue, config.needinfo_statuses, now=now
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
                    "priority": priority_name,
                    "need_info_from": need_info_from,
                    "version": affected_version,
                    "fix_version": fix_version,
                    "target_release": target_release,
                    "age": age if age is not None else "",
                }
            )

        if update_sheet:
            sheet_name = os.environ.get("JIRA_NEEDINFO_SHEET_NAME", "Need Info")
            sheet = GoogleSheet(spreadsheet_name, sheet_name)
            sheet.clean_rows(1, 2, 200, offsets=list(range(0, 10)))
            values = []
            for row in rows:
                values.append(
                    [
                        issue_link_formula(row["bug_id"], config.server),
                        row["summary"],
                        row["status"],
                        row["component"],
                        row["priority"],
                        row["need_info_from"],
                        row["version"],
                        row["fix_version"],
                        row["target_release"],
                        row["age"],
                    ]
                )
            sheet.batch_update_rows(2, values, start_col=1)

        if not rows:
            return ""

        columns = [
            ("bug_link", "Bug", True),
            ("summary", "Summary", False),
            ("status", "Status", False),
            ("component", "Component", False),
            ("priority", "Priority", False),
            ("need_info_from", "Need Information from", False),
            ("version", "Affects Version", False),
            ("fix_version", "Fix Version", False),
            ("target_release", "Target Version", False),
            ("age", "Need Info From age (days)", False),
        ]
        return build_html_table(
            "Need Info",
            columns,
            rows,
            row_tr_attrs=_need_info_row_tr_attrs,
            title_issues_url=issues_navigator_url(config, jql_needinfo_bugs(config)),
        )


if __name__ == "__main__":
    obj = NeedInfoCls()
    html = obj.get_need_info_bugs(sys.argv[1] if len(sys.argv) > 1 else None)
    sys.stdout.write(html)
