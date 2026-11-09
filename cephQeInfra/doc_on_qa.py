import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.gsheets import GoogleSheet
from lib.jira_queries import get_doc_on_qa_bugs, jql_doc_on_qa_bugs
from cephQeInfra.action_items_utils import (
    build_html_table,
    issues_navigator_url,
    extract_target_version,
    get_field_id,
    issue_link_formula,
    issue_link_html,
    status_age_days,
)


def _worksheet_candidates():
    return [
        os.environ.get("JIRA_DOC_ON_QA_SHEET_NAME"),
        "Doc Bugs",
        "DocBugs",
    ]


class DocOnQaCls:
    def get_doc_on_qa_bugs(self, spreadsheet_name=None, update_sheet=True, config=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if config is None:
            if not spreadsheet_name:
                raise ValueError("spreadsheet_name is required")
            config = load_config(spreadsheet_name)
        spreadsheet_name = config.spreadsheet_name
        now = datetime.now(timezone.utc)
        target_field_name = config.proposed_version_field
        target_field_id = get_field_id(config, target_field_name)

        issues = get_doc_on_qa_bugs(config)
        rows = []
        for issue in issues:
            priority = getattr(issue.fields, "priority", None)
            priority_name = getattr(priority, "name", "") if priority else ""
            versions = getattr(issue.fields, "versions", []) or []
            affected_version = ", ".join(
                [v.name for v in versions if getattr(v, "name", "")]
            )
            target_release = extract_target_version(
                issue, target_field_name, target_field_id
            )
            age = status_age_days(issue, config.qe_status, now=now)

            rows.append(
                {
                    "bug_id": issue.key,
                    "bug_link": issue_link_html(issue.key, config.server),
                    "summary": getattr(issue.fields, "summary", ""),
                    "priority": priority_name,
                    "version": affected_version,
                    "target_release": target_release,
                    "age": age if age is not None else "",
                }
            )

        if update_sheet:
            sheet = None
            last_error = None
            for sheet_name in [name for name in _worksheet_candidates() if name]:
                try:
                    sheet = GoogleSheet(spreadsheet_name, sheet_name)
                    break
                except Exception as exc:
                    last_error = exc
                    sheet = None
            if sheet is None:
                if last_error:
                    raise last_error
                raise ValueError("No worksheet name available for Doc On QA.")
            sheet.clean_rows(1, 2, 200, offsets=list(range(0, 6)))
            values = []
            for row in rows:
                values.append(
                    [
                        issue_link_formula(row["bug_id"], config.server),
                        row["summary"],
                        row["priority"],
                        row["version"],
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
            ("priority", "Priority", False),
            ("version", "Affects Version", False),
            ("target_release", "Target Version", False),
            ("age", "Age (days)", False),
        ]
        return build_html_table(
            "Doc Bugs On QA",
            columns,
            rows,
            title_issues_url=issues_navigator_url(config, jql_doc_on_qa_bugs(config)),
        )


if __name__ == "__main__":
    obj = DocOnQaCls()
    html = obj.get_doc_on_qa_bugs(sys.argv[1] if len(sys.argv) > 1 else None)
    sys.stdout.write(html)
