import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.gsheets import GoogleSheet
from lib.jira_queries import get_overall_backlog


def main(spreadsheet_name):
    config = load_config(spreadsheet_name)
    sheet = GoogleSheet(spreadsheet_name, "Average Quality Score")

    headers = [["Date", "Quality Score"]]
    sheet.batch_update_rows(1, headers)

    now = datetime.today()
    all_bugs = get_overall_backlog(config)
    row = [now.strftime("%Y-%m-%d"), len(all_bugs)]
    sheet.insert_row(row, 2, "USER_ENTERED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise IndexError("You must provide the spreadsheet name to work with")
    main(sys.argv[1])
