# Jira Reporter JQL Reference

This document lists the JQL used by each report **with current values** from
`Dashboard Configuration` and env/YAML overrides.

## Current values

- Project: `IBMCEPH`
- Affects Version field: `affectedVersion`
- Affects Version value: `9.1`
- Target Version field: `Target Version` (custom field)
- Target Version value: `9.1` (required in G7; only issues with this value are included; empty Target Version is excluded)
- Documentation component: `documentation`
- Regression label: `Regression`
- Open statuses: `New`, `ASSIGNED`, `POST`, `MODIFIED`
- QE status: `ON_QA`
- Verified status: `Verified`
- Release blocker field: `Release Blocker`
- Blocker approved values: `Approved` (Bugzilla Blocker+ → Approved)
- Blocker proposed values: `Proposed` (Bugzilla Blocker? → Proposed; Rejected = Blocker- is not used in open-blocker queries)
- Blocker rejected values: `Rejected` (excluded from open-blocker and blocker-arrival JQL when set)
- Approved version field: `Target Version`
- Done resolutions: `Done`, `Done-Errata`
- Customer labels: `IBM_Customer_Issue`, `RH_Customer_Issue`
- Documentation components: (optional) comma-separated list when using flattened components
- Severity field: (optional) e.g. `Severity`; when set, Unspecified Severity report filters by this field
- Unspecified severity values: (optional) when severity field is set, values that count as unspecified

**Bugzilla → Jira value mapping:** Severity: Urgent→Critical, High→Important, Medium→Moderate, Low→Low. Priority: Urgent→Critical, High→Major, Medium→Trivial, Low→Minor. Version: Bugzilla Version → Affects Version; Target Release → Target Version; Fixed In Version → Fix Version.

## Field clause names used

- `project` → Project (`project`)
- `status` → Status (`status`)
- `statusCategory` → Status Category (`statusCategory`)
- `labels` → Labels (`labels`)
- `component` → Components (`component`)
- `priority` → Priority (`priority`)
- `resolution` → Resolution (`resolution`)
- `created` → Created (`created`, `createdDate`)
- `affectedVersion` → Affects versions (`affectedVersion`)
- `fixVersion` → Fix versions (`fixVersion`)
- `Target Version` → Target Version (`Target Version`, `cf[10292]`)
- `Release Blocker` → Release Blocker (`Release Blocker`, `cf[10352]`)
- `Severity` → Severity (when `JIRA_SEVERITY_FIELD` is set; reporter-set)

## Arrivals Vs Resolved (`scripts/arrivals_vs_resolved.py`)

- **New arrivals**
  - `project = "IBMCEPH"`
  - `affectedVersion = "9.1"`
  - `component != "documentation"`
  - `created >= "<DATE_FROM>" and created <= "<DATE_TO>"`

- **Resolved (moved to QE status)**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `component != "documentation"`
  - `status in ("ON_QA", "Verified")`
  - `status changed TO "ON_QA" AFTER "<DATE_FROM>" BEFORE "<DATE_TO>"`

- **Verified**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status changed TO "Verified" AFTER "<DATE_FROM>" BEFORE "<DATE_TO>"`

- **Blocker arrivals**
  - `project = "IBMCEPH"`
  - `affectedVersion = "9.1"`
  - `component != "documentation"`
  - `created >= "<DATE_FROM>" and created <= "<DATE_TO>"`
  - `"Release Blocker" in ("Proposed", "Approved")`

## PQI Report (`scripts/pqi_report.py`)

Aligned with Bugzilla PQI: both dev and QE backlog are filtered by **Target Version** (Bugzilla: target_release), not by Affects Version.

- **Dev backlog**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `component != "documentation"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED", "ON_DEV")`

- **QE backlog**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status = "ON_QA"`

## Release Readiness Criteria (`scripts/release_readiness_criteria.py`)

- **QE backlog**: same as PQI QE backlog
- **Dev backlog**: same as PQI dev backlog

- **Open blockers**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - `"Release Blocker" in ("Approved")`

- **Open candidate blockers**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - `"Release Blocker" in ("Proposed")`

- **Critical bugs**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - `priority = "Critical"`

- **Regression bugs**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - `labels = "Regression"`

- **Untriaged bugs**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `component != "documentation"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED", "ON_DEV", "ON_QA", "Verified")`
  - `"Target Version" is EMPTY`

- **Documentation bugs**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `component = "documentation"`

- **All bugs in version**
  - `project = "IBMCEPH"`
  - `affectedVersion = "9.1"`
  - `component != "documentation"`
  - `(resolution is EMPTY or resolution in ("Done", "Done-Errata"))`

- **All regression bugs (version)**
  - `project = "IBMCEPH"`
  - `affectedVersion = "9.1"`
  - `labels = "Regression"`

- **All bugs targeted to version**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `component != "documentation"`
  - `(resolution is EMPTY or resolution in ("Done", "Done-Errata"))`

- **All verified bugs**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `(status = "Verified" or (status = "CLOSED" and resolution in ("Done", "Done-Errata")))`

