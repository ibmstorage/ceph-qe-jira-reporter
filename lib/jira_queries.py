from types import SimpleNamespace
import time
import warnings

from jira.exceptions import JIRAError

from config.settings import JiraConfig
from lib.jira_client import get_jira_client
from lib.retry import retry


def filter_by_status(issues, statuses):
    if isinstance(statuses, str):
        statuses = [statuses]
    return [issue for issue in issues if issue.fields.status.name in statuses]


DEFAULT_FIELDS = [
    "summary",
    "status",
    "components",
    "fixVersions",
    "versions",
    "labels",
    "issuetype",
    "project",
    "created",
    "reporter",
    "priority",
    "resolutiondate",
]

# JQL clause to restrict to bugs only; used so reporter counts align with Jira Cloud (type = Bug).
_ISSUETYPE_BUG = 'issuetype = "Bug"'

# Cache for Target Version field id per (server, field_name) so we only look up once per process
_target_version_field_id_cache = {}


def _ensure_target_version_in_fields(config: JiraConfig, field_list: list):
    """Append Target Version field id to field_list so the API returns it; uses cache to avoid repeated lookups."""
    field_name = config.proposed_version_field or "Target Version"
    cache_key = (config.server, field_name)
    if cache_key not in _target_version_field_id_cache:
        from cephQeInfra.action_items_utils import get_field_id
        _target_version_field_id_cache[cache_key] = get_field_id(config, field_name)
    field_id = _target_version_field_id_cache[cache_key]
    if field_id and field_id not in field_list:
        field_list.append(field_id)


def _jql_raw_to_obj(value):
    """Map Jira search JSON issue dict to SimpleNamespace (supports non-identifier field keys)."""
    if isinstance(value, dict):
        out = SimpleNamespace()
        for k, v in value.items():
            key = str(k) if not isinstance(k, str) else k
            if not key:
                continue
            try:
                setattr(out, key, _jql_raw_to_obj(v))
            except (TypeError, ValueError):
                pass
        return out
    if isinstance(value, list):
        return [_jql_raw_to_obj(item) for item in value]
    return value


class IncompleteJiraSearchError(RuntimeError):
    """Raised when verify_complete search retrieves fewer issues than approximate-count."""

    def __init__(self, jql: str, retrieved: int, expected: int):
        self.jql = jql
        self.retrieved = retrieved
        self.expected = expected
        super().__init__(
            f"JQL search expected ~{expected} issues (approximate count) but retrieved "
            f"{retrieved}; refusing incomplete results. JQL: {jql}"
        )


def _jql_approximate_count(client, config: JiraConfig, jql: str):
    """Return approximate issue count for JQL, or None if the endpoint is unavailable."""
    url = config.server.rstrip("/") + "/rest/api/3/search/approximate-count"
    response = client._session.post(url, json={"jql": jql})
    if response.status_code != 200:
        return None
    data = response.json()
    if not isinstance(data, dict):
        return None
    c = data.get("count")
    return int(c) if c is not None else None


def _jql_fetch_page(
    client, config: JiraConfig, jql, field_list, expand, page_cap, use_post: bool, next_token
):
    """Fetch one page from GET or POST /rest/api/3/search/jql.

    Returns (issue_objs, next_page_token, is_last).
    """
    url = config.server.rstrip("/") + "/rest/api/3/search/jql"
    fields_csv = ",".join(field_list)
    if use_post:
        body = {"jql": jql, "maxResults": page_cap, "fields": field_list}
        if expand:
            body["expand"] = expand
        if next_token:
            body["nextPageToken"] = next_token
        response = client._session.post(url, json=body)
    else:
        params = {
            "jql": jql,
            "maxResults": page_cap,
            "fields": fields_csv,
        }
        if expand:
            params["expand"] = expand
        if next_token:
            params["nextPageToken"] = next_token
        response = client._session.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    issues = [_jql_raw_to_obj(raw) for raw in payload.get("issues", [])]
    return issues, payload.get("nextPageToken"), payload.get("isLast")


