# Jira Reporter — Report Filters Reference Guide

This document lists each report script, the Jira query functions it uses, and the JQL/filters applied. Use it as a quick reference for what each report shows and which filters are in effect.

---

## 1. Key config variables (defaults and meaning)

Values are loaded from **environment variables** (and optionally overridden by the Google Sheet “Dashboard Configuration” where applicable). Defaults below are from `config/settings.py` when the env var is not set.

### Status-related

| Variable | Default | Meaning |
|----------|---------|---------|
| **open_statuses** | `New,ASSIGNED,POST,MODIFIED` | Jira statuses treated as “open” (not done). Used for backlog counts, blocker lists, critical/regression bugs, and most action-item reports. Typically: **New**, **ASSIGNED**, **POST**, **MODIFIED** (dev workflow). Add others (e.g. In Progress, ON_DEV) if your project uses them. Env: `JIRA_OPEN_STATUSES`. |
| **qe_status** | `ON_QA` | Status meaning “with QE for testing”. Used for QE backlog, “Test on QA”, “Doc on QA”, and resolution-time logic. Env: `JIRA_QE_STATUS`. |
| **verified_status** | `Verified` | Status meaning “QE verified”. Env: `JIRA_VERIFIED_STATUS`. |
| **needinfo_statuses** | `Need Information,ASSIGNED` | Statuses for “Need Info” action items. Includes `ASSIGNED` because bugs often keep that status while **Need Info From** is set. Env: `JIRA_NEEDINFO_STATUSES`. |
| **need_info_from_field** | `Need Info From` | Jira **multi-user** field (exact display name, or `customfield_…` id) used to mean “need information from”. When non-empty (the default), Need Info queries add `"{field}" in (…)` using **account IDs** resolved from the QE team worksheet (column A: work emails or Jira Cloud account IDs like `712020:…`). If the env var is **unset**, the default field name is used. Set `JIRA_NEED_INFO_FROM_FIELD` to an **empty** value, or to `disabled`, `-`, `false`, or `0`, to omit this clause (all issues in Need Info statuses, as before). Env: `JIRA_NEED_INFO_FROM_FIELD`. |

### Severity / priority (Unspecified Severity report)

| Variable | Default | Meaning |
|----------|---------|---------|
| **severity_field** | `Severity` | Jira field used for “Unspecified Severity” report (e.g. custom field name or ID). If not set, the report uses **Priority** instead. Env: `JIRA_SEVERITY_FIELD`. |
| **unspecified_severity_values** | *(empty)* | When `severity_field` is set: Severity values treated as “unspecified” (e.g. `Unspecified`, `None`). If empty, only **empty** Severity is treated as unspecified. Env: `JIRA_UNSPECIFIED_SEVERITY_VALUES` (comma-separated). |
| **unspecified_priorities** | `Undefined` | When **no** `severity_field` is set: Priority values treated as “unspecified”. Default: **Undefined**. Env: `JIRA_UNSPECIFIED_PRIORITIES` (comma-separated). |

### Components and labels (scoping / exclusion)

| Variable | Default | Meaning |
|----------|---------|---------|
| **exclude_components** | `Jira_Change_Requests,Jira_Issues` | Component names **excluded from all report queries** (plus documentation component). Env: `JIRA_EXCLUDE_COMPONENTS`. |
| **documentation_component** | `documentation` | Single component name for “documentation” bugs. Excluded from main reports; “Doc bugs” / “Doc on QA” use it to **include** only doc. Env: `JIRA_DOCUMENTATION_COMPONENT`. |
| **documentation_components** | *(empty)* | If set, overrides single `documentation_component` with a list (comma-separated). Env: `JIRA_DOCUMENTATION_COMPONENTS`. |
| **customer_labels** | `IBM_Customer_Issue,RH_Customer_Issue` | Labels used to identify customer-related bugs in Customer Bugs Release Tracking. Env: `JIRA_CUSTOMER_LABELS`. |

