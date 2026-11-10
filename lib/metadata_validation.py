import json
import os

from config.settings import JiraConfig


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_metadata(metadata_path=None):
    path = (
        metadata_path
        or os.environ.get("JIRA_METADATA_PATH")
        or os.path.join(_repo_root(), "metadata.json")
    )
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"metadata.json not found at {path}. Run metadata fetch first."
        )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _missing_values(values, allowed):
    return sorted([value for value in values if value not in allowed])


def validate_config(config: JiraConfig, metadata: dict, strict=True):
    issues = []

    statuses = set(metadata.get("statuses", []))
    resolutions = set(metadata.get("resolutions", []))
    components = set(metadata.get("components", []))
    labels = set(metadata.get("labels", []))
    field_names = set(metadata.get("bug_field_names", []))

    if statuses:
        missing_statuses = _missing_values(
            list(config.open_statuses) + [config.qe_status, config.verified_status],
            statuses,
        )
        if missing_statuses:
            issues.append(
                "Unknown statuses in config: " + ", ".join(missing_statuses)
            )
    else:
        issues.append("Metadata missing statuses list.")

    if resolutions:
        missing_resolutions = _missing_values(config.done_resolutions, resolutions)
        if missing_resolutions:
            issues.append(
                "Unknown resolutions in config: " + ", ".join(missing_resolutions)
            )
    else:
        issues.append("Metadata missing resolutions list.")

    if components:
        if config.documentation_component not in components:
            issues.append(
                "Unknown documentation component in config: "
                + config.documentation_component
            )
    else:
        issues.append("Metadata missing components list.")

    if labels:
        if config.regression_label not in labels:
            issues.append(
                "Unknown regression label in config: " + config.regression_label
            )
        if getattr(config, "customer_labels", None):
            missing_customers = _missing_values(config.customer_labels, labels)
            if missing_customers:
                issues.append(
                    "Unknown customer labels in config: "
                    + ", ".join(missing_customers)
                )
    else:
        issues.append("Metadata missing labels list.")

    if field_names:
        if config.blocker_field not in field_names:
            issues.append(
                "Unknown blocker field in config: " + config.blocker_field
            )
    else:
        issues.append("Metadata missing bug field names list.")

    if issues and strict:
        raise ValueError("Jira metadata validation failed:\n- " + "\n- ".join(issues))

    return issues
