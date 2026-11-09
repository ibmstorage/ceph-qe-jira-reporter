#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on 02 Jan 2024 20:28

Ported from reporter-bugzilla for Jira.
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinja_markdown import MarkdownExtension

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from lib.jira_client import get_jira_client
from lib.jira_queries import (
    IncompleteJiraSearchError,
    _exclude_components_clause,
    _jql_approximate_count,
    search_issues,
)


# Buffered fetch is only used to enrich field payloads for exact-JQL keys.
LAST24_FETCH_BUFFER_MINUTES = 60


def _last_24h_range_utc():
    """Return (start, end) as timezone-aware UTC datetimes for the last 24 hours."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)
    return start, end


def _parse_utc_datetime(value: str) -> datetime:
    """Parse a user-supplied instant as UTC (naive strings are treated as UTC)."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("empty datetime")
    # ISO-8601 (e.g. 2026-04-26T02:05:00Z or +00:00)
    if raw.endswith("Z") and "T" in raw:
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        dt = None
    if dt is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        raise ValueError(
            f"Could not parse datetime {value!r}; use e.g. 2026-04-26 02:05 or 2026-04-26T02:05:00Z"
        )
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _creation_range_utc():
    """Rolling last 24h, unless LAST_24H_BUGS_START_UTC and LAST_24H_BUGS_END_UTC are both set."""
    env_start = os.environ.get("LAST_24H_BUGS_START_UTC", "").strip()
    env_end = os.environ.get("LAST_24H_BUGS_END_UTC", "").strip()
    if env_start and env_end:
        start_dt = _parse_utc_datetime(env_start)
        end_dt = _parse_utc_datetime(env_end)
        if end_dt <= start_dt:
            raise ValueError(
                "LAST_24H_BUGS_END_UTC must be strictly after LAST_24H_BUGS_START_UTC"
            )
        return start_dt, end_dt
    if env_start or env_end:
        raise ValueError(
            "Set both LAST_24H_BUGS_START_UTC and LAST_24H_BUGS_END_UTC for a fixed window, or neither."
        )
    return _last_24h_range_utc()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _jql_window_bounds_utc(start_dt: datetime, end_dt: datetime):
    """Minute-precision bounds used in JQL and post-filtering: [start_floor, end_minute+1m)."""
    start_utc = _as_utc(start_dt)
    end_utc = _as_utc(end_dt)
    start_floor = start_utc.replace(second=0, microsecond=0)
    end_minute = end_utc.replace(second=0, microsecond=0)
    end_exclusive = end_minute + timedelta(minutes=1)
    return start_floor, end_exclusive


def _buffered_range_utc(start_dt: datetime, end_dt: datetime, buffer_minutes: int):
    """Return start/end expanded by +/- buffer minutes for broader API retrieval."""
    return (
        start_dt - timedelta(minutes=buffer_minutes),
        end_dt + timedelta(minutes=buffer_minutes),
    )


def _build_new_arrivals_jql(config, start_dt, end_dt):
    """JQL for bugs created between start_dt and end_dt in the project.

    Returns the filter only (no ORDER BY). Use _navigator_jql() for the Issue Navigator link;
    REST /search/jql uses this core string and sorts issues in Python.

    Embeds the same naive ``yyyy-MM-dd HH:mm`` wall-clock literals as Issue Navigator
    (no timezone conversion). Jira Cloud applies those literals in the viewer's/API user's
    profile timezone — converting them first produced a different absolute window and
    under-counted vs Navigator (e.g. 20 vs 22).

    Does NOT filter by Affects Version so new bugs (often without version set) are included.
    """
    # Minute-precision datetimes: avoid `created <= "… HH:mm"` — on many Cloud sites that is parsed as
    # … HH:mm:00.000, so issues later in the same minute (e.g. :30) are wrongly excluded from the API.
    start_floor, end_exclusive = _jql_window_bounds_utc(start_dt, end_dt)
    start_str = start_floor.strftime("%Y-%m-%d %H:%M")
    end_excl_str = end_exclusive.strftime("%Y-%m-%d %H:%M")
    clauses = [
        f'project = "{config.jira_project}"',
        'issuetype = "Bug"',
        f'created >= "{start_str}" and created < "{end_excl_str}"',
        _exclude_components_clause(config),
    ]
    core = " and ".join(c for c in clauses if c)
    return core


def _navigator_jql(jql_core: str) -> str:
    """ORDER BY for the Issue Navigator link only. Omitted from REST /search/jql — that API can return
    zero rows with ORDER BY in some Jira Cloud cases even when the same JQL works in the browser."""
    return f"{jql_core} ORDER BY created DESC"


def _issues_url(config, jql: str) -> str:
    """Issue Navigator URL (same pattern as cephQeInfra/test_on_qa.py)."""
    return f'{config.server.rstrip("/")}/issues/?jql={quote(jql)}'


