# Jira Cloud: Filters and Dashboard Guide

This guide helps you recreate the jira-reporter reports as **saved filters** and **dashboard gadgets** in Jira Cloud. Replace placeholders (e.g. `PROJECT`, `TARGET_VERSION`) with your project key and version values.

---

## Before you start

- **Target Version:** Use the field name in JQL: `"Target Version" = "9.1"` — no custom field ID is needed; this works in Jira Cloud as shown in the verified example below.
- **Other custom fields:** If "Release Blocker" or similar fail in JQL, try the field name in quotes first; only if the query fails, use **Jira → Settings → Issues → Custom fields** to find the field ID.
- **Project & versions:** Replace `PROJECT` with your project key (e.g. `IBMCEPH`) and `TARGET_VERSION` / `AFFECTED_VERSION` with your release (e.g. `9.1`).
- **Component exclusion:** The repo excludes documentation + `Jira_Change_Requests` + `Jira_Issues`. Adjust the `component not in (...)` list to match your `exclude_components` and documentation component.

### Verified JQL pattern (IBMCEPH)

Filters created with the following pattern work without custom field IDs:

```jql
project = IBMCEPH
AND type = "Bug"
AND status IN ("ASSIGNED", "MODIFIED", "New", "POST", "ON_DEV", "ON_QA")
AND "Target Version" = "9.1"
ORDER BY created DESC
```

Alternative (if your instance uses a version-picker field name):

```jql
spaceJira = "Ceph Storage" AND issuetype = Bug
AND "Target Version[Version Picker (multiple versions)]" = 9.1
AND component != documentation
```

Use the first style for the filters in this guide; add `type = "Bug"` and `ORDER BY created DESC` where you want only bugs and newest first.

### Team JQL conventions (for modifying queries)

Below is how your team’s JQL refers to project, type, status, and other fields. Use this when adapting the placeholder JQL in this guide to your instance.

| Concept | How it appears in your JQL | Notes |
|--------|----------------------------|--------|
| **Project** | `project = "Ceph Storage"` or `project = IBMCEPH` | Name (in quotes) vs project key; both are used. |
| **Issue type (bugs only)** | `worktype = Bug` or `issuetype = Bug` | Depends on product/context; use the one that works in your search. |
| **Status** | `status = ON_QA`, `status != Closed`, `status IN (New, Assigned, Post, Modified, ON_QA)` | Use exact values your Jira returns (e.g. `Assigned` vs `ASSIGNED`, `Post` vs `POST`). |
| **Target Version (single)** | `"Target Version" = "9.1"` | Simple form. |
| **Target Version (version picker)** | `"Target Version[Version Picker (multiple versions)]" = 9.1` or `IN (9.0z1, 8.1z5, 7.1z9, 9.0z2, 8.1z6, 7.1z10)` | Full field name when your scheme uses the version picker; use `IN (...)` for multiple versions. |
| **Component** | `component != documentation`, `component = rados` | Exclude doc; restrict to specific components by name. |
| **Space (if used)** | `spaceJira = "Ceph Storage"` | Use when your boards/filters are scoped by space. |
| **Customer label** | `labels = IBM_Customer_Issue` | Add `AND labels = RH_Customer_Issue` or `labels IN (...)` if needed. |
| **Reporter (team)** | `reporter IN (712020:uuid1, 712020:uuid2, ...)` | Jira Cloud account IDs; use for “reported by QE” or similar. |

**Example patterns your team uses:**

- Customer bugs (open):  
  `project = "Ceph Storage" AND labels = IBM_Customer_Issue AND worktype = Bug AND status != Closed`
- Bugs in ON_QA:  
  `project = "Ceph Storage" AND worktype = Bug AND status = ON_QA`
- Target version + component (e.g. rados):  
  `issuetype = Bug AND "Target Version[Version Picker (multiple versions)]" = 9.1 AND component != documentation AND component = rados AND project = IBMCEPH AND status in (New, ASSIGNED, EMPTY, "Need Information", ON_DEV, Review)`
- Multiple target versions:  
  `spaceJira = "Ceph Storage" AND issuetype = Bug AND status IN (New, Assigned, Post, Modified, ON_QA) AND "Target Version[Version Picker (multiple versions)]" IN (9.0z1, 8.1z5, 7.1z9, 9.0z2, 8.1z6, 7.1z10) AND component != documentation`

When building or editing filters, stick to the same project style (`"Ceph Storage"` vs `IBMCEPH`), the same type field (`worktype` vs `issuetype`), and the same status wording as in the saved filters that already work for you.

### PQI / QE backlog parity with Jira Cloud

To align **PQI report** ON_QA count with your Jira Cloud filter (e.g. 26 vs 26):

