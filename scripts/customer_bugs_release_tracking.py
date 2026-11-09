import argparse
import os
import re
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.gsheets import GoogleSheet
from lib.jira_queries import _exclude_components_clause, _quoted_list, search_issues
from lib.report_utils import (
    get_issue_key,
    get_issue_status_name,
    get_issue_summary,
    parse_jira_datetime,
)
from cephQeInfra.action_items_utils import get_field_id, normalize_field_values


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Update customer bugs release tracking Jira report."
    )
    parser.add_argument("spreadsheet_name", help="Target Google Sheet name")
    parser.add_argument(
        "--target-version",
        dest="target_version",
        help="Optional target fixVersion to filter on",
    )
    return parser.parse_args()


def _normalize_version(value):
    if not value:
        return "N/A"
    value = re.sub(r"(\d+)\.\*", r"\1.9", value)
    value = re.sub(r"(\d+)\.(\d+)\.(\d+)", r"\1.\2\3", value)
    return value


def _build_customer_jql(config, target_version=None):
    """JQL for customer bugs. With target_version: matches Cloud (project, issuetype, Target Version, component NOT IN, labels IN)."""
    labels = _quoted_list(config.customer_labels) if config.customer_labels else ""
    clauses = [
        f'project = "{config.jira_project}"',
        'issuetype = "Bug"',
    ]
    if target_version:
        target_field = config.proposed_version_field or "Target Version"
        clauses.append(f'"{target_field}" = "{target_version}"')
    else:
        clauses.append("statusCategory = Done")
    clauses.extend([
        _exclude_components_clause(config),
        f"labels in {labels}" if labels else 'labels ~ "customer"',
    ])
    return " and ".join([c for c in clauses if c])


def _extract_target_version(issue, config, field_id=None):
    """Extract Target Version (or configured field) from issue; use field_id when field name is not an API key."""
    field = config.proposed_version_field or "Target Version"
    if field in {"fixVersion", "Fix Version/s"}:
        fix_versions = getattr(issue.fields, "fixVersions", []) or []
        return ", ".join([v.name for v in fix_versions if getattr(v, "name", "")])
    # Prefer field id (e.g. customfield_10292) so we read the correct custom field from API response
    attr = field_id if field_id else (field if field.startswith("customfield_") else None)
    if attr:
        raw_value = getattr(issue.fields, attr, None)
        values = normalize_field_values(raw_value)
        return ", ".join(values) if values else ""
    raw_value = getattr(issue.fields, field, None)
    if raw_value is not None:
        values = normalize_field_values(raw_value)
        return ", ".join(values) if values else ""
    return ""


def main(spreadsheet_name, target_version=None):
    config = load_config(spreadsheet_name)
    sheet = GoogleSheet(spreadsheet_name, "Customer Bugs Release Tracking")

    headers = [
        [
            "Bug ID",
            "Summary",
            "Component",
            "Creation Date",
            "Reported Version",
            "Target Version",
            "Status",
        ]
    ]
    sheet.batch_update_rows(1, headers)
    # Clear all 7 data columns (A–G) from row 2; default clean_rows offsets would skip C–F
    sheet.clean_rows(1, 2, 1000, offsets=list(range(0, 7)))

    field_name = config.proposed_version_field or "Target Version"
    target_version_field_id = get_field_id(config, field_name)

    effective_target = target_version or config.target_version
    if not effective_target:
        jql = _build_customer_jql(config, target_version=None)
    else:
        jql = _build_customer_jql(config, target_version=effective_target)
    # Target Version is included automatically in search_issues (see jira_queries._ensure_target_version_in_fields)
    issues = search_issues(config, jql)

    rows = []
    for issue in issues:
        created_time = parse_jira_datetime(getattr(issue.fields, "created", None))
        if created_time is None:
            continue

        created_date = created_time.strftime("%Y-%m-%d")

        affects = getattr(issue.fields, "versions", []) or []
        affects_version = ", ".join([v.name for v in affects if getattr(v, "name", "")])
        affects_version = _normalize_version(affects_version) if affects_version else "N/A"

        target_release = _extract_target_version(issue, config, field_id=target_version_field_id)
        target_release = _normalize_version(target_release) if target_release else "N/A"

        status = get_issue_status_name(issue) or ""
        component = ""
        components = getattr(issue.fields, "components", []) or []
        if components:
            component = components[0].name

        summary = get_issue_summary(issue) or ""
        if summary and len(summary) > 100:
            summary = summary[:100]

        key = get_issue_key(issue) or "unknown"
        row = [
            f'=HYPERLINK("{config.server}/browse/{key}", "{key}")',
            summary,
            component,
            created_date,
            affects_version,
            target_release,
            status,
        ]
        rows.append(row)

    if rows:
        sheet.batch_update_rows(2, rows)


if __name__ == "__main__":
    args = _parse_args()
    main(args.spreadsheet_name, target_version=args.target_version)