### RBD report (Action Items)

| Variable | Default | Meaning |
|----------|---------|---------|
| **rbd_components** | `rbd,rbd-mirror` | Component names used to **include** issues in the **RBD bugs** section. Default: **rbd**, **rbd-mirror**. Env: `JIRA_RBD_COMPONENTS`. |
| **rbd_labels** | *(empty)* | Optional. If set, issues must have at least one of these labels **and** (if `rbd_components` set) match component. Env: `JIRA_RBD_LABELS`. |

### OpenStack report (Action Items)

| Variable | Default | Meaning |
|----------|---------|---------|
| **openstack_components** | `openstack-nova,openstack-swift,...` (or from metadata) | Component names for **OpenStack** bugs section. Default includes e.g. **openstack-nova**, **openstack-swift**, **openstack-tripleo**, **openstack-tempest**, etc. Env: `JIRA_OPENSTACK_COMPONENTS`. |
| **openstack_labels** | *(empty)* | Optional. If set, issues must also have one of these labels. Env: `JIRA_OPENSTACK_LABELS`. |

### Blockers and resolutions

| Variable | Default | Meaning |
|----------|---------|---------|
| **blocker_field** | `Release Blocker` | Jira field for release-blocker flag (e.g. custom field name). Env: `JIRA_BLOCKER_FIELD`. |
| **blocker_approved_values** | `Approved` | Values meaning “approved blocker”. Env: `JIRA_BLOCKER_APPROVED_VALUES`. |
| **blocker_proposed_values** | `Proposed` | Values meaning “proposed (candidate) blocker”. Env: `JIRA_BLOCKER_PROPOSED_VALUES`. |
| **blocker_rejected_values** | `Rejected` | Values excluded from blocker lists (e.g. Rejected). Env: `JIRA_BLOCKER_REJECTED_VALUES`. |
| **done_resolutions** | `Done,Done-Errata` | Resolutions treated as “done” for version/verification counts. Env: `JIRA_DONE_RESOLUTIONS`. |

### Other

| Variable | Default | Meaning |
|----------|---------|---------|
| **regression_label** | `Regression` | Label used to identify regression bugs. Env: `JIRA_REGRESSION_LABEL`. |

---

## 2. How filters are built

- **Config** comes from the Google Sheet **Dashboard Configuration** (and env vars). Key fields: `jira_project`, `target_version`, `open_statuses`, `exclude_components`, `documentation_component` / `documentation_components`, etc.
- **Component exclusion** is shared across reports: documentation components plus `exclude_components` (e.g. `Jira_Change_Requests`, `Jira_Issues`) are combined into one list and excluded via `component not in (...)` (or `component != "X"` when only one).
- **Target Version** (or configured field name) is used in most reports to limit to a release; when we say “target clause” below, it means: `"<proposed_version_field>" = "<target_version>"`.
- All JQL is built in `lib/jira_queries.py`; scripts either call `get_*` helpers or build custom JQL using the same clause helpers.

---

## 3. Shared clause helpers (`lib/jira_queries.py`)

| Helper | Effect |
|--------|--------|
| `_target_clause(config)` | Target Version (or configured field) = config value. |
| `_exclude_components_clause(config)` | Excludes documentation + `exclude_components` (e.g. Jira_Change_Requests, Jira_Issues). |
| `_documentation_only_clause(config)` | `component` in documentation component(s). |
| `_exclude_rejected_blocker_clause(config)` | Excludes `blocker_rejected_values` (e.g. Rejected) from blocker queries. |
| `_resolved_statuses_clause(config)` | Status in QE status + Verified. |
| `_components_clause(components)` | `component in (components)` when non-empty. |
| `_labels_clause(labels)` | `labels in (labels)` when non-empty. |

---

## 4. Report scripts and their filters

### 4.1 `scripts/tracking_dashboard.py` — QE Tracking Dashboard