def _get_field_id(config, field_name):
    client = get_jira_client(config)
    url = config.server.rstrip("/") + "/rest/api/3/field"
    response = client._session.get(url)
    response.raise_for_status()
    for field in response.json():
        if field.get("name") == field_name:
            return field.get("id")
    return None


def _normalize_field_values(value):
    if value is None:
        return []
    if isinstance(value, list):
        values = value
    else:
        values = [value]
    normalized = []
    for item in values:
        if isinstance(item, str):
            normalized.append(item)
        else:
            item_value = getattr(item, "value", None)
            item_name = getattr(item, "name", None)
            if item_value:
                normalized.append(item_value)
            elif item_name:
                normalized.append(item_name)
    return normalized


def _get_blocker_status(issue, field_id, config):
    if not field_id:
        return ""
    fields = getattr(issue, "fields", None)
    if fields is None:
        return ""
    raw_value = getattr(fields, field_id, None)
    values = _normalize_field_values(raw_value)
    if not values:
        return ""
    if any(value in config.blocker_approved_values for value in values):
        return "+"
    if any(value in config.blocker_proposed_values for value in values):
        return "?"
    return "-"


def _issue_created_sort_key(issue):
    """Sort key for ordering issues by created time (ISO string from Jira API)."""
    raw = getattr(getattr(issue, "fields", None), "created", None)
    if raw is None:
        return ""
    return raw if isinstance(raw, str) else str(raw)


def _extract_target_version(issue, field_name, field_id):
    if not field_name:
        return ""
    fields = getattr(issue, "fields", None)
    if fields is None:
        return ""
    if field_name in {"fixVersion", "Fix Version/s"}:
        fix_versions = getattr(fields, "fixVersions", []) or []
        return ", ".join([v.name for v in fix_versions if getattr(v, "name", "")])
    if field_id:
        raw_value = getattr(fields, field_id, None)
        values = _normalize_field_values(raw_value)
        return ", ".join(values)
    return ""


