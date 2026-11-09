import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.jira_queries import get_openstack_action_items, jql_openstack_action_items
from cephQeInfra.action_items_utils import (
    build_html_table,
    issues_navigator_url,
    extract_target_version,
    get_field_id,
    issue_link_html,
)


class OpenstackBugsCls:
    def get_openstack_bugs(self, spreadsheet_name=None, config=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if config is None:
            if not spreadsheet_name:
                raise ValueError("spreadsheet_name is required")
            config = load_config(spreadsheet_name)
        spreadsheet_name = config.spreadsheet_name
        target_field_name = config.proposed_version_field
        target_field_id = get_field_id(config, target_field_name)

        issues = get_openstack_action_items(config)
        rows = []
        for issue in issues:
            components = getattr(issue.fields, "components", []) or []
            component = components[0].name if components else ""
            priority = getattr(issue.fields, "priority", None)
            priority_name = getattr(priority, "name", "") if priority else ""
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
            ("priority", "Priority", False),
            ("target_release", "Target Version", False),
        ]
        return build_html_table(
            "OpenStack DP Action Items",
            columns,
            rows,
            title_issues_url=issues_navigator_url(
                config, jql_openstack_action_items(config)
            ),
        )


if __name__ == "__main__":
    obj = OpenstackBugsCls()
    html_out = obj.get_openstack_bugs(sys.argv[1] if len(sys.argv) > 1 else None)
    sys.stdout.write(html_out)