1. **Issue type:** jira-reporter adds `issuetype = "Bug"` to the QE backlog JQL (same as Cloud `type = Bug`).
2. **Same component list:** Use the same component names as in Cloud, e.g. `component not in (documentation, Jira_Change_Requests, Jira_Issues)`. The reporter gets the documentation component from `JIRA_DOCUMENTATION_COMPONENT` (default `documentation`, lowercase). If you use lowercase in Cloud, leave the env unset so the reporter uses `documentation` too.
3. **If counts still differ:** Check **config** (e.g. `JIRA_DOCUMENTATION_COMPONENT` in env, or `jira_project` / target version in the Dashboard Configuration sheet) so the reporter uses the same project, target version, and component list as your Cloud filter.

---

## Part 1: Create saved filters

For each report below, create a **saved filter** so you can reuse it in dashboards.

**Steps in Jira Cloud:**

1. **Issues → Search for issues** (or **Filters**).
2. Switch to **Advanced** (JQL).
3. Paste the JQL and replace placeholders.
4. **Save as** → name the filter (e.g. "QE Backlog – 9.1") → Save.

Use the same JQL and names as in the table; the dashboard section will refer to these filter names.

---

## Part 2: JQL by report

Use these JQL strings to create one saved filter per row. Replace:

- `PROJECT` → your project key (e.g. `IBMCEPH`)  
- `TARGET_VERSION` → e.g. `9.1`  
- `AFFECTED_VERSION` → same or your "Affects Version" value  
- `"TARGET_VERSION_FIELD"` → use **`"Target Version"`** (no custom field ID needed)  
- `AFFECTED_VERSION_FIELD` → `affectedVersion` (or your field)  
- `BLOCKER_FIELD` → `"Release Blocker"` or your field  
- `EXCLUDE_COMPONENTS` → e.g. `("documentation", "Jira_Change_Requests", "Jira_Issues")` — one value: use `component != "X"`

Optional: add `AND type = "Bug"` to limit to bugs, and `ORDER BY created DESC` to sort newest first.

---

### Backlog & release readiness

| Filter name (suggested) | JQL |
|------------------------|-----|
| **Dev Backlog** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status in ("New", "ASSIGNED", "POST", "MODIFIED", "ON_DEV")` |
| **QE Backlog** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status = "ON_QA"` |
| **Overall Backlog** | Same as Dev Backlog (used for Component Distribution / Average QA Score). |
| **Open Blockers** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status in ("New", "ASSIGNED", "POST", "MODIFIED") AND "BLOCKER_FIELD" in ("Approved") AND "BLOCKER_FIELD" not in ("Rejected")` |
| **Candidate Blockers** | Same as Open Blockers but `"BLOCKER_FIELD" in ("Proposed")` and exclude Rejected. |
| **Critical Bugs** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status in ("New", "ASSIGNED", "POST", "MODIFIED") AND priority = "Critical"` |
| **Regression Bugs** | Same as Critical but add `AND labels = "Regression"` (or your regression label). |
| **Untriaged** | `project = PROJECT AND component not in EXCLUDE_COMPONENTS AND status in ("New", "ASSIGNED", "POST", "MODIFIED", "ON_DEV", "ON_QA", "Verified") AND "TARGET_VERSION_FIELD" is EMPTY` |
| **Doc Bugs** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component = "documentation"` |

---

### Arrivals & resolution (use a fixed date range or relative)

| Filter name | JQL (replace DATE_FROM, DATE_TO e.g. start/end of week) |
|-------------|--------------------------------------------------------|
| **New Arrivals (week)** | `project = PROJECT AND AFFECTED_VERSION_FIELD = "AFFECTED_VERSION" AND component not in EXCLUDE_COMPONENTS AND created >= "DATE_FROM" AND created <= "DATE_TO"` |
| **Resolved to QE (week)** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status in ("ON_QA", "Verified") AND status changed TO "ON_QA" AFTER "DATE_FROM" BEFORE "DATE_TO"` |
| **Verified (week)** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status changed TO "Verified" AFTER "DATE_FROM" BEFORE "DATE_TO"` |
| **Blocker Arrivals (week)** | Same as New Arrivals, plus: `AND "BLOCKER_FIELD" in ("Proposed", "Approved") AND "BLOCKER_FIELD" not in ("Rejected")` |

---

### Action items & specialty

| Filter name | JQL |
|-------------|-----|
| **Need Info** | `project = PROJECT AND issuetype = Bug AND component not in EXCLUDE_COMPONENTS AND status in ("Need Information", "ASSIGNED")` **plus** `AND "NEED_INFO_FROM_FIELD_ID" in (ACCOUNT_ID_1, ACCOUNT_ID_2, …)` — no target-version filter. Field id is resolved from the **Need Info From** field (`JIRA_NEED_INFO_FROM_FIELD`; default name when env unset). Account IDs come from the **QE team** worksheet column A (emails resolved via Jira user search, or paste IDs). Omit the `in (...)` clause if `JIRA_NEED_INFO_FROM_FIELD` is empty or `disabled`. |
| **Doc on QA** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component = "documentation" AND status = "ON_QA"` |
| **Test on QA** (saved filter, one release) | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status = "ON_QA"` |
| **Test on QA** (Action Items mail) | Omit Target Version from the line above: all ON_QA bugs (after component exclusion rules); the mail table columns are the distinct target versions on those issues; rows follow the QE team sheet. |
| **Unspecified Severity** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status in ("New", "ASSIGNED", "POST", "MODIFIED") AND ("Severity" is EMPTY OR "Severity" in ("Unspecified"))` *(Adjust Severity field name and values to match your instance.)* |
| **RBD Action Items** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status in ("New", "ASSIGNED", "POST", "MODIFIED") AND component in ("rbd", "rbd-mirror")` |
| **OpenStack Action Items** | Same as RBD but `AND component in ("openstack-nova", "openstack-swift", ...)` (your openstack component list). |

---

### Tracking & customer

| Filter name | JQL |
|-------------|-----|
| **QE Tracking – Feature** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND status in ("New", "ASSIGNED", "POST", "MODIFIED") AND labels in ("BetaBlocker", "DevelBlocker", "ServiceDeliveryBlocker", "DeliveryBlocker")` |
| **QE Tracking – Stability** | Same but `labels in ("UpgradeBlocker", "BuildBlocker")`. |
| **QE Tracking – Test** | Same but `labels in ("AutomationBlocker", "TestBlocker")`. |
| **Scale Blockers** | `project = PROJECT AND component not in EXCLUDE_COMPONENTS AND status in ("New", "ASSIGNED", "POST", "MODIFIED") AND labels in ("TestBlocker") AND labels in ("Scale", "Performance&Scale")` |
| **Performance Blockers** | Same but `AND (labels in ("Performance", "Performance&Scale") OR component = "performance")`. |
| **Customer Bugs (target)** | `project = PROJECT AND component not in EXCLUDE_COMPONENTS AND labels in ("IBM_Customer_Issue", "RH_Customer_Issue") AND "TARGET_VERSION_FIELD" = "TARGET_VERSION"` |
| **Customer Bugs (done)** | Same but replace Target Version clause with `AND statusCategory = Done`. |