- **Verified weekly**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status changed TO "Verified" AFTER "<DATE_FROM>" BEFORE "<DATE_TO>"`

## Blocker Resolution Time (`scripts/blocker_resolution_time.py`)

- **QE-reported blockers**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED", "ON_QA", "Verified")`
  - `"Release Blocker" in ("Proposed", "Approved")`

## Customer Bugs Release Tracking (`scripts/customer_bugs_release_tracking.py`)

- **When target version is provided**
  - `project = "IBMCEPH"`
  - `labels in ("IBM_Customer_Issue", "RH_Customer_Issue")` (fallback: `labels ~ "customer"`)
  - `"Target Version" = "9.1"`

- **When target version is empty**
  - `project = "IBMCEPH"`
  - `labels in ("IBM_Customer_Issue", "RH_Customer_Issue")` (fallback: `labels ~ "customer"`)
  - `statusCategory = Done`

## Average Quality Score (`scripts/average_qa_score.py`)

- **Overall backlog**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `component != "documentation"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED", "ON_DEV")`

## QE Tracking Dashboard (`scripts/tracking_dashboard.py`)

- **Blockers by labels**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - `labels in (<CATEGORY_LABELS>)`
    - Feature: `BetaBlocker`, `DevelBlocker`, `ServiceDeliveryBlocker`, `DeliveryBlocker`
    - Stability: `UpgradeBlocker`, `BuildBlocker`
    - Test: `AutomationBlocker`, `TestBlocker`

## Component Distribution (`scripts/component_distribution.py`)

- **Overall backlog**: same as Average Quality Score (JQL unchanged).
- **Sheet columns:** component × severity buckets (Critical, Important, Low, Moderate, None) from the Jira field configured by `JIRA_SEVERITY_FIELD` (default `Severity`).

## Performance & Scale Blockers (`scripts/scale_n_perf_defects.py`)

- **Scale blockers**
  - `project = "IBMCEPH"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - `labels in ("TestBlocker")`
  - `labels in ("Scale", "Performance&Scale")`

- **Performance blockers**
  - `project = "IBMCEPH"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - `labels in ("TestBlocker")`
  - `(labels in ("Performance", "Performance&Scale") or component = "performance")`

## Last 24 Hours HTML Report (`cephQeInfra/last_24_hour_bugs.py`)

- **New arrivals in last 24 hours** (no affected/target version filter)
  - `project = "IBMCEPH"`
  - `issuetype = "Bug"`
  - `created >= "<start>" and created < "<end_exclusive>"` — same naive wall-clock literals as Issue Navigator (minute-precision exclusive upper bound; no timezone rewrite)
  - `component not in ("documentation", "Jira_Change_Requests", "Jira_Issues")` *(or your configured exclude list)*
  - `ORDER BY created DESC` *(Navigator link only; REST search sorts in Python)*
  - API searches the exact report-window JQL (`verify_complete=True`); a ±60 minute buffered fetch may enrich field payloads for those keys only (does not add extra rows)
  - Incomplete approximate-count mismatch fails the job

## Action Items (`scripts/action_items.py`)

- **Need Info**
  - `project = "IBMCEPH"`
  - `issuetype = Bug`
  - `component not in ("documentation", "Jira_Change_Requests", "Jira_Issues")` *(or your configured exclude list)*
  - `status in ("Need Information", "ASSIGNED")` *(default; override with `JIRA_NEEDINFO_STATUSES`)*
  - **No** `"Target Version"` filter (Need Info bugs may span releases)
  - **QE “Need Info From” filter (default):** `"customfield_XXXXX" in (712020:…, 712020:…, …)` — field id is looked up from the field named **Need Info From** (override with `JIRA_NEED_INFO_FROM_FIELD`); account IDs are taken from the QE team worksheet column A (work emails or raw Cloud account IDs). Set `JIRA_NEED_INFO_FROM_FIELD` to empty or `disabled` to drop this clause.

- **Doc Bugs On QA**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `component = "documentation"`
  - `status = "ON_QA"`

- **Test On QA** (Action Items matrix: all releases as columns)
  - `project = "IBMCEPH"`
  - `issuetype = Bug`
  - `component not in ("documentation", "Jira_Change_Requests", "Jira_Issues")` *(per config)*
  - `status = "ON_QA"`
  - *(No `Target Version` clause — bugs for every targeted release are grouped in the table.)*

- **Unspecified Severity**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `component != "documentation"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - When `JIRA_SEVERITY_FIELD` is set: `"Severity" is EMPTY` (or `"Severity" in (<values>)` if `JIRA_UNSPECIFIED_SEVERITY_VALUES` set). Otherwise: `priority in ("Undefined")` or `priority is EMPTY`

- **RBD Action Items**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - `component in ("rbd", "rbd-mirror")`

- **OpenStack DP Action Items**
  - `project = "IBMCEPH"`
  - `"Target Version" = "9.1"`
  - `status in ("New", "ASSIGNED", "POST", "MODIFIED")`
  - `component in ("openstack-*")`