def _jql_paginate_enhanced(client, config: JiraConfig, jql, field_list, expand, page_cap, use_post: bool):
    """Fetch all pages from GET or POST /rest/api/3/search/jql (Jira Cloud enhanced search).

    A page is treated as final only when ``isLast`` is true, the page is empty, or
    ``nextPageToken`` is absent *and* a fresh first-page probe adds no new keys.
    Under-filled pages without ``isLast`` are no longer assumed complete.
    """
    seen = {}
    next_token = None
    while True:
        issues, next_token, is_last = _jql_fetch_page(
            client, config, jql, field_list, expand, page_cap, use_post, next_token
        )
        for issue in issues:
            key = getattr(issue, "key", None)
            if key:
                seen[key] = issue

        if is_last is True:
            break
        if next_token:
            continue
        if len(issues) == 0:
            break

        # No token and not explicitly last — probe a fresh first page for keys we missed.
        # Cloud sometimes returns an under-filled page without nextPageToken/isLast while
        # more matching issues exist; a second unpaginated fetch can surface them.
        probe_new = False
        probe_token = None
        for probe_post in (False, True):
            probe_issues, probe_token, probe_last = _jql_fetch_page(
                client, config, jql, field_list, expand, page_cap, probe_post, None
            )
            for issue in probe_issues:
                key = getattr(issue, "key", None)
                if key and key not in seen:
                    seen[key] = issue
                    probe_new = True
            if probe_last is True:
                return list(seen.values())
            if probe_token:
                next_token = probe_token
                use_post = probe_post
                break
        if next_token:
            continue
        if not probe_new:
            break
        # New keys found but still no pagination token — stop to avoid an infinite loop.
        warnings.warn(
            "Jira search/jql returned additional issues on probe without nextPageToken or "
            "isLast=true; results may still be incomplete. Narrow JQL or report to Atlassian "
            "if persistent.",
            RuntimeWarning,
            stacklevel=2,
        )
        break

    return list(seen.values())


@retry(JIRAError, 5, 10)
def search_issues(config: JiraConfig, jql, expand=None, fields=None, verify_complete: bool = False):
    client = get_jira_client(config)
    page_size = config.max_results or 1000

    # Jira Cloud removed GET /rest/api/3/search (410); use enhanced JQL search only.
    # See https://developer.atlassian.com/changelog/#CHANGE-2046
    field_list = list(DEFAULT_FIELDS)
    _ensure_target_version_in_fields(config, field_list)
    if fields:
        if isinstance(fields, str):
            extra_fields = [value for value in fields.split(",") if value]
        else:
            extra_fields = list(fields)
        for value in extra_fields:
            if value not in field_list:
                field_list.append(value)

    # Enhanced search commonly caps page size (often 100); larger values may be clamped.
    page_cap = min(page_size, 100)
    all_issues = _jql_paginate_enhanced(
        client, config, jql, field_list, expand, page_cap, use_post=False
    )
    # GET pagination sometimes returns an under-filled page without nextPageToken while more
    # issues exist. When verify_complete (last-24h mail): union GET+POST, key-only pass,
    # retry with backoff until approximate-count matches (or raise).
    if verify_complete:
        merged = {}
        for issue in all_issues:
            key = getattr(issue, "key", None)
            if key:
                merged[key] = issue

        # Minimal fields for a second pass that may surface keys dropped from heavy payloads.
        key_fields = ["key", "created", "summary", "status", "issuetype", "project"]

        def _field_richness(issue):
            fields = getattr(issue, "fields", None)
            if fields is None:
                return 0
            score = 0
            for attr in ("summary", "components", "reporter", "priority", "status", "versions"):
                if getattr(fields, attr, None) is not None:
                    score += 1
            return score

        def _merge_batch(batch):
            for issue in batch:
                key = getattr(issue, "key", None)
                if not key:
                    continue
                existing = merged.get(key)
                if existing is None or _field_richness(issue) >= _field_richness(existing):
                    merged[key] = issue

        def _merge_next_round():
            for use_post in (False, True):
                batch = _jql_paginate_enhanced(
                    client, config, jql, field_list, expand, page_cap, use_post=use_post
                )
                _merge_batch(batch)
            for use_post in (False, True):
                batch = _jql_paginate_enhanced(
                    client, config, jql, key_fields, expand, page_cap, use_post=use_post
                )
                _merge_batch(batch)

        max_rounds = 5
        approx = None
        for attempt in range(max_rounds):
            _merge_next_round()
            approx = _jql_approximate_count(client, config, jql)
            if approx is None or len(merged) >= approx:
                break
            time.sleep(2 * (attempt + 1))

        # Re-fetch full fields if any key-only stubs remain (missing typical report fields).
        if any(_field_richness(issue) < 3 for issue in merged.values()):
            full_again = _jql_paginate_enhanced(
                client, config, jql, field_list, expand, page_cap, use_post=True
            )
            _merge_batch(full_again)

        all_issues = list(merged.values())
        if approx is not None and len(all_issues) < approx:
            raise IncompleteJiraSearchError(jql, len(all_issues), approx)

    return all_issues