- **Output:** Google Sheet “QE Tracking Dashboard” — bugs grouped by category (Feature / Stability / Test) and label.
- **Functions used:** `_build_jql()` (in script), `search_issues()`.
- **JQL / filters:**
  - `project = "<jira_project>"`
  - Target Version = `<target_version>` (target clause)
  - Exclude components (documentation + exclude_components)
  - `status in (open_statuses)`
  - `labels in (category labels)` — per category: Feature (BetaBlocker, DevelBlocker, …), Stability (UpgradeBlocker, BuildBlocker), Test (AutomationBlocker, TestBlocker).

---

### 4.2 `scripts/blocker_resolution_time.py` — Blocker Resolution Time

- **Output:** Google Sheet “Blocker Resolution Time” — QE-reported blockers with creation date, ON_QA date, days to ON_QA.
- **Functions used:** `_build_blocker_jql()` (in script), `search_issues(config, jql, expand="changelog")`.
- **JQL / filters:**
  - `project = "<jira_project>"`
  - Target Version (target clause)
  - Exclude components
  - `status in (open_statuses + qe_status + verified_status)` (includes ON_QA)
  - `"<blocker_field>" in (blocker_proposed + blocker_approved)`
  - No `_exclude_rejected_blocker_clause` in this script (unlike `get_open_blockers`).
- **Post-filter:** Only issues whose reporter is in the QE team list are included.

---

### 4.3 `scripts/scale_n_perf_defects.py` — Performance & Scale Blockers

- **Output:** Google Sheet “Performance & Scale Blockers” — Scale blockers and Performance blockers.
- **Functions used:** `_build_jql()` (in script), `search_issues()`.
- **JQL / filters (both sections):**
  - `project = "<jira_project>"`
  - Exclude components
  - `status in (open_statuses)`
  - `labels in (TestBlocker)`
  - **Scale:** `labels in (Scale, Performance&Scale)`
  - **Performance:** `(labels in (Performance, Performance&Scale) or component = "performance")`

Note: No target version filter; all open TestBlocker bugs matching the label/component criteria.

---

### 4.4 `scripts/customer_bugs_release_tracking.py` — Customer Bugs Release Tracking

- **Output:** Google Sheet “Customer Bugs Release Tracking” — customer-related bugs with version info.
- **Functions used:** `_build_customer_jql()` (in script), `search_issues()`.
- **JQL / filters:**
  - `project = "<jira_project>"`
  - Exclude components
  - `labels in (customer_labels)` or, if no customer_labels, `labels ~ "customer"`
  - If `--target-version` or config `target_version`: Target Version = that version; else `statusCategory = Done`.

---

### 4.5 `scripts/release_readiness_criteria.py` — Release Readiness Criteria

- **Output:** Google Sheet “Release Readiness Criteria” — counts and rates (QE backlog, dev backlog, blockers, regressions, verification rate, etc.).
- **Functions used:**  
  `get_qe_backlog`, `get_all_verified_bugs`, `get_dev_backlog`, `get_open_blockers`, `get_open_candidate_blockers`, `get_critical_bugs`, `get_regression_bugs`, `get_untriaged_bugs`, `get_doc_bugs`, `get_all_bugs_in_version`, `get_all_regression_bugs`, `get_all_bugs_targeted_to_version`, `get_verified_bugs`, plus changelog/transition helpers.
- **Filters:** Same as the underlying `get_*` functions below (all use target clause + exclude components unless noted).

