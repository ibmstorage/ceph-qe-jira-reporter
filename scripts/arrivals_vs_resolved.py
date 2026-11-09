import argparse
import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from cephQeInfra.action_items_utils import issues_navigator_hyperlink_formula
from lib.gsheets import GoogleSheet
from lib.jira_queries import (
    get_new_arrivals,
    get_new_blockers_by_priority,
    get_resolved_bugs,
    get_verified_bugs,
    jql_new_arrivals,
    jql_new_blockers_by_priority,
    jql_resolved_bugs,
    jql_verified_bugs,
)
from lib.metadata_validation import load_metadata, validate_config


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Update arrivals vs resolved Jira report."
    )
    parser.add_argument("spreadsheet_name", help="Target Google Sheet name")
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip Jira metadata validation before running",
    )
    return parser.parse_args()


def _should_skip_validation(flag_value):
    if flag_value:
        return True
    return os.environ.get("JIRA_SKIP_METADATA_VALIDATION", "").lower() in {
        "1",
        "true",
        "yes",
    }


def main(spreadsheet_name, skip_validation=False):
    config = load_config(spreadsheet_name)
    if not _should_skip_validation(skip_validation):
        metadata = load_metadata()
        validate_config(config, metadata, strict=True)
    sheet = GoogleSheet(spreadsheet_name, "Arrivals Vs Resolved")

    now = datetime.today()
    day_end = now

    # Use Jira relative startOfDay(-1d) so counts match Cloud (from start of yesterday until now)
    new_bugs = get_new_arrivals(
        config,
        changed_from="startOfDay(-1d)",
        changed_to="",
    )
    resolved_bugs = get_resolved_bugs(
        config,
        changed_from="startOfDay(-1d)",
        changed_to="",
    )
    verified_bugs = get_verified_bugs(
        config,
        changed_from="startOfDay(-1d)",
        changed_to="",
    )
    blocker_bugs = get_new_blockers_by_priority(
        config,
        changed_from="startOfDay(-1d)",
        changed_to="",
    )

    _from = "startOfDay(-1d)"
    _to = ""
    values = [
        day_end.strftime("%Y-%m-%d"),
        issues_navigator_hyperlink_formula(
            config, jql_new_arrivals(config, _from, _to), len(new_bugs)
        ),
        issues_navigator_hyperlink_formula(
            config, jql_resolved_bugs(config, _from, _to), len(resolved_bugs)
        ),
        issues_navigator_hyperlink_formula(
            config, jql_verified_bugs(config, _from, _to), len(verified_bugs)
        ),
        issues_navigator_hyperlink_formula(
            config, jql_new_blockers_by_priority(config, _from, _to), len(blocker_bugs)
        ),
    ]
    sheet.insert_row(values, 2, "USER_ENTERED")


if __name__ == "__main__":
    args = _parse_args()
    main(args.spreadsheet_name, skip_validation=args.skip_validation)
