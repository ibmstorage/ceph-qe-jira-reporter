# Local credentials: Jira API token and Google service account

This guide helps new contributors run jira-reporter scripts on a laptop or VM. The same environment variables are what Jenkins supplies via credentials (see `pipeline/*.groovy`).

You need:

1. **Jira Cloud** — an API token and the **same** Atlassian account email the token belongs to (usually read from the dashboard sheet cell `H7`, or `JIRA_EMAIL` / `metadata.json`).
2. **Google Sheets** — a **service account** JSON key file and the spreadsheet shared with that service account (Editor).

---

## 1. Jira Cloud API token

### Create the token

1. Sign in to Atlassian with the account that should run the reports (often a shared QE or automation user, per your org’s policy).
2. Open **Atlassian account** security:  
   [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
3. Select **Create API token**, give it a label (e.g. `jira-reporter-local`), create it, and **copy the token immediately**. You cannot view it again later; revoke and create a new one if lost.

### How the reporter uses it

- The scripts read **`JIRA_TOKEN`** from the environment only (never from the sheet).
- The Jira **user email** must match the account that created the token. This project loads email from:
  - **`H7`** on the **Dashboard Configuration** worksheet, or
  - **`JIRA_EMAIL`** if you set it in the environment, or
  - **`metadata.json`** (`jira_email`) when used.

The client uses **`basic_auth=(email, api_token)`** when an email is present (`lib/jira_client.py`), which is the standard Jira Cloud pattern.

### Shell setup (each terminal, or your profile)

```bash
export JIRA_TOKEN="paste_your_api_token_here"
# Optional if H7 is empty or you want to override:
# export JIRA_EMAIL="your.name@company.com"
```

**Security:** Do not commit the token, paste it into tickets, or log it. Prefer a password manager or your OS keychain; for automation, use your CI secret store.

---

## 2. Google Cloud service account (Sheets + Drive)

The code uses **gspread** with a service account JSON key (`lib/gsheets.py`). The default file path is `~/.gapi/google_api_secret.json`, or set **`GSPREAD_SERVICE_ACCOUNT`** to any path you prefer.

### 2.1 Create a project and enable APIs

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select or create a **project** (e.g. `jira-reporter-local`).
2. Go to **APIs & Services** → **Library**.
3. Enable:
   - **Google Sheets API**
   - **Google Drive API** (used when opening spreadsheets by title/name with gspread)

### 2.2 Create a service account and key

1. **IAM & Admin** → **Service Accounts** → **Create service account**.
2. Give it a name (e.g. `jira-reporter-sheets`); project-level roles can stay minimal if you only access Sheets by sharing (many teams use no extra IAM roles beyond what’s needed to create keys).
3. Open the service account → **Keys** → **Add key** → **JSON** and download the file.
4. Note the **`client_email`** inside the JSON (looks like `something@PROJECT_ID.iam.gserviceaccount.com`). You will share each spreadsheet with this address.

### 2.3 Share your spreadsheet with the service account

1. Open the Google Sheet in a browser (as an owner or editor).
2. **Share** → add the **`client_email`** from the JSON → role **Editor** → send/confirm.

Without this step, API calls fail with permission errors even if the JSON is valid.

### 2.4 Point the reporter at the key file

```bash
# Option A: default path (create directory if needed)
mkdir -p ~/.gapi
mv ~/Downloads/your-project-xxxxx.json ~/.gapi/google_api_secret.json
chmod 600 ~/.gapi/google_api_secret.json

# Option B: explicit path (good for multiple projects)
export GSPREAD_SERVICE_ACCOUNT="/absolute/path/to/service-account.json"
```

**Security:** Treat the JSON like a password. Do not commit it; add `*.json` key paths to `.gitignore` if you keep keys under the repo tree (not recommended). Restrict file permissions (`chmod 600`).

---

## 3. One-shot check before running reports

From the repo root, with venv activated:

```bash
export JIRA_TOKEN="…"
# export JIRA_EMAIL="…"   # if needed
export GSPREAD_SERVICE_ACCOUNT="${GSPREAD_SERVICE_ACCOUNT:-$HOME/.gapi/google_api_secret.json}"

python scripts/release_readiness_criteria.py "YOUR EXACT SPREADSHEET TITLE"
```

- **Spreadsheet title** must match what you see in Google Sheets (the document name), including spaces and punctuation.
- If Jira fails: check token not expired/revoked, email matches token, `E7` / `H7` in **Dashboard Configuration** match your Jira Cloud site and user.
- If Sheets fails: APIs enabled, JSON path correct, spreadsheet shared with **`client_email`**, and the account still has Editor access.

---

## 4. Optional: `.env` file (not loaded automatically)

This repository does not load a `.env` file by itself. If you use [direnv](https://direnv.net/) or a small wrapper, you can keep variables in a **gitignored** `.env` and export them in your shell.

---

## 5. Mapping to Jenkins

In `pipeline/*.groovy`, the same variables appear as:

- `JIRA_TOKEN` — from a Jenkins secret text credential (e.g. `atlassian-jira-token`).
- `GSPREAD_SERVICE_ACCOUNT` — path to a **file** credential containing the service account JSON (e.g. `gcp-service-account`), passed via `withEnv(["GSPREAD_SERVICE_ACCOUNT=..."])`.

Local setup mirrors that: token in env, path to the JSON file in `GSPREAD_SERVICE_ACCOUNT` or default path under `~/.gapi/`.
