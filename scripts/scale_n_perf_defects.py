import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.gsheets import GoogleSheet
from lib.jira_queries import _exclude_components_clause, _quoted_list, search_issues
from lib.report_utils import parse_jira_datetime


HEADERS = ["Bug ID", "Summary", "Status", "Component", "Priority", "Age (days)"]

SCALE_LABELS = ["Scale", "Performance&Scale"]
PERF_LABELS = ["Performance", "Performance&Scale"]
TEST_BLOCKER_LABEL = "TestBlocker"

SCALE_HEADING_ROW = 4
SCALE_HEADERS_ROW = 5
SCALE_START_ROW = 6
SCALE_END_ROW = 19
PERF_HEADING_ROW = 21
PERF_HEADERS_ROW = 22
PERF_START_ROW = 23
PERF_END_ROW = 36


def _build_jql(config, category_labels, component_name=None):
    statuses = _quoted_list(config.open_statuses)
    label_clause = f"labels in {_quoted_list(category_labels)}"
    if component_name:
        label_clause = f"({label_clause} or component = \"{component_name}\")"
    clauses = [
        f'project = "{config.jira_project}"',
        'issuetype = "Bug"',
        _exclude_components_clause(config),
        f"status in {statuses}",
        f'labels in {_quoted_list([TEST_BLOCKER_LABEL])}',
        label_clause,
    ]
    return " and ".join([clause for clause in clauses if clause])


def _format_issue_row(config, issue, now):
    created_time = parse_jira_datetime(getattr(issue.fields, "created", None))
    age_days = ""
    if created_time is not None:
        age_days = (now - created_time).days

    components = getattr(issue.fields, "components", []) or []
    component = components[0].name if components else ""

    priority = getattr(issue.fields, "priority", None)
    priority_name = getattr(priority, "name", "") if priority else ""

    summary = (getattr(issue.fields, "summary", "") or "").strip()
    status = (
        issue.fields.status.name if getattr(issue.fields, "status", None) else ""
    ).strip()
    if summary and len(summary) > 100:
        summary = summary[:100]

    return [
        f'=HYPERLINK("{config.server}/browse/{issue.key}", "{issue.key}")',
        summary,
        status,
        component,
        priority_name,
        age_days,
    ]


def _write_table(sheet, heading_row, headers_row, start_row, end_row, heading, rows):
    sheet.batch_update_cells([(heading_row, 1, heading)])
    sheet.batch_update_rows(headers_row, [HEADERS], start_col=1)
    if rows:
        sheet.batch_update_rows(start_row, rows, start_col=1)
    clear_start = start_row + len(rows)
    if clear_start <= end_row:
        sheet.clean_rows(1, clear_start, end_row, offsets=[0, 1, 2, 3, 4, 5])


def main(spreadsheet_name):
    config = load_config(spreadsheet_name)
    sheet = GoogleSheet(spreadsheet_name, "Performance & Scale Blockers")

    now = datetime.now().astimezone()
    sheet.batch_update_cells(
        [(1, 1, f'Last Updated: {now.strftime("%Y-%m-%d %H:%M")}')]
    )

    scale_jql = _build_jql(config, SCALE_LABELS)
    scale_issues = search_issues(config, scale_jql)
    scale_rows = [_format_issue_row(config, issue, now) for issue in scale_issues]
    _write_table(
        sheet,
        SCALE_HEADING_ROW,
        SCALE_HEADERS_ROW,
        SCALE_START_ROW,
        SCALE_END_ROW,
        "Scale Blockers",
        scale_rows,
    )

    perf_jql = _build_jql(config, PERF_LABELS, component_name="performance")
    perf_issues = search_issues(config, perf_jql)
    perf_rows = [_format_issue_row(config, issue, now) for issue in perf_issues]
    _write_table(
        sheet,
        PERF_HEADING_ROW,
        PERF_HEADERS_ROW,
        PERF_START_ROW,
        PERF_END_ROW,
        "Performance Blockers",
        perf_rows,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise IndexError("You must provide the spreadsheet name to work with")
    main(sys.argv[1])