| Data point | Function | Main JQL filters |
|------------|----------|-------------------|
| QE backlog count | `get_qe_backlog` | project, target, exclude components, status = qe_status |
| Verified bugs (for rates) | `get_all_verified_bugs` | project, target, exclude components, Verified or CLOSED with done resolutions |
| Dev backlog | `get_dev_backlog` | project, target, exclude components, status in (open_statuses + ON_DEV) |
| Open blockers | `get_open_blockers` | project, target, exclude components, open statuses, blocker field in approved, exclude rejected |
| Candidate blockers | `get_open_candidate_blockers` | project, target, exclude components, open statuses, blocker field in proposed, exclude rejected |
| Critical bugs | `get_critical_bugs` | project, target, exclude components, open statuses, priority = Critical |
| Regression bugs | `get_regression_bugs` | project, target, exclude components, open statuses, regression label |
| Untriaged | `get_untriaged_bugs` | project, exclude components, open+ON_DEV+QE+Verified statuses, approved_version_field is EMPTY (no target clause) |
| Doc bugs | `get_doc_bugs` | project, target, documentation_only clause (component = doc) |
| All bugs in version | `get_all_bugs_in_version` | project, affected version = X, exclude components, resolution EMPTY or in done_resolutions |
| All regression bugs | `get_all_regression_bugs` | project, affected version, regression label, exclude components |
| Targeted bugs (changelog) | `get_all_bugs_targeted_to_version` | project, target, exclude components, resolution EMPTY or done |
| Verified (weekly) | `get_verified_bugs` | project, target, exclude components, status changed TO Verified in date range |

---

### 4.6 `scripts/action_items.py` — Action Items (HTML)

- **Output:** HTML combining several “action item” sections.
- **Functions used:** Delegates to cephQeInfra: `NeedInfoCls`, `DocOnQaCls`, `TestOnQaCls`, `UnspecifiedSeverityCls`, `RbdBugsCls`, `OpenstackBugsCls` (each uses one `get_*` below).

See sections 4.11–4.17 for each subsection’s filters.

---

### 4.7 `scripts/pqi_report.py` — PQI Report

- **Output:** Google Sheet “PQI Report” — daily counts by dev status and QE backlog.
- **Functions used:** `get_dev_backlog`, `filter_by_status`, `get_qe_backlog`.
- **Filters:**
  - **Dev backlog:** project, target, exclude components, status in (open_statuses + ON_DEV). Then in Python: split by status (New, ASSIGNED, POST, MODIFIED).
  - **QE backlog:** project, target, exclude components, status = qe_status.

---

### 4.8 `scripts/component_distribution.py` — Component Distribution

- **Output:** Google Sheet “Component Distribution” — backlog counts by component and severity bucket (Critical, Important, Low, Moderate, None), using `JIRA_SEVERITY_FIELD` / `severity_field` for the Jira field.
- **Functions used:** `get_component_distribution_backlog`.
- **Component rows:** `metadata.json` `components` order first (full Jira names, no `parent/child` collapsing), then any component seen on a backlog issue but not listed in metadata, sorted A–Z. Names starting with `jira` (case-insensitive) are skipped.
- **JQL / filters:**  
  project, target, exclude components-only (not documentation), `status in (open_statuses + ON_DEV)`.

---

### 4.9 `scripts/average_qa_score.py` — Average Quality Score

- **Output:** Google Sheet “Average Quality Score” — single count (backlog size).
- **Functions used:** `get_overall_backlog`.
- **JQL / filters:** Same as Component Distribution: project, target, exclude components, status in (open_statuses + ON_DEV).

---

### 4.10 `scripts/arrivals_vs_resolved.py` — Arrivals Vs Resolved

- **Output:** Google Sheet “Arrivals Vs Resolved” — daily counts for new, resolved, verified, blocker arrivals.
- **Functions used:** `get_new_arrivals`, `get_resolved_bugs`, `get_verified_bugs`, `get_blocker_arrivals` (with date range = previous day).
- **Filters (all use config date range for “yesterday”):**

