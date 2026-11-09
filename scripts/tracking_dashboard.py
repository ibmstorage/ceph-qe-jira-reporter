import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.gsheets import GoogleSheet
from lib.jira_queries import _exclude_components_clause, _quoted_list, _target_clause, search_issues
from lib.report_utils import parse_jira_datetime


HEADERS = [
    "Bug ID",
    "Summary",
    "Status",
    "Component",
    "Severity",
    "Age (days)",
    "Label",
]

CATEGORY_LABELS = {
    "Feature": [
        "BetaBlocker",
        "DevelBlocker",
        "ServiceDeliveryBlocker",
        "DeliveryBlocker",
    ],
    "Stability": [
        "UpgradeBlocker",
        "BuildBlocker",
    ],
    "Test": [
        "AutomationBlocker",
        "TestBlocker",
    ],
}


def _build_jql(config, labels):
    statuses = _quoted_list(config.open_statuses)
    label_clause = f"labels in {_quoted_list(labels)}"
    clauses = [
        f'project = "{config.jira_project}"',
        'issuetype = "Bug"',
        _target_clause(config),
        _exclude_components_clause(config),
        f"status in {statuses}",
        label_clause,
    ]
    return " and ".join([clause for clause in clauses if clause])


def _format_issue_row(config, issue, now, label):
    created_time = parse_jira_datetime(getattr(issue.fields, "created", None))
    age_days = ""
    if created_time is not None:
        age_days = (now - created_time).days

    components = getattr(issue.fields, "components", []) or []
    component = components[0].name if components else ""
    priority = getattr(issue.fields, "priority", None)
    severity = getattr(priority, "name", "") if priority else ""

    summary = (getattr(issue.fields, "summary", "") or "").strip()
    status = (
        issue.fields.status.name if getattr(issue.fields, "status", None) else ""
    ).strip()
    severity = (severity or "").strip()
    if summary and len(summary) > 100:
        summary = summary[:100]

    return [
        f'=HYPERLINK("{config.server}/browse/{issue.key}", "{issue.key}")',
        summary,
        status,
        component,
        severity,
        age_days,
        label,
    ]


def main(spreadsheet_name):
    config = load_config(spreadsheet_name)
    sheet = GoogleSheet(spreadsheet_name, "QE Tracking Dashboard")

    now = datetime.now().astimezone()
    sheet.batch_update_cells([(1, 1, f'Last Updated: {now.strftime("%Y-%m-%d %H:%M")}')])

    rows = [HEADERS]
    for _category, labels in CATEGORY_LABELS.items():
        jql = _build_jql(config, labels)
        issues = search_issues(config, jql)
        for issue in issues:
            issue_labels = getattr(issue.fields, "labels", []) or []
            label = next((value for value in labels if value in issue_labels), "")
            row = _format_issue_row(config, issue, now, label)
            rows.append(row)

    start_row = 2
    if rows:
        sheet.batch_update_rows(start_row, rows, start_col=1)
        clear_start = start_row + len(rows)
        sheet.clean_rows(
            1, clear_start, clear_start + 1000, offsets=[0, 1, 2, 3, 4, 5, 6]
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise IndexError("You must provide the spreadsheet name to work with")
    main(sys.argv[1])
