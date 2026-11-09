"""CLI for action items: prints HTML to stdout and updates Need Info + Doc on QA sheet tabs.

Requires JIRA_TOKEN and a writable Google service account (GSPREAD_SERVICE_ACCOUNT).
"""
import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cephQeInfra.action_items import ActionItemsCls


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Generate Jira action items HTML (stdout). "
            "Also refreshes the Need Info and Doc on QA worksheets in the same run."
        )
    )
    parser.add_argument("spreadsheet_name", help="Target Google Sheet name")
    return parser.parse_args()


def main(spreadsheet_name):
    action_items = ActionItemsCls()
    html = action_items.get_action_items(spreadsheet_name)
    sys.stdout.write(html)


if __name__ == "__main__":
    args = _parse_args()
    main(args.spreadsheet_name)