---

### Version-wide (for rates)

| Filter name | JQL |
|-------------|-----|
| **All bugs in version** | `project = PROJECT AND AFFECTED_VERSION_FIELD = "AFFECTED_VERSION" AND component not in EXCLUDE_COMPONENTS AND (resolution is EMPTY OR resolution in ("Done", "Done-Errata"))` |
| **All regressions in version** | `project = PROJECT AND AFFECTED_VERSION_FIELD = "AFFECTED_VERSION" AND labels = "Regression" AND component not in EXCLUDE_COMPONENTS` |
| **All verified (target)** | `project = PROJECT AND "TARGET_VERSION_FIELD" = "TARGET_VERSION" AND component not in EXCLUDE_COMPONENTS AND (status = "Verified" OR (status = "CLOSED" AND resolution in ("Done", "Done-Errata")))` |

---

## Part 3: Create the dashboard

**Steps:**

1. **Dashboards → Create dashboard** (or open an existing one).
2. Name it (e.g. "Release health – 9.1").
3. Add gadgets: **Add gadget** → choose type → **Configure** (select the saved filter, set columns/axes).

---

## Part 4: Gadget and axis recommendations

Use one row per report you want on the dashboard. **Filter** = the saved filter you created from Part 2.

| Report / metric | Gadget type | Configuration | X-axis | Y-axis (or meaning) |
|-----------------|-------------|---------------|--------|----------------------|
| **Dev Backlog** | Filter Results | Filter = Dev Backlog; columns: Key, Summary, Status, Component, Priority, Assignee | — | — (table) |
| **QE Backlog** | Filter Results | Filter = QE Backlog; columns: Key, Summary, Status, Component, Assignee | — | — (table) |
| **Open Blockers** | Filter Results | Filter = Open Blockers | — | — (table) |
| **Candidate Blockers** | Filter Results | Filter = Candidate Blockers | — | — (table) |
| **Critical / Regression / Untriaged / Doc** | Filter Results | Filter = respective filter | — | — (table) |
| **Need Info, Doc on QA, Test on QA, Unspecified Severity, RBD, OpenStack** | Filter Results | Filter = respective action-item filter | — | — (table) |
| **Backlog by status** | Two Dimensional Filter Statistics | Filter = Dev Backlog (or Overall Backlog) | **Status** | **Count of issues** (bars per status) |
| **Backlog by component** | Two Dimensional Filter Statistics | Filter = Overall Backlog | **Component** | **Count of issues** |
| **Backlog by priority** | Two Dimensional Filter Statistics | Filter = Overall Backlog | **Priority** | **Count of issues** |
| **Release readiness counts** | Pie Chart (or 2D Filter Statistics) | Filter = Dev Backlog; Statistic type = Count; Group by = (none) — one slice. Repeat for QE Backlog, Open Blockers, etc. as separate gadgets, or use **Single Stat** if available. | — | **Count** (single number or one slice per filter) |
| **Arrivals vs Resolved (over time)** | Created vs Resolved Chart | Filter = e.g. "All bugs in version" or project + component exclusion; choose date range | **Time (week/month)** | **Created** (line/bar), **Resolved** (line/bar) |
| **New vs Verified this week** | Two Dimensional Filter Statistics | Use two filters: "New Arrivals (week)" and "Verified (week)" — best as two **Filter Results** counts or two Single Stat gadgets; Jira may not have a single gadget that compares two filters. Alternative: one Filter Results for New Arrivals, one for Verified. | — | Count (number of issues) |
| **Regression rate** | — | Use filter "All regressions in version" count ÷ "All bugs in version" count (manual or external); or one Filter Results for regressions with a title "Regressions in version". | — | — |
| **Component × Priority** | Two Dimensional Filter Statistics | Filter = Overall Backlog | **Component** | **Priority** (heatmap/grid: component vs priority) |
| **QE Tracking (Feature/Stability/Test)** | Filter Results | Three filters → three tables, or one 2D: Filter = QE Tracking – Feature, Group by = Labels. | — | — (table or count by label) |
| **Scale / Performance Blockers** | Filter Results | Filter = Scale Blockers; same for Performance Blockers | — | — (table) |
| **Customer Bugs** | Filter Results | Filter = Customer Bugs (target or done) | — | — (table) |

