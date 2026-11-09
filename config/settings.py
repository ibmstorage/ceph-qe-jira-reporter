import os
from dataclasses import dataclass

import yaml

from lib.gsheets import GoogleSheet


@dataclass
class JiraConfig:
    spreadsheet_name: str
    version: str
    jira_project: str
    target_version: str
    affected_version: str
    affected_version_field: str
    proposed_version_field: str
    jql_target_version_field: str  # optional JQL clause name for target/proposed version links (not customfield id)
    approved_version_field: str
    approved_version: str  # value from I7 (e.g. 9.1), same role as target_version from G7
    server: str
    email: str
    token: str
    open_statuses: list
    qe_status: str
    verified_status: str
    blocker_field: str
    blocker_approved_values: list
    blocker_proposed_values: list
    blocker_rejected_values: list  # optional; when set, excluded from open-blocker / blocker-arrival queries
    regression_label: str
    customer_labels: list
    documentation_component: str
    documentation_components: list  # when set, overrides single documentation_component for JQL in/not in
    exclude_components: list  # e.g. ["Jira_Change_Requests", "Jira_Issues"]; excluded from all report queries
    severity_field: str  # e.g. "Severity"; when set, Unspecified Severity report filters by this field
    # JQL fragment for that field when customfield_… breaks Issue Navigator links (e.g. Severity[Dropdown])
    severity_jql_field: str
    unspecified_severity_values: list  # when severity_field set, treat these as unspecified (empty = only EMPTY)
    done_resolutions: list
    max_results: int
    needinfo_statuses: list
    need_info_from_field: str  # Jira field for "Need Info From" (name or customfield_ id); empty = no user filter
    # JQL name for that field when customfield_… breaks Issue Navigator (env: JIRA_NEED_INFO_JQL_FIELD)
    need_info_jql_field: str
    unspecified_priorities: list
    rbd_components: list
    rbd_labels: list
    openstack_components: list
    openstack_labels: list
    # On QA matrix: group by QE Contact (user picker); JQL override for Cloud navigator
    qe_contact_field: str
    qe_contact_jql_field: str