def _quoted_list(items):
    quoted = [f'"{item}"' for item in items]
    return "(" + ", ".join(quoted) + ")"


def _target_clause(config: JiraConfig):
    """Strict filter: only issues whose Target Version (or configured field) equals the configured value. Issues with empty Target Version are excluded."""
    if config.proposed_version_field and config.target_version:
        field = config.proposed_version_field
        return f'"{field}" = "{config.target_version}"'
    return ""


def _doc_components_list(config: JiraConfig):
    """List of component names treated as documentation (flattened or single)."""
    if getattr(config, "documentation_components", None):
        return config.documentation_components
    if config.documentation_component:
        return [config.documentation_component]
    return []


def _excluded_components_list(config: JiraConfig):
    """Combined list of components to exclude from report queries: documentation + exclude_components (e.g. Jira_Change_Requests)."""
    doc = _doc_components_list(config)
    extra = getattr(config, "exclude_components", None) or []
    return list(dict.fromkeys(doc + extra))


def _exclude_components_clause(config: JiraConfig):
    """Exclude documentation and other configured components (e.g. Jira_Change_Requests) from report queries."""
    comps = _excluded_components_list(config)
    if not comps:
        return ""
    if len(comps) == 1:
        return f'component != "{comps[0]}"'
    return f"component not in {_quoted_list(comps)}"


def _exclude_components_only_clause(config: JiraConfig):
    """Exclude only exclude_components (e.g. Jira_Change_Requests, Jira_Issues), not documentation. For Component Distribution to match Cloud."""
    comps = getattr(config, "exclude_components", None) or []
    if not comps:
        return ""
    if len(comps) == 1:
        return f'component != "{comps[0]}"'
    return f"component not in {_quoted_list(comps)}"


def _documentation_only_clause(config: JiraConfig):
    """JQL clause for issues that are documentation-only (component in doc list or = single)."""
    doc_list = _doc_components_list(config)
    if not doc_list:
        return ""
    if len(doc_list) == 1:
        return f'component = "{doc_list[0]}"'
    return f"component in {_quoted_list(doc_list)}"


def _resolved_statuses_clause(config: JiraConfig):
    statuses = _quoted_list([config.qe_status, config.verified_status])
    return f"status in {statuses}"


def _blocker_arrival_values(config: JiraConfig):
    values = config.blocker_proposed_values + config.blocker_approved_values
    unique = list(dict.fromkeys(values))
    return _quoted_list(unique)


def _exclude_rejected_blocker_clause(config: JiraConfig):
    """Exclude Rejected (Blocker-) from blocker queries when configured."""
    rejected = getattr(config, "blocker_rejected_values", None) or []
    if not rejected:
        return ""
    return f'"{config.blocker_field}" not in {_quoted_list(rejected)}'


def _join_clauses(clauses):
    return " and ".join([clause for clause in clauses if clause])


def _reporter_not_in_clause(account_ids):
    """JQL ``reporter not in (...)`` for Cloud accountIds; empty if no ids."""
    ids = [a for a in (account_ids or []) if a]
    if not ids:
        return ""

    def _esc(s):
        return (s or "").replace("\\", "\\\\").replace('"', '\\"')

    inner = ", ".join(f'"{_esc(aid)}"' for aid in ids)
    return f"reporter not in ({inner})"


def _pqi_dev_backlog_status_clauses(config: JiraConfig):
    statuses = _quoted_list(list(dict.fromkeys(config.open_statuses + ["ON_DEV"])))
    return [
        f'project = "{config.jira_project}"',
        _ISSUETYPE_BUG,
        _target_clause(config),
        _exclude_components_clause(config),
        f"status in {statuses}",
    ]


def jql_dev_backlog(config: JiraConfig) -> str:
    """Dev backlog JQL (PQI dev columns are subsets by status)."""
    return _join_clauses(_pqi_dev_backlog_status_clauses(config))


def jql_pqi_dev_status(config: JiraConfig, status_name: str) -> str:
    """Single-status slice of dev backlog (e.g. New, ASSIGNED) for PQI sheet links."""
    return _join_clauses(
        _pqi_dev_backlog_status_clauses(config) + [f'status = "{status_name}"']
    )


def get_dev_backlog(config: JiraConfig):
    """Dev backlog: same scope as Bugzilla PQI — filtered by Target Version (target_release)."""
    return search_issues(config, jql_dev_backlog(config))


