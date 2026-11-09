import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.gsheets import GoogleSheet
from lib.jira_queries import _exclude_components_clause, _quoted_list, _target_clause, search_issues
from lib.report_utils import (
    get_issue_key,
    get_issue_status_name,
    get_issue_summary,
    iter_status_changes,
    parse_jira_datetime,
)
from lib.team_members import load_qe_team_members


def _build_blocker_jql(config):
    statuses = _quoted_list(
        list(dict.fromkeys(config.open_statuses + [config.qe_status, config.verified_status]))
    )
    blocker_values = _quoted_list(
        list(dict.fromkeys(config.blocker_proposed_values + config.blocker_approved_values))
    )
    clauses = [
        f'project = "{config.jira_project}"',
        'issuetype = "Bug"',
        _target_clause(config),
        _exclude_components_clause(config),
        f"status in {statuses}",
        f'"{config.blocker_field}" in {blocker_values}',
    ]
    return " and ".join([clause for clause in clauses if clause])


def _on_qa_date(issue, qe_status):
    for change_time, status in iter_status_changes(issue):
        if status == qe_status and change_time is not None:
            return change_time
    return None


def _is_qe_reported(issue, members):
    reporter = getattr(issue.fields, "reporter", None)
    if reporter is None:
        return False
    email = getattr(reporter, "emailAddress", "") or ""
    email = email.lower()
    for member in members:
        member_lower = member.lower()
        if email.startswith(member_lower) or email == f"{member_lower}@redhat.com":
            return True
    return False


def main(spreadsheet_name):
    config = load_config(spreadsheet_name)
    sheet = GoogleSheet(spreadsheet_name, "Blocker Resolution Time")

    headers = [
        [
            "Bug ID",
            "Summary",
            "Component",
            "Severity",
            "Creation Date",
            "ON_QA Date",
            "Days to ON_QA",
            "Current Status",
        ]
    ]
    sheet.batch_update_rows(1, headers)
    # Clear all 8 data columns (A–H); default clean_rows offsets would skip C–F
    sheet.clean_rows(1, 2, 1000, offsets=list(range(0, 8)))

    members = load_qe_team_members(spreadsheet_name)
    jql = _build_blocker_jql(config)
    issues = search_issues(config, jql, expand="changelog")

    rows = []
    for issue in issues:
        if not _is_qe_reported(issue, members):
            continue

        created_time = parse_jira_datetime(getattr(issue.fields, "created", None))
        if created_time is None:
            continue

        on_qa_time = _on_qa_date(issue, config.qe_status)
        if on_qa_time is None:
            continue

        days = (on_qa_time - created_time).days
        on_qa_date = on_qa_time.strftime("%Y-%m-%d")
        creation_date = created_time.strftime("%Y-%m-%d")

        key = get_issue_key(issue) or "unknown"
        summary = get_issue_summary(issue) or ""
        components = getattr(issue.fields, "components", []) or []
        component = components[0].name if components else ""
        priority = getattr(issue.fields, "priority", None)
        severity = getattr(priority, "name", "") if priority else ""
        status = get_issue_status_name(issue) or ""

        row = [
            f'=HYPERLINK("{config.server}/browse/{key}", "{key}")',
            summary,
            component,
            severity,
            creation_date,
            on_qa_date,
            days,
            status,
        ]
        rows.append(row)

    if rows:
        sheet.batch_update_rows(2, rows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise IndexError("You must provide the spreadsheet name to work with")
    main(sys.argv[1])
