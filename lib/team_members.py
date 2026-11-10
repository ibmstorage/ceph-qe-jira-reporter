import os

from lib.gsheets import GoogleSheet


def _worksheet_candidates():
    return [
        os.environ.get("JIRA_QE_TEAM_SHEET"),
        "QE Team Member",
        "QE Team members",
        "QE_team_member",
    ]


def load_qe_team_members(spreadsheet_name, worksheet_name=None):
    """
    Load QE team members from a worksheet column A (one entry per row).
    Values may be email addresses, display names, or Jira Cloud account IDs (e.g. 712020:uuid).
    """
    candidates = [worksheet_name] if worksheet_name else []
    candidates.extend([name for name in _worksheet_candidates() if name])

    last_error = None
    sheet = None
    for name in candidates:
        try:
            sheet = GoogleSheet(spreadsheet_name, name)
            break
        except Exception as exc:
            last_error = exc
            sheet = None

    if sheet is None:
        if last_error:
            raise last_error
        raise ValueError("No worksheet name provided for QE team members.")

    members = []
    idx = 1
    while True:
        member = sheet.get_cell_value(idx, 1)
        if member:
            members.extend(member.split())
            idx += 1
        else:
            break
    return members
