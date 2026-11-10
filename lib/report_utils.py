from datetime import datetime, timezone


def _get_field(issue, field_path, default=None):
    """Get a value from issue or issue.fields, supporting both object and dict-like structures."""
    if issue is None:
        return default
    parts = field_path.split(".")
    obj = issue
    for part in parts:
        if obj is None:
            return default
        val = getattr(obj, part, None)
        if val is None and hasattr(obj, "__getitem__") and not isinstance(obj, (str, list)):
            try:
                val = obj[part]
            except (KeyError, TypeError):
                pass
        obj = val
    return obj if obj is not None else default


def get_issue_key(issue):
    """Return issue key (e.g. PROJ-123), supporting both API v3 _to_obj and jira library Issue."""
    key = getattr(issue, "key", None)
    if key:
        return str(key)
    if hasattr(issue, "__getitem__"):
        try:
            return issue.get("key") if hasattr(issue, "get") else issue["key"]
        except (KeyError, TypeError):
            pass
    return ""


def get_issue_summary(issue):
    """Return issue summary from fields, supporting both object and dict-like fields."""
    fields = getattr(issue, "fields", None)
    if fields is None:
        return ""
    summary = getattr(fields, "summary", None)
    if summary is not None:
        return str(summary)
    if hasattr(fields, "get"):
        summary = fields.get("summary")
        if summary is not None:
            return str(summary)
    return ""


def get_issue_status_name(issue):
    """Return current status name (e.g. ON_QA), supporting both object and dict-like fields."""
    fields = getattr(issue, "fields", None)
    if fields is None:
        return ""
    status = getattr(fields, "status", None)
    if status is not None:
        name = getattr(status, "name", None)
        if name:
            return str(name)
        if hasattr(status, "get"):
            name = status.get("name")
            if name:
                return str(name)
    if hasattr(fields, "get"):
        status = fields.get("status")
        if isinstance(status, dict):
            return str(status.get("name", ""))
        if status is not None and hasattr(status, "name"):
            return str(status.name)
    return ""


def parse_jira_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        # Jira library sometimes returns datetime objects; ensure timezone-aware for comparisons
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not isinstance(value, str):
        value = str(value)
    raw = value.strip()
    if not raw:
        return None
    # Normalize Zulu / offset forms so fromisoformat can parse Cloud payloads.
    if raw.endswith("Z") and "T" in raw:
        raw = raw[:-1] + "+00:00"
    # "+0000" / "+0530" → "+00:00" / "+05:30"
    if len(raw) >= 5 and raw[-5] in "+-" and raw[-3] != ":":
        raw = raw[:-2] + ":" + raw[-2:]
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except (ValueError, TypeError):
            continue
    return None


def iter_status_changes(issue):
    histories = getattr(issue, "changelog", None)
    if histories is None:
        return []
    result = []
    for history in histories.histories:
        created = parse_jira_datetime(history.created)
        for change in history.items:
            if change.field == "status":
                result.append((created, change.toString))
    return result


def iter_status_transitions(issue):
    histories = getattr(issue, "changelog", None)
    if histories is None:
        return []
    result = []
    for history in histories.histories:
        created = parse_jira_datetime(history.created)
        for change in history.items:
            if change.field == "status":
                result.append((created, change.fromString, change.toString))
    return result