def jql_qe_backlog(config: JiraConfig) -> str:
    """QE backlog JQL for PQI ON_QA count / Issue Navigator."""
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f'status = "{config.qe_status}"',
        ]
    )


def get_qe_backlog(config: JiraConfig, expand_changelog=True):
    """QE backlog: same scope as Bugzilla PQI — filtered by Target Version (target_release)."""
    query = jql_qe_backlog(config)
    expand = "changelog" if expand_changelog else ""
    return search_issues(config, query, expand=expand)


def get_open_blockers(config: JiraConfig):
    """Open issues with Release Blocker field = Approved (custom field). Use get_open_blockers_by_priority for Cloud (priority = Blocker)."""
    statuses = _quoted_list(config.open_statuses)
    blocker_values = _quoted_list(config.blocker_approved_values)
    query = _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f"status in {statuses}",
            f'"{config.blocker_field}" in {blocker_values}',
            _exclude_rejected_blocker_clause(config),
        ]
    )
    return search_issues(config, query)


def jql_open_blockers_by_priority(config: JiraConfig) -> str:
    """Open bugs with priority = Blocker (Cloud open blockers)."""
    statuses = list(dict.fromkeys(config.open_statuses + ["In Progress"]))
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f"status in {_quoted_list(statuses)}",
            'priority = "Blocker"',
        ]
    )


def get_open_blockers_by_priority(config: JiraConfig):
    """Open bugs with priority = Blocker. Matches Cloud 'open blockers' (status in open + In Progress, priority = Blocker)."""
    return search_issues(config, jql_open_blockers_by_priority(config))


def jql_open_candidate_blockers(config: JiraConfig) -> str:
    statuses = _quoted_list(config.open_statuses)
    blocker_values = _quoted_list(config.blocker_proposed_values)
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f"status in {statuses}",
            f'"{config.blocker_field}" in {blocker_values}',
            _exclude_rejected_blocker_clause(config),
        ]
    )


def get_open_candidate_blockers(config: JiraConfig):
    return search_issues(config, jql_open_candidate_blockers(config))


def jql_critical_bugs(config: JiraConfig) -> str:
    statuses = _quoted_list(config.open_statuses)
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f"status in {statuses}",
            'priority = "Critical"',
        ]
    )


def get_critical_bugs(config: JiraConfig):
    return search_issues(config, jql_critical_bugs(config))


def jql_regression_bugs(config: JiraConfig) -> str:
    statuses = _quoted_list(config.open_statuses)
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f"status in {statuses}",
            f'labels = "{config.regression_label}"',
        ]
    )


def get_regression_bugs(config: JiraConfig):
    return search_issues(config, jql_regression_bugs(config))


def jql_untriaged_bugs(config: JiraConfig) -> str:
    """Bugs with no Target Version set (untriaged). Matches Cloud: Target Version is EMPTY, status != Closed."""
    target_version_field = config.proposed_version_field or "Target Version"
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            f'"{target_version_field}" is EMPTY',
            _exclude_components_clause(config),
            'status != "Closed"',
        ]
    )


def get_untriaged_bugs(config: JiraConfig):
    """Bugs with no Target Version set (untriaged). Matches Cloud: Target Version is EMPTY, status != Closed."""
    return search_issues(config, jql_untriaged_bugs(config))


def jql_doc_bugs(config: JiraConfig) -> str:
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _documentation_only_clause(config),
        ]
    )


def get_doc_bugs(config: JiraConfig):
    return search_issues(config, jql_doc_bugs(config))


def get_overall_backlog(config: JiraConfig):
    statuses = list(dict.fromkeys(config.open_statuses + ["ON_DEV"]))
    query = _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f"status in {_quoted_list(statuses)}",
        ]
    )
    return search_issues(config, query)


def get_component_distribution_backlog(config: JiraConfig):
    """Backlog for Component Distribution: exclude only Jira_Change_Requests, Jira_Issues (not documentation). Matches Cloud."""
    from cephQeInfra.action_items_utils import get_field_id

    statuses = list(dict.fromkeys(config.open_statuses + ["ON_DEV"]))
    query = _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_only_clause(config),
            f"status in {_quoted_list(statuses)}",
        ]
    )
    severity_name = (getattr(config, "severity_field", None) or "").strip() or "Severity"
    sev_id = get_field_id(config, severity_name)
    extra = sev_id or severity_name
    return search_issues(config, query, fields=[extra])