| Count | Function | Main JQL filters |
|-------|----------|-------------------|
| New | `get_new_arrivals` | project, affected version = X, exclude components, created in range |
| Resolved | `get_resolved_bugs` | project, target, exclude components, status in (QE, Verified), status changed TO qe_status in range |
| Verified | `get_verified_bugs` | project, target, exclude components, status changed TO verified in range |
| Blocker arrivals | `get_blocker_arrivals` | project, affected version, exclude components, created in range, blocker in (proposed+approved), exclude rejected |

---

### 4.11 `cephQeInfra/last_24_hour_bugs.py` — Last 24 Hour Bugs

- **Output:** HTML report of bugs created in the last 24 hours (UTC).
- **Functions used:** `_build_new_arrivals_jql()` (in script), `search_issues()`.
- **JQL / filters:**
  - `project = "<jira_project>"`
  - `issuetype = "Bug"`
  - `created >= "<start>" and created < "<end_exclusive>"` using the same naive wall-clock minute bounds as Issue Navigator (`[start_floor, end_minute+1m)`); Jira applies those literals in the viewer/API user timezone.
  - Exclude components.
- **Consistency logic:**
  - API retrieval searches the exact report-window JQL with `verify_complete=True` (GET+POST merge/retry, key-only pass, backoff until approximate-count matches). Table membership matches that JQL (same as Issue Navigator).
  - A buffered window (`+/- 60 minutes`) may supply richer field payloads for those keys only; it does not add bugs outside the exact JQL.
  - If retrieved count is still below Jira approximate-count for the report window, the script raises and exits non-zero so the pipeline does not email a short list.
- **Note:** No target version and no affected version filter, so all new bugs in the project (in the time window) are included except excluded components.

---

### 4.12 Need Info (`cephQeInfra/need_info.py`), used in Action Items

- **Functions used:** `get_needinfo_bugs` (loads QE team from the spreadsheet; resolves emails to Jira account IDs via `/rest/api/3/user/search` when needed).
- **JQL / filters:**  
  project, exclude components, `status in (needinfo_statuses)` (default includes `ASSIGNED` and `Need Information`), and when `need_info_from_field` is set: `"{field_id}" in (accountId1, accountId2, …)` for members listed in the QE team sheet. **No** dashboard target-version filter (bugs across all releases). If no QE account IDs can be resolved, the script logs a warning and falls back to the base Need Info query (without the `Need Info From in (...)` clause). Fetched with `expand=changelog`.
- **Need Info From age (days):** From the changelog, days since the **Need Info From** field was last set to a **non-empty** value (i.e. when the “who needs to provide info” roster was last updated). If there is no matching history entry, falls back to age in **Need Information** status (same as before).

---

### 4.13 Doc on QA (`cephQeInfra/doc_on_qa.py`), used in Action Items

- **Functions used:** `get_doc_on_qa_bugs`.
- **JQL / filters:**  
  project, target, **documentation_only** (component = doc), `status = qe_status`. Fetched with `expand=changelog`.

---

### 4.14 Test on QA (`cephQeInfra/test_on_qa.py`), used in Action Items

- **Functions used:** `get_test_on_qa_bugs`.
- **JQL / filters:**  
  project, exclude components, `status = qe_status` — **no** Target Version filter. Fetched with the QE Contact field and `fixVersions`. Mail HTML is a **Contact Person × Fix Version/s** grid (QE team sheet order), **Total** row, counts as links to Issue Navigator; bugs without a Fix Version appear under **Unspecified** and `--` is shown when zero.

---

### 4.15 Unspecified Severity (`cephQeInfra/unspecified_severity.py`), used in Action Items

- **Functions used:** `get_unspecified_severity_bugs`.
- **JQL / filters:**  
  project, target, exclude components, `status in (open_statuses)`, and either: Severity (or configured severity field) is EMPTY or in `unspecified_severity_values`, or if no severity field then `priority in (unspecified_priorities)` or priority EMPTY.

---

### 4.16 RBD Bugs (`cephQeInfra/rbd_bugs.py`), used in Action Items

