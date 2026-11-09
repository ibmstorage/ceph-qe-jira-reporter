"""Action items HTML for the QE mail.

A single call to ``ActionItemsCls.get_action_items()`` (from ``scripts/action_items.py``)
does everything in one process:

1. Loads Jira config from the dashboard spreadsheet.
2. Refreshes Google Sheet tabs that support it — **Need Info** and **Doc on QA**
   (see ``cephQeInfra.need_info`` and ``cephQeInfra.doc_on_qa`` with ``update_sheet=True``).
3. Returns HTML for the other sections (Test on QA matrix, etc. are HTML-only). Sections with no matching issues return no HTML so the mail omits empty tables.

There is **no** separate Jenkins job or script only for updating Sheets: the same run that
writes HTML to stdout also updates those tabs, as long as ``GSPREAD_SERVICE_ACCOUNT``
points at a credential that can edit the spreadsheet (see ``pipeline/jira-action-items.groovy``).
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from cephQeInfra.need_info import NeedInfoCls
from cephQeInfra.doc_on_qa import DocOnQaCls
from cephQeInfra.test_on_qa import TestOnQaCls
from cephQeInfra.on_qa_priority_bugs import OnQaPriorityBugsCls
from cephQeInfra.unassigned_qe_contact_bugs import UnassignedQeContactBugsCls
from cephQeInfra.unspecified_severity import UnspecifiedSeverityCls
from cephQeInfra.rbd_bugs import RbdBugsCls
from cephQeInfra.openstack_dp_bugs import OpenstackBugsCls


class ActionItemsCls:
    def get_action_items(self, spreadsheet_name=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if not spreadsheet_name:
            raise ValueError("spreadsheet_name is required")
        config = load_config(spreadsheet_name)
        sections = [
            NeedInfoCls().get_need_info_bugs(
                spreadsheet_name=config.spreadsheet_name,
                update_sheet=True,
                config=config,
            ),
            DocOnQaCls().get_doc_on_qa_bugs(
                spreadsheet_name=config.spreadsheet_name,
                update_sheet=True,
                config=config,
            ),
            TestOnQaCls().get_test_on_qa_bugs(config=config),
            OnQaPriorityBugsCls().get_on_qa_priority_bugs(config=config),
            UnassignedQeContactBugsCls().get_unassigned_qe_contact_bugs(config=config),
            UnspecifiedSeverityCls().get_unspecified_severity_bugs(config=config),
            RbdBugsCls().get_rbd_bugs(config=config),
            OpenstackBugsCls().get_openstack_bugs(config=config),
        ]
        non_empty = [s for s in sections if (s or "").strip()]
        content = "\n<br/>\n".join(non_empty) if non_empty else "<p>No action items for this run.</p>"
        return f"<html><body>{content}</body></html>"


if __name__ == "__main__":
    obj = ActionItemsCls()
    html_out = obj.get_action_items(sys.argv[1] if len(sys.argv) > 1 else None)
    sys.stdout.write(html_out)