def get_all_bugs_in_version(config: JiraConfig):
    done_resolutions = _quoted_list(config.done_resolutions)
    query = _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            f'"{config.affected_version_field}" = "{config.affected_version}"',
            _exclude_components_clause(config),
            f"(resolution is EMPTY or resolution in {done_resolutions})",
        ]
    )
    return search_issues(config, query)


def get_all_regression_bugs(config: JiraConfig):
    clauses = [
        f'project = "{config.jira_project}"',
        _ISSUETYPE_BUG,
        f'"{config.affected_version_field}" = "{config.affected_version}"',
        f'labels = "{config.regression_label}"',
        _exclude_components_clause(config),
    ]
    query = _join_clauses(clauses)
    return search_issues(config, query)


def get_all_bugs_targeted_to_version(config: JiraConfig, expand_changelog=True):
    done_resolutions = _quoted_list(config.done_resolutions)
    query = _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f"(resolution is EMPTY or resolution in {done_resolutions})",
        ]
    )
    expand = "changelog" if expand_changelog else ""
    return search_issues(config, query, expand=expand)


def get_all_verified_bugs(config: JiraConfig, expand_changelog=True):
    done_resolutions = _quoted_list(config.done_resolutions)
    query = _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f'(status = "{config.verified_status}" '
            f'or (status = "CLOSED" and resolution in {done_resolutions}))',
        ]
    )
    expand = "changelog" if expand_changelog else ""
    return search_issues(config, query, expand=expand)


def _status_changed_after_clause(status_value, changed_from, changed_to):
    """Build JQL for 'status changed TO X AFTER ... [BEFORE ...]'. Use startOfDay(-1d) for 'last day' to match Jira Cloud."""
    if changed_from == "startOfDay(-1d)" and (not changed_to or not str(changed_to).strip()):
        return f'status changed TO "{status_value}" AFTER startOfDay(-1d)'
    return f'status changed TO "{status_value}" AFTER "{changed_from}" BEFORE "{changed_to}"'


def jql_verified_bugs(config: JiraConfig, changed_from="-1w", changed_to="-0d") -> str:
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            _status_changed_after_clause(config.verified_status, changed_from, changed_to),
        ]
    )


def get_verified_bugs(config: JiraConfig, changed_from="-1w", changed_to="-0d"):
    return search_issues(
        config, jql_verified_bugs(config, changed_from, changed_to)
    )


def jql_resolved_bugs(config: JiraConfig, changed_from="-1w", changed_to="-0d") -> str:
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            _resolved_statuses_clause(config),
            _status_changed_after_clause(config.qe_status, changed_from, changed_to),
        ]
    )


def get_resolved_bugs(config: JiraConfig, changed_from="-1w", changed_to="-0d"):
    return search_issues(
        config, jql_resolved_bugs(config, changed_from, changed_to)
    )


def _created_range_clause(changed_from, changed_to):
    """Build JQL for created date range. Use startOfDay(-1d) for 'last day' to match Jira Cloud."""
    if changed_from == "startOfDay(-1d)" and (not changed_to or not str(changed_to).strip()):
        return "created >= startOfDay(-1d)"
    return f'created >= "{changed_from}" and created <= "{changed_to}"'


def jql_new_arrivals(
    config: JiraConfig, changed_from="-1w", changed_to="-0d"
) -> str:
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            f'"{config.affected_version_field}" = "{config.affected_version}"',
            _exclude_components_clause(config),
            _created_range_clause(changed_from, changed_to),
        ]
    )


def get_new_arrivals(config: JiraConfig, changed_from="-1w", changed_to="-0d"):
    return search_issues(
        config, jql_new_arrivals(config, changed_from, changed_to)
    )


def get_blocker_arrivals(config: JiraConfig, changed_from="-1w", changed_to="-0d"):
    blocker_values = _blocker_arrival_values(config)
    query = _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            f'"{config.affected_version_field}" = "{config.affected_version}"',
            _exclude_components_clause(config),
            _created_range_clause(changed_from, changed_to),
            f'"{config.blocker_field}" in {blocker_values}',
            _exclude_rejected_blocker_clause(config),
        ]
    )
    return search_issues(config, query)


def jql_new_blockers_by_priority(
    config: JiraConfig, changed_from="-1w", changed_to="-0d"
) -> str:
    """JQL for new Blocker-priority bugs in created range (Arrivals vs Resolved column)."""
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            f'"{config.affected_version_field}" = "{config.affected_version}"',
            _exclude_components_clause(config),
            'priority = "Blocker"',
            _created_range_clause(changed_from, changed_to),
        ]
    )