- **Functions used:** `get_rbd_action_items`.
- **JQL / filters:**  
  project, target, exclude components, `status in (open_statuses)`, plus optional `component in (rbd_components)` and `labels in (rbd_labels)` when configured.

---

### 4.17 OpenStack Bugs (`cephQeInfra/openstack_dp_bugs.py`), used in Action Items

- **Functions used:** `get_openstack_action_items`.
- **JQL / filters:**  
  project, target, exclude components, `status in (open_statuses)`, plus optional `component in (openstack_components)` and `labels in (openstack_labels)` when configured.

---

## 5. Summary: `get_*` functions and their filters

| Function | Target | Exclude components | Other main filters |
|----------|--------|---------------------|--------------------|
| `get_dev_backlog` | ✓ | ✓ | status in (open + ON_DEV) |
| `get_qe_backlog` | ✓ | ✓ | status = qe_status |
| `get_open_blockers` | ✓ | ✓ | open statuses, blocker approved, exclude rejected |
| `get_open_candidate_blockers` | ✓ | ✓ | open statuses, blocker proposed, exclude rejected |
| `get_critical_bugs` | ✓ | ✓ | open statuses, priority = Critical |
| `get_regression_bugs` | ✓ | ✓ | open statuses, regression label |
| `get_untriaged_bugs` | — | ✓ | open+ON_DEV+QE+Verified, approved_version EMPTY |
| `get_doc_bugs` | ✓ | — (doc only) | documentation_only clause |
| `get_overall_backlog` | ✓ | ✓ | status in (open + ON_DEV) |
| `get_all_bugs_in_version` | — (affected) | ✓ | affected version, resolution EMPTY or done |
| `get_all_regression_bugs` | — (affected) | ✓ | affected version, regression label |
| `get_all_bugs_targeted_to_version` | ✓ | ✓ | resolution EMPTY or done |
| `get_all_verified_bugs` | ✓ | ✓ | Verified or CLOSED + done resolutions |
| `get_verified_bugs` | ✓ | ✓ | status changed TO Verified in range |
| `get_resolved_bugs` | ✓ | ✓ | status in (QE, Verified), changed TO qe_status in range |
| `get_new_arrivals` | — (affected) | ✓ | affected version, created in range |
| `get_blocker_arrivals` | — (affected) | ✓ | affected version, created in range, blocker in values, exclude rejected |
| `get_needinfo_bugs` | ✓ | — | status in needinfo_statuses; optional “Need Info From” ∈ QE account IDs (no target version) |
| `get_doc_on_qa_bugs` | ✓ | doc only | status = qe_status |
| `get_test_on_qa_bugs` | — | ✓ | status = qe_status (any target version) |
| `get_unspecified_severity_bugs` | ✓ | ✓ | open statuses, severity/priority unspecified |
| `get_rbd_action_items` | ✓ | ✓ | open statuses, optional rbd components/labels |
| `get_openstack_action_items` | ✓ | ✓ | open statuses, optional openstack components/labels |

---

## 6. Config keys that affect filters

- **Version/scope:** `target_version`, `affected_version`, `proposed_version_field`, `affected_version_field`, `approved_version_field`, `approved_version`
- **Exclusions:** `exclude_components`, `documentation_component` / `documentation_components`
- **Statuses / Need Info:** `open_statuses`, `qe_status`, `verified_status`, `needinfo_statuses`, `need_info_from_field` (plus QE team sheet for account ID list)
- **Blockers:** `blocker_field`, `blocker_approved_values`, `blocker_proposed_values`, `blocker_rejected_values`
- **Other:** `regression_label`, `customer_labels`, `done_resolutions`, `rbd_components`, `rbd_labels`, `openstack_components`, `openstack_labels`, `severity_field`, `unspecified_severity_values`, `unspecified_priorities`

Env override for default exclude components: `JIRA_EXCLUDE_COMPONENTS` (comma-separated; default `Jira_Change_Requests,Jira_Issues`).
