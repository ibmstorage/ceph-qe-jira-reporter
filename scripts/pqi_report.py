import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from cephQeInfra.action_items_utils import issues_navigator_hyperlink_formula
from lib.gsheets import GoogleSheet
from lib.jira_queries import (
    filter_by_status,
    get_dev_backlog,
    get_qe_backlog,
    jql_pqi_dev_status,
    jql_qe_backlog,
)


def main(spreadsheet_name):
    config = load_config(spreadsheet_name)
    sheet = GoogleSheet(spreadsheet_name, "PQI Report")
    now = datetime.today()

    dev_backlog = get_dev_backlog(config)
    new = filter_by_status(dev_backlog, "New")
    assigned = filter_by_status(dev_backlog, "ASSIGNED")
    post = filter_by_status(dev_backlog, "POST")
    modified = filter_by_status(dev_backlog, "MODIFIED")

    qe_backlog = get_qe_backlog(config, expand_changelog=False)
    sheet.insert_row(
        [
            now.strftime("%Y-%m-%d"),
            issues_navigator_hyperlink_formula(
                config, jql_pqi_dev_status(config, "New"), len(new)
            ),
            issues_navigator_hyperlink_formula(
                config, jql_pqi_dev_status(config, "ASSIGNED"), len(assigned)
            ),
            issues_navigator_hyperlink_formula(
                config, jql_pqi_dev_status(config, "POST"), len(post)
            ),
            issues_navigator_hyperlink_formula(
                config, jql_pqi_dev_status(config, "MODIFIED"), len(modified)
            ),
            issues_navigator_hyperlink_formula(
                config, jql_qe_backlog(config), len(qe_backlog)
            ),
        ],
        2,
        "USER_ENTERED",
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise IndexError("You must provide the spreadsheet name to work with")
    main(sys.argv[1])