def get_new_blockers_by_priority(config: JiraConfig, changed_from="-1w", changed_to="-0d"):
    """New bugs with priority = Blocker created in the range. Matches Cloud 'new blockers' (priority = Blocker, created >= startOfDay(-1d))."""
    return search_issues(
        config, jql_new_blockers_by_priority(config, changed_from, changed_to)
    )


def _components_clause(components):
    if components:
        return f"component in {_quoted_list(components)}"
    return ""


def _labels_clause(labels):
    if labels:
        return f"labels in {_quoted_list(labels)}"
    return ""


def _needinfo_mail_clauses_and_field(config: JiraConfig):
    """Clauses and API field id for Need Info mail.

    Does not filter by dashboard target version (Need Info bugs may span releases).
    When ``need_info_from_field`` is enabled but no QE team account IDs resolve,
    fall back to the base Need Info query (without the assignee JQL clause).
    """
    from cephQeInfra.action_items_utils import get_field_id
    from lib.jira_user_lookup import resolve_identifiers_to_account_ids
    from lib.team_members import load_qe_team_members

    statuses = _quoted_list(config.needinfo_statuses)
    clauses = [
        f'project = "{config.jira_project}"',
        _ISSUETYPE_BUG,
        _exclude_components_clause(config),
        f"status in {statuses}",
    ]
    field_spec = (getattr(config, "need_info_from_field", None) or "").strip()
    need_info_field_id_for_api = None
    abort_empty = False
    if field_spec:
        members = load_qe_team_members(config.spreadsheet_name)
        account_ids = resolve_identifiers_to_account_ids(config, members)
        if not account_ids:
            import sys

            print(
                "Warning: need_info_from_field is set but no Jira account IDs could be "
                "resolved from the QE team sheet; returning no Need Info issues.",
                file=sys.stderr,
            )
            abort_empty = True
        else:
            if field_spec.startswith("customfield_"):
                need_info_field_id_for_api = field_spec
            else:
                need_info_field_id_for_api = get_field_id(config, field_spec)
                if not need_info_field_id_for_api:
                    raise ValueError(
                        f'Jira field not found for need_info_from_field={field_spec!r}. '
                        "Set JIRA_NEED_INFO_FROM_FIELD to the exact field name or to the "
                        "custom field id (e.g. customfield_12345)."
                    )
            jql_override = (getattr(config, "need_info_jql_field", None) or "").strip()
            if jql_override:
                field_for_jql = jql_override
            elif str(need_info_field_id_for_api).startswith(
                "customfield_"
            ) and field_spec == "Need Info From":
                # Jira Cloud Issue Navigator rejects customfield_… in URLs; JQL autocomplete name.
                field_for_jql = "Need Info From[User Picker (multiple users)]"
            else:
                field_for_jql = need_info_field_id_for_api
            ids_jql = ", ".join(account_ids)
            clauses.append(f'"{field_for_jql}" in ({ids_jql})')
    else:
        # JQL filter off: still fetch the field for mail/sheet "Need Information from" column.
        need_info_field_id_for_api = get_field_id(config, "Need Info From")
    return clauses, need_info_field_id_for_api, abort_empty


def jql_needinfo_bugs(config: JiraConfig) -> str:
    """JQL for Need Info action items (Issue Navigator link). Omits assignee clause if sheet resolves no IDs."""
    clauses, _, _ = _needinfo_mail_clauses_and_field(config)
    return _join_clauses(clauses)


def get_needinfo_bugs(config: JiraConfig):
    clauses, need_info_field_id_for_api, abort_empty = _needinfo_mail_clauses_and_field(
        config
    )
    if abort_empty:
        return []
    query = _join_clauses(clauses)
    extra_fields = [need_info_field_id_for_api] if need_info_field_id_for_api else None
    return search_issues(config, query, expand="changelog", fields=extra_fields)


def jql_doc_on_qa_bugs(config: JiraConfig) -> str:
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _documentation_only_clause(config),
            f'status = "{config.qe_status}"',
        ]
    )


def get_doc_on_qa_bugs(config: JiraConfig):
    query = jql_doc_on_qa_bugs(config)
    return search_issues(config, query, expand="changelog")


def jql_test_on_qa_matrix_bugs(config: JiraConfig) -> str:
    """All ON_QA bugs for the Test on QA matrix (grouped by QE Contact and Fix Version/s)."""
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _exclude_components_clause(config),
            f'status = "{config.qe_status}"',
        ]
    )