---

## Part 5: Quick reference – axes by gadget type

- **Filter Results:** no axes; show issue list (columns = Key, Summary, Status, etc.).
- **Two Dimensional Filter Statistics:**  
  - **X-axis:** Status, Component, Priority, Assignee, or Labels (what to group by first).  
  - **Y-axis:** usually **Count of issues** (how many per group).  
  - For a **heatmap** (e.g. Component × Priority): X = Component, Y = Priority (or vice versa).
- **Created vs Resolved:** X = **Time** (week/month), Y = **Number created** and **Number resolved** (two series).
- **Pie Chart:** one dimension (e.g. Status or Component); "slices" = groups, size = count.
- **Single Stat / Number:** one filter → one number (e.g. total QE Backlog count). Use Filter = that filter, Statistic = Count.

---

## Part 6: Steps summary

1. **Create all saved filters** (Part 2) with your PROJECT, TARGET_VERSION, AFFECTED_VERSION, TARGET_VERSION_FIELD, BLOCKER_FIELD, EXCLUDE_COMPONENTS.
2. **Create a new dashboard** (or open existing).
3. **Add gadgets:**  
   - **Tables:** Filter Results → choose filter → pick columns.  
   - **Counts / breakdowns:** Two Dimensional Filter Statistics (or Pie Chart) → choose filter → set X (and Y if 2D).  
   - **Trends:** Created vs Resolved → choose filter + date range.
4. **Arrange** gadgets and save the dashboard.
5. **Reuse:** For a new release, duplicate the dashboard and edit each gadget’s filter to the new version filter, or use a **version picker** if you build filters with a shared naming pattern.

---

## Optional: JQL with your exact values

If you want copy-paste JQL for one project/version (e.g. IBMCEPH, 9.1), substitute in the table in Part 2:

- `PROJECT` → `IBMCEPH`
- `TARGET_VERSION` and `AFFECTED_VERSION` → `9.1`
- `TARGET_VERSION_FIELD` → `"Target Version"`
- `AFFECTED_VERSION_FIELD` → `affectedVersion`
- `BLOCKER_FIELD` → `"Release Blocker"`
- `EXCLUDE_COMPONENTS` → `("documentation", "Jira_Change_Requests", "Jira_Issues")`

For **relative dates** in “Arrivals & resolution” filters you can use Jira’s relative dates, e.g. `created >= -7d AND created <= now()` for “last 7 days”, if your Jira Cloud supports it; otherwise use fixed `DATE_FROM` / `DATE_TO`.

If you share your project key, version, and custom field names/IDs, the JQL can be rewritten once with those values filled in for direct copy-paste.
