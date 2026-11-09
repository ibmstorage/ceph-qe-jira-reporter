"""Unassigned QE Contact bugs for Action Items mail (all target versions by default)."""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.jira_queries import (
    get_unassigned_qe_contact_bugs as search_unassigned_qe_contact_bugs,
    jql_unassigned_qe_contact_bugs,
)
from cephQeInfra.action_items_utils import (
    build_html_table,
    extract_target_version,
    get_field_id,
    issue_link_html,
    issues_navigator_url,
)
from cephQeInfra.test_on_qa import (
    _jql_clause_field_for_target_version,
    _qe_contact_field_for_jql,
)


class UnassignedQeContactBugsCls:
    def get_unassigned_qe_contact_bugs(self, spreadsheet_name=None, config=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if config is None:
            if not spreadsheet_name:
                raise ValueError("spreadsheet_name is required")
            config = load_config(spreadsheet_name)

        target_field_name = config.proposed_version_field or "Target Version"
        target_field_id = get_field_id(config, target_field_name)
        # Optional: set JIRA_UNASSIGNED_QE_TARGET_VERSION to restrict to one release.
        target_version = os.environ.get("JIRA_UNASSIGNED_QE_TARGET_VERSION", "").strip()
        jql_version_field = (
            _jql_clause_field_for_target_version(config, target_field_name)
            if target_version
            else ""
        )
        qe_jql_field = _qe_contact_field_for_jql(config)
        severity_field = (getattr(config, "severity_field", None) or "").strip() or None
        severity_field_id = (
            get_field_id(config, severity_field) if severity_field else None
        )

        issues = search_unassigned_qe_contact_bugs(
            config, qe_jql_field, jql_version_field, target_version
        )
        rows = []
        for issue in issues:
            reporter = getattr(issue.fields, "reporter", None)
            reporter_name = (
                reporter.displayName
                if reporter and getattr(reporter, "displayName", None)
                else ""
            )
            status = getattr(issue.fields, "status", None)
            status_name = getattr(status, "name", "") if status else ""
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
            versions = getattr(issue.fields, "versions", []) or []
            affected_version = ", ".join(
                [v.name for v in versions if getattr(v, "name", "")]
            )
            fix_versions = getattr(issue.fields, "fixVersions", []) or []
            fix_version = ", ".join([v.name for v in fix_versions if getattr(v, "name", "")])
            target_release = extract_target_version(
                issue, target_field_name, target_field_id
            )
            rows.append(
                {
                    "bug_link": issue_link_html(issue.key, config.server),
                    "summary": getattr(issue.fields, "summary", ""),
                    "reporter": reporter_name,
                    "status": status_name,
                    "component": component,
                    "severity": severity_val,
                    "affected_version": affected_version,
                    "fix_version": fix_version,
                    "target_release": target_release,
                }
            )

        if not rows:
            return ""

        rows.sort(
            key=lambda r: (
                r.get("target_release") or "",
                r.get("status") or "",
                r.get("bug_link") or "",
            )
        )

        title_jql = jql_unassigned_qe_contact_bugs(
            config, qe_jql_field, jql_version_field, target_version
        )
        columns = [
            ("bug_link", "Bug", True),
            ("summary", "Summary", False),
            ("reporter", "Reporter", False),
            ("status", "Status", False),
            ("component", "Component", False),
            ("severity", "Severity", False),
            ("affected_version", "Affected Version", False),
            ("fix_version", "Fix Version", False),
            ("target_release", "Target Version", False),
        ]
        section_title = (
            f"Unassigned QE Contact ({target_version})"
            if target_version
            else "Unassigned QE Contact"
        )
        return build_html_table(
            section_title,
            columns,
            rows,
            title_issues_url=issues_navigator_url(config, title_jql),
        )


if __name__ == "__main__":
    html_out = UnassignedQeContactBugsCls().get_unassigned_qe_contact_bugs(
        sys.argv[1] if len(sys.argv) > 1 else None
    )
    sys.stdout.write(html_out)