def get_test_on_qa_bugs(config: JiraConfig):
    """All bugs in QE testing status. Action Items groups by QE Contact × Fix Version/s."""
    from cephQeInfra.action_items_utils import get_field_id

    query = jql_test_on_qa_matrix_bugs(config)
    qe_name = (getattr(config, "qe_contact_field", None) or "").strip() or "QE Contact"
    qe_field_id = get_field_id(config, qe_name)
    extra = qe_field_id or qe_name
    return search_issues(config, query, fields=[extra, "fixVersions"])


_severity_field_id_cache = {}


def _unspecified_severity_clause(config: JiraConfig, severity_field_id=None):
    """When severity_field is set, filter by Severity. Else fallback to priority.
    Prefer JIRA_SEVERITY_JQL_FIELD when set. If Jira returns customfield_… for field name
    ``Severity``, use ``Severity[Dropdown]`` in JQL so Issue Navigator links work; otherwise
    field id or display name."""
    if getattr(config, "severity_field", None):
        jql_name = (getattr(config, "severity_jql_field", None) or "").strip()
        if jql_name:
            field = jql_name
        elif severity_field_id and str(severity_field_id).startswith("customfield_"):
            if (config.severity_field or "").strip() == "Severity":
                field = "Severity[Dropdown]"
            else:
                field = severity_field_id   
        else:
            field = severity_field_id or config.severity_field
        if getattr(config, "unspecified_severity_values", None):
            vals = _quoted_list(config.unspecified_severity_values)
            return f'("{field}" is EMPTY or "{field}" in {vals})'
        return f'"{field}" is EMPTY'
    if config.unspecified_priorities:
        return f"priority in {_quoted_list(config.unspecified_priorities)}"
    return "priority is EMPTY"


def jql_unspecified_severity_bugs(config: JiraConfig) -> str:
    statuses = _quoted_list(config.open_statuses)
    severity_field = getattr(config, "severity_field", None)
    severity_field_id = None
    if severity_field:
        cache_key = (config.server, severity_field)
        if cache_key not in _severity_field_id_cache:
            from cephQeInfra.action_items_utils import get_field_id
            _severity_field_id_cache[cache_key] = get_field_id(config, severity_field)
        severity_field_id = _severity_field_id_cache[cache_key]
    severity_clause = _unspecified_severity_clause(config, severity_field_id=severity_field_id)
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f"status in {statuses}",
            severity_clause,
        ]
    )


def get_unspecified_severity_bugs(config: JiraConfig):
    """Bugs with empty/unspecified Severity (or priority) in open statuses.
    Set JIRA_SEVERITY_FIELD to the Severity field name (e.g. 'Severity') so the script
    filters by that field; otherwise it uses Priority. Only statuses in open_statuses
    are included—if you need In Progress, ON_QA, etc., add them to JIRA_OPEN_STATUSES."""
    query = jql_unspecified_severity_bugs(config)
    severity_field = getattr(config, "severity_field", None)
    severity_field_id = None
    if severity_field:
        cache_key = (config.server, severity_field)
        severity_field_id = _severity_field_id_cache.get(cache_key)
    extra_fields = None
    if severity_field:
        extra_fields = severity_field_id or severity_field
    return search_issues(config, query, fields=extra_fields)


def jql_rbd_action_items(config: JiraConfig, exclude_reporter_account_ids=None) -> str:
    """RBD action-item JQL. When ``exclude_reporter_account_ids`` is set (QE Cloud accountIds),
    appends ``reporter not in (...)`` so the Issue Navigator link matches the mail table."""
    statuses = _quoted_list(config.open_statuses)
    clauses = [
        f'project = "{config.jira_project}"',
        _ISSUETYPE_BUG,
        _target_clause(config),
        _exclude_components_clause(config),
        f"status in {statuses}",
        _components_clause(config.rbd_components),
        _labels_clause(config.rbd_labels),
    ]
    ric = _reporter_not_in_clause(
        sorted(exclude_reporter_account_ids) if exclude_reporter_account_ids else None
    )
    if ric:
        clauses.append(ric)
    return _join_clauses(clauses)


def get_rbd_action_items(config: JiraConfig):
    from cephQeInfra.action_items_utils import get_field_id

    query = jql_rbd_action_items(config)
    severity_name = (getattr(config, "severity_field", None) or "").strip() or "Severity"
    sev_id = get_field_id(config, severity_name)
    extra = sev_id or severity_name
    return search_issues(config, query, fields=[extra])


