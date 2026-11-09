import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.jira_queries import get_unspecified_severity_bugs, jql_unspecified_severity_bugs
from cephQeInfra.action_items_utils import (
    build_html_table,
    issues_navigator_url,
    extract_target_version,
    get_field_id,
    issue_link_html,
)


class UnspecifiedSeverityCls:
    def get_unspecified_severity_bugs(self, spreadsheet_name=None, config=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if config is None:
            if not spreadsheet_name:
                raise ValueError("spreadsheet_name is required")
            config = load_config(spreadsheet_name)
        spreadsheet_name = config.spreadsheet_name
        target_field_name = config.proposed_version_field
        target_field_id = get_field_id(config, target_field_name)

        issues = get_unspecified_severity_bugs(config)
        severity_field = getattr(config, "severity_field", None)
        severity_field_id = get_field_id(config, severity_field) if severity_field else None
        rows = []
        for issue in issues:
            reporter = getattr(issue.fields, "reporter", None)
            reporter_name = (
                reporter.displayName if reporter and getattr(reporter, "displayName", None) else ""
            )
            components = getattr(issue.fields, "components", []) or []
            component = components[0].name if components else ""
            target_release = extract_target_version(
                issue, target_field_name, target_field_id
            )
            severity_val = ""
            if severity_field_id or severity_field:
                sf = getattr(issue.fields, severity_field_id, None) if severity_field_id else getattr(issue.fields, severity_field, None)
                if sf is not None:
                    severity_val = getattr(sf, "value", None) or getattr(sf, "name", None) or str(sf)
            row = {
                "bug_id": issue.key,
                "bug_link": issue_link_html(issue.key, config.server),
                "summary": getattr(issue.fields, "summary", ""),
                "reporter": reporter_name,
                "component": component,
                "target_release": target_release,
            }
            if severity_field:
                row["severity"] = severity_val
            rows.append(row)

        if not rows:
            return ""

        columns = [
            ("bug_link", "Bug", True),
            ("summary", "Summary", False),
            ("reporter", "Reporter", False),
            ("component", "Component", False),
            ("target_release", "Target Version", False),
        ]
        if severity_field:
            columns.insert(4, ("severity", "Severity", False))
        return build_html_table(
            "Unspecified Severity",
            columns,
            rows,
            title_issues_url=issues_navigator_url(
                config, jql_unspecified_severity_bugs(config)
            ),
        )


if __name__ == "__main__":
    obj = UnspecifiedSeverityCls()
    html_out = obj.get_unspecified_severity_bugs(
        sys.argv[1] if len(sys.argv) > 1 else None
    )
    sys.stdout.write(html_out)