class Last24HourBugsCls:
    def getLast24HourBugs(self, spreadsheet_name=None, start_dt=None, end_dt=None):
        spreadsheet_name = spreadsheet_name or os.environ.get("SPREADSHEET_NAME")
        if not spreadsheet_name:
            raise ValueError("spreadsheet_name is required")

        config = load_config(spreadsheet_name)
        items = []

        project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        template_dir = os.path.join(project_dir, "html_template")

        target_field_name = config.proposed_version_field
        target_field_id = _get_field_id(config, target_field_name)
        blocker_field_id = _get_field_id(config, config.blocker_field)
        severity_field = (getattr(config, "severity_field", None) or "").strip() or None
        severity_field_id = (
            _get_field_id(config, severity_field) if severity_field else None
        )

        if start_dt is not None and end_dt is not None:
            if end_dt <= start_dt:
                raise ValueError("end_dt must be strictly after start_dt")
        elif start_dt is not None or end_dt is not None:
            raise ValueError("Pass both start_dt and end_dt, or neither")
        else:
            start_dt, end_dt = _creation_range_utc()
        jql_core = _build_new_arrivals_jql(config, start_dt, end_dt)
        fetch_start_dt, fetch_end_dt = _buffered_range_utc(
            start_dt, end_dt, LAST24_FETCH_BUFFER_MINUTES
        )
        fetch_jql_core = _build_new_arrivals_jql(config, fetch_start_dt, fetch_end_dt)
        win_start, win_end_excl = _jql_window_bounds_utc(start_dt, end_dt)
        date_range_str = (
            f"{win_start.strftime('%Y-%m-%d %H:%M')} UTC to "
            f"{win_end_excl.strftime('%Y-%m-%d %H:%M')} UTC (exclusive upper bound)"
        )
        search_fields = []
        if target_field_id:
            search_fields.append(target_field_id)
        if blocker_field_id:
            search_fields.append(blocker_field_id)
        if severity_field:
            search_fields.append(severity_field_id or severity_field)
        extra_fields = search_fields if search_fields else None

        # Exact Navigator JQL is the membership source of truth (same literals as the green link).
        # A ±60m buffered fetch is used only to enrich field payloads for those keys — never to
        # add extra rows. UTC post-filter on buffered hits previously inflated 22 → 23.
        exact_issues = search_issues(
            config,
            jql_core,
            fields=extra_fields,
            verify_complete=True,
        )
        buffered_issues = search_issues(
            config,
            fetch_jql_core,
            fields=extra_fields,
            verify_complete=True,
        )

        def _field_richness(issue):
            fields = getattr(issue, "fields", None)
            if fields is None:
                return 0
            score = 0
            for attr in ("summary", "components", "reporter", "priority", "status", "versions"):
                if getattr(fields, attr, None) is not None:
                    score += 1
            return score

        exact_by_key = {}
        for issue in exact_issues:
            key = getattr(issue, "key", None)
            if key:
                exact_by_key[key] = issue
        for issue in buffered_issues:
            key = getattr(issue, "key", None)
            if not key or key not in exact_by_key:
                continue
            if _field_richness(issue) > _field_richness(exact_by_key[key]):
                exact_by_key[key] = issue

        issues = list(exact_by_key.values())
        issues.sort(key=_issue_created_sort_key, reverse=True)
        print(
            f"last_24h search: exact={len(exact_issues)} buffered={len(buffered_issues)} "
            f"table={len(issues)}",
            file=sys.stderr,
        )
        if not issues and (exact_issues or buffered_issues):
            raise RuntimeError(
                f"Fetched issues but table is empty; refusing empty report. JQL: {jql_core}"
            )

        # Cross-check the Navigator (unbuffered) window so a short table cannot ship silently.
        client = get_jira_client(config)
        approx_core = _jql_approximate_count(client, config, jql_core)
        if approx_core is not None and len(issues) < approx_core:
            print(
                f"Incomplete results: table has {len(issues)} bugs but Jira approximate-count "
                f"for the report window is ~{approx_core}. Refusing to send a short mail.",
                file=sys.stderr,
            )
            raise IncompleteJiraSearchError(jql_core, len(issues), approx_core)
        if approx_core is None and len(exact_issues) == 0 and len(issues) == 0:
            print(
                "Warning: exact-window search returned 0 issues and approximate-count "
                "was unavailable; table may be incomplete vs Issue Navigator.",
                file=sys.stderr,
            )

        for issue in issues:
            fld = getattr(issue, "fields", None)
            reporter = ""
            if fld is not None and getattr(fld, "reporter", None):
                rep = fld.reporter
                reporter = getattr(rep, "displayName", None) or getattr(
                    rep, "emailAddress", ""
                )
            components = getattr(fld, "components", []) or [] if fld else []
            component = components[0].name if components else ""
            priority = getattr(fld, "priority", None) if fld else None
            priority_name = getattr(priority, "name", "") if priority else ""
            severity_val = ""
            if fld is not None and (severity_field_id or severity_field):
                sf = (
                    getattr(fld, severity_field_id, None)
                    if severity_field_id
                    else getattr(fld, severity_field, None)
                )
                if sf is not None:
                    severity_val = (
                        getattr(sf, "value", None)
                        or getattr(sf, "name", None)
                        or str(sf)
                    )

            versions = getattr(fld, "versions", []) or [] if fld else []
            affected_version = ", ".join([v.name for v in versions if getattr(v, "name", "")])
            fix_versions = getattr(fld, "fixVersions", []) or [] if fld else []
            fix_version = ", ".join([v.name for v in fix_versions if getattr(v, "name", "")])
            target_release = _extract_target_version(
                issue, target_field_name, target_field_id
            )
            blocker_status = _get_blocker_status(issue, blocker_field_id, config)

            st = getattr(fld, "status", None) if fld else None
            status_name = getattr(st, "name", "") if st else ""

            an_item = dict(
                bug_id=getattr(issue, "key", "") or "",
                summary=getattr(fld, "summary", "") if fld else "",
                reporter=reporter,
                status=status_name,
                component=component,
                priority=priority_name,
                severity=severity_val,
                is_Blocker=blocker_status,
                version=affected_version,
                fix_version=fix_version,
                target_release=target_release,
            )
            items.append(an_item)

        jinja_env = Environment(
            extensions=[MarkdownExtension],
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )
        template = jinja_env.get_template("last_24hrs_bugs.html")
        html = template.render(
            items=items,
            jira_server=config.server,
            date_range=date_range_str,
            jql_issues_url=_issues_url(config, _navigator_jql(jql_core)),
        )
        return html


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Emit HTML for bugs created in a UTC window: default last 24 hours, "
            "or a fixed range via --start-utc/--end-utc or env vars."
        )
    )
    parser.add_argument(
        "spreadsheet",
        nargs="?",
        default=None,
        help="Dashboard Google Sheet name (or set SPREADSHEET_NAME)",
    )
    parser.add_argument(
        "--start-utc",
        metavar="WHEN",
        help='Fixed window start (UTC), e.g. "2026-04-26 02:05". Requires --end-utc.',
    )
    parser.add_argument(
        "--end-utc",
        metavar="WHEN",
        help='Fixed window end (UTC), e.g. "2026-04-27 02:05". Requires --start-utc.',
    )
    args = parser.parse_args()
    spreadsheet = args.spreadsheet or os.environ.get("SPREADSHEET_NAME")
    win_start = win_end = None
    if args.start_utc or args.end_utc:
        if not (args.start_utc and args.end_utc):
            parser.error("--start-utc and --end-utc must be used together")
        win_start = _parse_utc_datetime(args.start_utc)
        win_end = _parse_utc_datetime(args.end_utc)

    try:
        last_24_hour_bugs_obj = Last24HourBugsCls()
        last_24_hour_html = last_24_hour_bugs_obj.getLast24HourBugs(
            spreadsheet_name=spreadsheet,
            start_dt=win_start,
            end_dt=win_end,
        )
    except IncompleteJiraSearchError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(last_24_hour_html)