def jql_openstack_action_items(config: JiraConfig) -> str:
    statuses = _quoted_list(config.open_statuses)
    return _join_clauses(
        [
            f'project = "{config.jira_project}"',
            _ISSUETYPE_BUG,
            _target_clause(config),
            _exclude_components_clause(config),
            f"status in {statuses}",
            _components_clause(config.openstack_components),
            _labels_clause(config.openstack_labels),
        ]
    )


def get_openstack_action_items(config: JiraConfig):
    query = jql_openstack_action_items(config)
    return search_issues(config, query)


def jql_unassigned_qe_contact_bugs(
    config: JiraConfig,
    qe_field_for_jql: str,
    target_version_jql_field: str = "",
    target_version: str = "",
) -> str:
    """Bugs with empty QE Contact (New / ASSIGNED / ON_QA).

    When ``target_version`` is set (and a JQL field name is provided), restrict to that
    Target Version; otherwise include all versions.
    """
    if not qe_field_for_jql:
        return ""
    statuses = _quoted_list(
        list(dict.fromkeys(["ON_QA", "ASSIGNED", "New", config.qe_status]))
    )
    clauses = [
        f'project = "{config.jira_project}"',
        _ISSUETYPE_BUG,
        f"status in {statuses}",
        _exclude_components_clause(config),
        f'"{qe_field_for_jql}" is EMPTY',
    ]
    if target_version and target_version_jql_field:
        tv = target_version.replace("\\", "\\\\").replace('"', '\\"')
        clauses.insert(-1, f'"{target_version_jql_field}" = "{tv}"')
    return _join_clauses(clauses)


def get_unassigned_qe_contact_bugs(
    config: JiraConfig,
    qe_field_for_jql: str,
    target_version_jql_field: str = "",
    target_version: str = "",
):
    """Fetch unassigned-QE-Contact bugs (all versions unless target_version is set)."""
    query = jql_unassigned_qe_contact_bugs(
        config, qe_field_for_jql, target_version_jql_field, target_version
    )
    if not query:
        return []
    from cephQeInfra.action_items_utils import get_field_id

    target_field_name = config.proposed_version_field or "Target Version"
    target_field_id = get_field_id(config, target_field_name) if target_field_name else None
    severity_name = (getattr(config, "severity_field", None) or "").strip() or "Severity"
    sev_id = get_field_id(config, severity_name)
    extra_fields = []
    for f in (
        sev_id or severity_name,
        target_field_id,
        "status",
        "reporter",
        "versions",
    ):
        if f and f not in extra_fields:
            extra_fields.append(f)
    return search_issues(config, query, fields=extra_fields)


def jql_on_qa_priority_bugs(
    config: JiraConfig, qe_field_for_jql: str, account_ids, *, for_navigator: bool = False
) -> str:
    """ON_QA bugs with QE Contact on the QE team.

    When ``for_navigator`` is True, adds ``NOT status CHANGED AFTER -14d`` for the mail heading link.
    Table rows still use changelog age >14 days in ``on_qa_priority_bugs.py``.
    """
    ids = [a for a in (account_ids or []) if a]
    if not ids or not qe_field_for_jql:
        return ""
    ids_jql = ", ".join(ids)
    clauses = [
        f'project = "{config.jira_project}"',
        _ISSUETYPE_BUG,
        _exclude_components_clause(config),
        f'status = "{config.qe_status}"',
        f'"{qe_field_for_jql}" in ({ids_jql})',
    ]
    if for_navigator:
        clauses.append("NOT status CHANGED AFTER -14d")
    return _join_clauses(clauses)


def get_on_qa_priority_bugs(config: JiraConfig, qe_field_for_jql: str, account_ids):
    """Fetch ON_QA bugs whose QA Contact is on the QE team (stale-age filter in mail code)."""
    query = jql_on_qa_priority_bugs(config, qe_field_for_jql, account_ids)
    if not query:
        return []
    from cephQeInfra.action_items_utils import get_field_id

    qe_name = (getattr(config, "qe_contact_field", None) or "").strip() or "QE Contact"
    qe_field_id = get_field_id(config, qe_name)
    target_field_name = config.proposed_version_field or "Target Version"
    target_field_id = get_field_id(config, target_field_name) if target_field_name else None
    severity_name = (getattr(config, "severity_field", None) or "").strip() or "Severity"
    sev_id = get_field_id(config, severity_name)
    extra_fields = []
    for f in (qe_field_id or qe_name, sev_id or severity_name, target_field_id):
        if f and f not in extra_fields:
            extra_fields.append(f)
    return search_issues(config, query, expand="changelog", fields=extra_fields)
