import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from cephQeInfra.action_items_utils import get_field_id
from lib.gsheets import GoogleSheet
from lib.jira_queries import get_component_distribution_backlog
from lib.metadata_validation import load_metadata

# Sheet column order (Jira severity labels: Critical, Important, Low, Moderate, None).
SEVERITY_COLUMNS = ("Critical", "Important", "Low", "Moderate", "None")


def _normalize_severity(raw):
    """Map Jira Severity field value to one of SEVERITY_COLUMNS (case-insensitive)."""
    if raw is None:
        return "None"
    v = str(raw).strip().lower()
    if not v:
        return "None"
    if v == "none" or "unspec" in v:
        return "None"
    if "critical" in v:
        return "Critical"
    if "important" in v:
        return "Important"
    if "moderate" in v:
        return "Moderate"
    if "low" in v:
        return "Low"
    return "None"


def _severity_from_issue(issue, severity_field_id, severity_field_name):
    if severity_field_id:
        raw = getattr(issue.fields, severity_field_id, None)
    else:
        raw = getattr(issue.fields, severity_field_name, None)
    if raw is None:
        return None
    return getattr(raw, "value", None) or getattr(raw, "name", None) or str(raw)


def _trim_component_name(name):
    """Use Jira component names as-is (no parent/child merging on `/`)."""
    return (name or "").strip()


def _components_from_metadata(metadata):
    raw = metadata.get("components", []) or []
    out = []
    for comp in raw:
        c = _trim_component_name(comp)
        if not c or c.lower().startswith("jira"):
            continue
        if c not in out:
            out.append(c)
    return out


def main(spreadsheet_name):
    config = load_config(spreadsheet_name)
    sheet = GoogleSheet(spreadsheet_name, "Component Distribution")

    headers = [["Component", *SEVERITY_COLUMNS]]
    sheet.batch_update_rows(1, headers)

    metadata = load_metadata()
    meta_components = _components_from_metadata(metadata)

    severity_field_name = (getattr(config, "severity_field", None) or "").strip() or "Severity"
    severity_field_id = get_field_id(config, severity_field_name)

    all_bugs = get_component_distribution_backlog(config)

    seen_on_issues = set()
    for issue in all_bugs:
        for component in getattr(issue.fields, "components", []) or []:
            cn = _trim_component_name(getattr(component, "name", ""))
            if cn and not cn.lower().startswith("jira"):
                seen_on_issues.add(cn)

    meta_set = set(meta_components)
    extras = sorted(c for c in seen_on_issues if c not in meta_set)
    components = meta_components + extras

    counts = {
        comp: {col: 0 for col in SEVERITY_COLUMNS}
        for comp in components
    }

    for issue in all_bugs:
        sev_raw = _severity_from_issue(
            issue, severity_field_id, severity_field_name
        )
        bucket = _normalize_severity(sev_raw)

        issue_components = getattr(issue.fields, "components", []) or []
        for component in issue_components:
            comp_name = _trim_component_name(getattr(component, "name", ""))
            if comp_name in counts:
                counts[comp_name][bucket] += 1

    rows = []
    for comp in components:
        comp_counts = counts.get(comp, {})
        rows.append([comp] + [comp_counts.get(col, 0) for col in SEVERITY_COLUMNS])

    if rows:
        sheet.batch_update_rows(2, rows, start_col=1)
        clear_start = 2 + len(rows)
        num_cols = 1 + len(SEVERITY_COLUMNS)
        sheet.clean_rows(1, clear_start, clear_start + 1000, offsets=list(range(num_cols)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise IndexError("You must provide the spreadsheet name to work with")
    main(sys.argv[1])
