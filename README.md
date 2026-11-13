# Jira Reporter

Fetch QE metrics from Jira and update Google Sheets dashboards.

## Quick start

1. Install dependencies:
   - `python -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`

2. **Credentials (first-time onboarding):** create a Jira Cloud API token and a Google service account key, then export env vars. Step-by-step instructions: **[docs/LOCAL_CREDENTIALS_SETUP.md](docs/LOCAL_CREDENTIALS_SETUP.md)**.

3. Ensure Google Sheets service account credentials:
   - Default path: `~/.gapi/google_api_secret.json`
   - Override with `GSPREAD_SERVICE_ACCOUNT=/path/to/creds.json`
   - Share each target spreadsheet with the service account `client_email` from the JSON (Editor).

4. Provide Jira credentials:
   - `export JIRA_TOKEN="your_api_token"`
   - Jira user email (must match the token) is read from the sheet (cell `H7`) or `JIRA_EMAIL` / `metadata.json`

5. Run a report:
   - `python scripts/release_readiness_criteria.py "YOUR SPREADSHEET NAME"`

## Configuration

The scripts read the `Dashboard Configuration` worksheet in the target spreadsheet. All version/field names and core settings are taken from sheet cells; optional overrides use environment variables only.

### Google Sheet cells used for input (Dashboard Configuration)

| Cell | Row 6 (header/label) | Row 7 (value) | Purpose |
|------|----------------------|---------------|---------|
| **D** | — | `D7` | JIRA_BUGS_PROJECT (Jira project key) |
| **E** | — | `E7` | JIRA_SERVER (Jira base URL) |
| **F** | `F6` | `F7` | F6 = JIRA_AFFECTED_VERSION_FIELD (e.g. `affectedVersion`); F7 = JIRA_AFFECTED_VERSION / version value |
| **G** | `G6` | `G7` | G6 = JIRA_PROPOSED_VERSION_FIELD (e.g. `Target Version`, `Fix Version`); G7 = JIRA_TARGET_VERSION (release value for JQL) |
| **H** | — | `H7` | JIRA_EMAIL |
| **I** | `I6` | `I7` | I6 = JIRA_APPROVED_VERSION_FIELD (e.g. `Target Version`, `Fix Version`). I7 = approved version value (e.g. `9.1`). Same behaviour as G6/G7: if I6 empty → env `JIRA_APPROVED_VERSION_FIELD` then default; if I7 empty → env `JIRA_APPROVED_VERSION` then default to G7 value. |

**Required:** D7, E7, F6, F7, G6, G7, H7 (or JIRA_EMAIL from env/metadata). I6 and I7 are optional; same fallback behaviour as proposed (G6/G7).

**Complete list of Dashboard Configuration cells used for input:**  
`D7`, `E7`, `F6`, `F7`, `G6`, `G7`, `H7`, `I6`, `I7`.

**Other worksheets:** The QE team list is read from the worksheet named in `JIRA_QE_TEAM_SHEET` (default: `QE Team Member` or `QE_team_member`). Column **A** is one entry per row: **work email** (resolved to a Jira account via the REST API), **Jira Cloud account ID** (e.g. `712020:uuid`), or (for other reports that filter in Python) a display name. The **Need Info** report and Action Items section use this list to restrict bugs to those whose **Need Info From** field includes one of those users (see `JIRA_NEED_INFO_FROM_FIELD`).

### Optional overrides (environment variables only)

If a sheet cell is empty, the corresponding env (when documented) or a default is used. All optional behaviour is controlled by env vars:

- `JIRA_AFFECTED_VERSION_FIELD` (default: `affectedVersion`)
- `JIRA_PROPOSED_VERSION_FIELD` (default: `Target Version`)
- `JIRA_APPROVED_VERSION_FIELD` (default: `Target Version`; also read from sheet `I6`, same as G6)
- `JIRA_APPROVED_VERSION` (default: same as G7 value; also read from sheet `I7`, same as G7 for value)
- `JIRA_OPEN_STATUSES` (default: `New,ASSIGNED,POST,MODIFIED`)
- `JIRA_QE_STATUS` (default: `ON_QA`)
- `JIRA_VERIFIED_STATUS` (default: `Verified`)
- `JIRA_BLOCKER_FIELD` (default: `Release Blocker`)
- `JIRA_BLOCKER_APPROVED_VALUES` (default: `Approved`)
- `JIRA_BLOCKER_PROPOSED_VALUES` (default: `Proposed`)
- `JIRA_BLOCKER_REJECTED_VALUES` (default: `Rejected`; set to empty to disable)
- `JIRA_REGRESSION_LABEL` (default: `Regression`)
- `JIRA_CUSTOMER_LABELS` (default: `IBM_Customer_Issue,RH_Customer_Issue`)
- `JIRA_DOCUMENTATION_COMPONENT` (default: `documentation`)
- `JIRA_DOCUMENTATION_COMPONENTS` (comma-separated list; unset by default)
- `JIRA_SEVERITY_FIELD` (default: unset)
- `JIRA_UNSPECIFIED_SEVERITY_VALUES` (comma-separated; unset by default)
- `JIRA_DONE_RESOLUTIONS` (default: `Done,Done-Errata`)
- `JIRA_MAX_RESULTS` (default: `1000`)
- `JIRA_NEEDINFO_STATUSES` (default: `Need Information,ASSIGNED`)
- `JIRA_NEED_INFO_FROM_FIELD` (default when **unset**: `Need Info From` — adds a JQL `in (accountId,…)` clause using the QE team sheet; set to **empty** or `disabled` / `-` / `false` / `0` to disable and show all Need Info–status bugs)
- `JIRA_UNSPECIFIED_PRIORITIES` (default: `Undefined`)
- `JIRA_RBD_COMPONENTS` (default: `rbd,rbd-mirror`)
- `JIRA_RBD_LABELS` (default: unset)
- `JIRA_OPENSTACK_COMPONENTS` (default: from `metadata.json` or fallback list)
- `JIRA_OPENSTACK_LABELS` (default: unset)
- `JIRA_NEEDINFO_SHEET_NAME` (default: `Need Info`)
- `JIRA_DOC_ON_QA_SHEET_NAME` (default: `DocBugs`)
- `JIRA_QE_TEAM_SHEET` (default: `QE Team Member` or `QE_team_member`)
- `JIRA_JQL_TARGET_VERSION_FIELD` (optional; **Unassigned QE Contact** target-version link/filter only) — exact field token for JQL when `customfield_…` fails in Issue Navigator. The **On QA list of bugs** uses only `fixVersion` and does not use this setting.
- `JIRA_RELEASE_READINESS_FAST` (default: unset)
- `JIRA_METADATA_PATH` (default: `./metadata.json`)
- `JIRA_SKIP_METADATA_VALIDATION` (default: unset)

Jira API token is **not** read from the sheet; set `JIRA_TOKEN` in the environment.

## Bugzilla to Jira field mapping

When migrating from Bugzilla, use these mappings for configuration and JQL:

| Bugzilla | Jira Cloud | Notes |
|----------|------------|--------|
| Version | Affects Version (`affectedVersion`) | Reporter-set; version the bug affects. |
| Target Release | Target Version (custom) | Engineer-set; version the fix is aimed at. |
| Fixed In Version | Fix Version (`fixVersions`) | Set when the fix is released. |
| Fixed In Build | Fixed In Version | Build that contains the fix. |
| Blocker+ | Release Blocker = Approved | |
| Blocker? | Release Blocker = Proposed | |
| Blocker- | Release Blocker = Rejected | Not used in open-blocker queries. |
| **Severity** (reporter) | **Severity** | Urgent → Critical, High → Important, Medium → Moderate, Low → Low. |
| **Priority** (team lead) | **Priority** | Urgent → Critical, High → Major, Medium → Trivial, Low → Minor. |

**Components:** Jira has no subcomponents; Bugzilla subcomponents are flattened (e.g. `Documentation / Administration Guide`). Use `JIRA_DOCUMENTATION_COMPONENTS` with a comma-separated list of all doc component names if needed.

**Unspecified Severity report:** By default the report uses **priority** (e.g. `Undefined`). Set `JIRA_SEVERITY_FIELD=Severity` to filter by the Jira **Severity** field (reporter-set) instead (bugs with Severity empty or in `JIRA_UNSPECIFIED_SEVERITY_VALUES`).

## Metadata validation

`scripts/arrivals_vs_resolved.py` validates config values against `metadata.json`
before running. To skip validation:

- Pass `--skip-validation`, or
- Set `JIRA_SKIP_METADATA_VALIDATION=true`

## Reports

- `scripts/release_readiness_criteria.py`
- `scripts/arrivals_vs_resolved.py`
- `scripts/pqi_report.py`
- `scripts/blocker_resolution_time.py` (Sheet: `Blocker Resolution Time`)
- `scripts/customer_bugs_release_tracking.py` (Sheet: `Customer Bugs Release Tracking`)
- `scripts/average_qa_score.py` (Sheet: `Average Quality Score`)
- `scripts/tracking_dashboard.py` (Sheet: `QE Tracking Dashboard`)
- `scripts/component_distribution.py` (Sheet: `Component Distribution`)
- `scripts/scale_n_perf_defects.py` (Sheet: `Performance & Scale Blockers`)
- `scripts/action_items.py` (Sheets: `Need Info`, `DocBugs`; other sections HTML only)
- `cephQeInfra/last_24_hour_bugs.py` (HTML only)

## HTML mail reports

- `cephQeInfra/last_24_hour_bugs.py` renders the HTML body for last 24 hours
  Jira arrivals using `html_template/last_24hrs_bugs.html`.
- `scripts/action_items.py` renders HTML action items for Need Info, Doc On QA,
  Test On QA, Unspecified Severity, RBD, and OpenStack DP.

## Jenkins pipelines

Pipelines live under `pipeline/` and run individual reports. Email is sent only
for last-24-hours and action-items pipelines.
Run all core reports:
```
python run_all.py "YOUR SPREADSHEET NAME"
```