def _load_metadata_config():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    metadata_path = os.environ.get(
        "JIRA_METADATA_PATH", os.path.join(repo_root, "metadata.json")
    )
    if not os.path.exists(metadata_path):
        return {}
    with open(metadata_path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {}
    return data


def load_config(spreadsheet_name):
    sheet = GoogleSheet(spreadsheet_name, "Dashboard Configuration")

    version = sheet.get_cell_value(7, 6)
    jira_project = sheet.get_cell_value(7, 4)
    affected_version_field = sheet.get_cell_value(6, 6)
    affected_version = sheet.get_cell_value(7, 6)
    proposed_version_field = sheet.get_cell_value(6, 7)
    target_version = sheet.get_cell_value(7, 7)
    approved_version_field = (sheet.get_cell_value(6, 9) or "").strip()
    approved_version = (sheet.get_cell_value(7, 9) or "").strip()

    metadata_cfg = _load_metadata_config()
    if not affected_version_field:
        affected_version_field = os.environ.get(
            "JIRA_AFFECTED_VERSION_FIELD", "affectedVersion"
        )
    if affected_version_field in {"Affects versions", "Affects Version/s"}:
        affected_version_field = "affectedVersion"
    if not proposed_version_field:
        proposed_version_field = os.environ.get(
            "JIRA_PROPOSED_VERSION_FIELD", "Target Version"
        )
    if proposed_version_field in {"Target Release", "Target Release/s"}:
        proposed_version_field = "Target Version"
    if proposed_version_field in {"Fix Version", "Fix Version/s"}:
        proposed_version_field = "fixVersion"
    if not approved_version_field:
        approved_version_field = os.environ.get(
            "JIRA_APPROVED_VERSION_FIELD", "Target Version"
        )
    if approved_version_field in {"Target Release", "Target Release/s"}:
        approved_version_field = "Target Version"
    if approved_version_field in {"Fix Version", "Fix Version/s"}:
        approved_version_field = "fixVersion"
    if not approved_version:
        approved_version = (
            os.environ.get("JIRA_APPROVED_VERSION", "").strip()
            or (target_version or "").strip()
        )

    server = sheet.get_cell_value(7, 5)
    email = (
        sheet.get_cell_value(7, 8)
        or os.environ.get("JIRA_EMAIL")
        or metadata_cfg.get("jira_email")
        or ""
    )
    token = os.environ.get("JIRA_TOKEN", "")

    open_statuses = _split_csv(
        os.environ.get("JIRA_OPEN_STATUSES", "New,ASSIGNED,POST,MODIFIED")
    )
    qe_status = os.environ.get("JIRA_QE_STATUS", "ON_QA")
    verified_status = os.environ.get("JIRA_VERIFIED_STATUS", "Verified")
    blocker_field = os.environ.get("JIRA_BLOCKER_FIELD", "Release Blocker")
    blocker_approved_values = _split_csv(
        os.environ.get("JIRA_BLOCKER_APPROVED_VALUES", "Approved")
    )
    blocker_proposed_values = _split_csv(
        os.environ.get("JIRA_BLOCKER_PROPOSED_VALUES", "Proposed")
    )
    _rejected_raw = os.environ.get("JIRA_BLOCKER_REJECTED_VALUES", "Rejected")
    blocker_rejected_values = _split_csv(_rejected_raw) if _rejected_raw else []
    regression_label = os.environ.get("JIRA_REGRESSION_LABEL", "Regression")
    customer_labels = _split_csv(
        os.environ.get(
            "JIRA_CUSTOMER_LABELS", "IBM_Customer_Issue,RH_Customer_Issue"
        )
    )
    documentation_component = os.environ.get(
        "JIRA_DOCUMENTATION_COMPONENT", "documentation"
    )
    _doc_components_raw = os.environ.get("JIRA_DOCUMENTATION_COMPONENTS", "")
    documentation_components = _split_csv(_doc_components_raw) if _doc_components_raw else []
    exclude_components = _split_csv(
        os.environ.get("JIRA_EXCLUDE_COMPONENTS", "Jira_Change_Requests,Jira_Issues")
    )
    severity_field = os.environ.get("JIRA_SEVERITY_FIELD", "Severity")
    severity_jql_field = os.environ.get("JIRA_SEVERITY_JQL_FIELD", "").strip()
    _unspec_sev_raw = os.environ.get("JIRA_UNSPECIFIED_SEVERITY_VALUES", "")
    unspecified_severity_values = _split_csv(_unspec_sev_raw) if _unspec_sev_raw else []
    done_resolutions = _split_csv(
        os.environ.get("JIRA_DONE_RESOLUTIONS", "Done,Done-Errata")
    )
    max_results = int(os.environ.get("JIRA_MAX_RESULTS", 1000))
    needinfo_statuses = _split_csv(
        os.environ.get("JIRA_NEEDINFO_STATUSES", "Need Information,ASSIGNED")
    )
    _raw_need_info_from = os.environ.get("JIRA_NEED_INFO_FROM_FIELD")
    if _raw_need_info_from is None:
        need_info_from_field = "Need Info From"
    else:
        need_info_from_field = _raw_need_info_from.strip()
        if need_info_from_field.lower() in ("-", "disabled", "false", "0"):
            need_info_from_field = ""
    need_info_jql_field = os.environ.get("JIRA_NEED_INFO_JQL_FIELD", "").strip()
    unspecified_priorities = _split_csv(
        os.environ.get("JIRA_UNSPECIFIED_PRIORITIES", "Undefined")
    )
    rbd_components = _split_csv(
        os.environ.get("JIRA_RBD_COMPONENTS", "rbd,rbd-mirror")
    )
    rbd_labels = _split_csv(os.environ.get("JIRA_RBD_LABELS", ""))
    openstack_components = _split_csv(
        os.environ.get("JIRA_OPENSTACK_COMPONENTS", "")
        or ",".join(
            [
                comp
                for comp in metadata_cfg.get("components", [])
                if isinstance(comp, str) and comp.startswith("openstack-")
            ]
        )
        or "openstack-nova,openstack-swift,openstack-tripleo,openstack-tempest,openstack-tripleo-heat-templates,openstack-ceilometer,openstack-mistral"
    )
    openstack_labels = _split_csv(os.environ.get("JIRA_OPENSTACK_LABELS", ""))
    jql_target_version_field = os.environ.get("JIRA_JQL_TARGET_VERSION_FIELD", "").strip()
    qe_contact_field = os.environ.get("JIRA_QE_CONTACT_FIELD", "QE Contact").strip()
    qe_contact_jql_field = os.environ.get("JIRA_QE_CONTACT_JQL_FIELD", "").strip()

    if not server:
        raise ValueError("JIRA_SERVER is required (Dashboard configuration E7).")
    if not jira_project:
        raise ValueError("JIRA_BUGS_PROJECT is required (Dashboard configuration D7).")
    if not affected_version_field:
        raise ValueError(
            "JIRA_AFFECTED_VERSION_FIELD is required (Dashboard configuration F6)."
        )
    if not affected_version:
        raise ValueError(
            "JIRA_AFFECTED_VERSION is required (Dashboard configuration F7)."
        )
    target_version = (target_version or "").strip()
    if not target_version:
        raise ValueError(
            "JIRA_TARGET_VERSION is required (Dashboard configuration G7). "
            "Provide the release value (e.g. 9.1); only issues with this Target Version are included."
        )

    return JiraConfig(
        spreadsheet_name=spreadsheet_name,
        version=version,
        jira_project=jira_project,
        target_version=target_version,
        affected_version=affected_version,
        affected_version_field=affected_version_field,
        proposed_version_field=proposed_version_field,
        jql_target_version_field=jql_target_version_field,
        approved_version_field=approved_version_field,
        approved_version=approved_version,
        server=server,
        email=email,
        token=token,
        open_statuses=open_statuses,
        qe_status=qe_status,
        verified_status=verified_status,
        blocker_field=blocker_field,
        blocker_approved_values=blocker_approved_values,
        blocker_proposed_values=blocker_proposed_values,
        blocker_rejected_values=blocker_rejected_values,
        regression_label=regression_label,
        customer_labels=customer_labels,
        documentation_component=documentation_component,
        documentation_components=documentation_components,
        exclude_components=exclude_components,
        severity_field=severity_field,
        severity_jql_field=severity_jql_field,
        unspecified_severity_values=unspecified_severity_values,
        done_resolutions=done_resolutions,
        max_results=max_results,
        needinfo_statuses=needinfo_statuses,
        need_info_from_field=need_info_from_field,
        need_info_jql_field=need_info_jql_field,
        unspecified_priorities=unspecified_priorities,
        rbd_components=rbd_components,
        rbd_labels=rbd_labels,
        openstack_components=openstack_components,
        openstack_labels=openstack_labels,
        qe_contact_field=qe_contact_field,
        qe_contact_jql_field=qe_contact_jql_field,
    )


def _split_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]
