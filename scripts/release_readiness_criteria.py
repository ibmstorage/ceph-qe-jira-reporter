import os
import sys
from datetime import datetime, timezone

from scipy.stats import scoreatpercentile, tmean

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import load_config
from cephQeInfra.action_items_utils import issues_navigator_hyperlink_formula
from lib.gsheets import GoogleSheet
from lib.jira_queries import (
    get_all_bugs_in_version,
    get_all_bugs_targeted_to_version,
    get_all_regression_bugs,
    get_all_verified_bugs,
    get_critical_bugs,
    get_dev_backlog,
    get_doc_bugs,
    get_open_blockers_by_priority,
    get_open_candidate_blockers,
    get_qe_backlog,
    get_regression_bugs,
    get_untriaged_bugs,
    get_verified_bugs,
    jql_critical_bugs,
    jql_dev_backlog,
    jql_doc_bugs,
    jql_open_blockers_by_priority,
    jql_open_candidate_blockers,
    jql_qe_backlog,
    jql_regression_bugs,
    jql_untriaged_bugs,
)
from lib.report_utils import get_issue_key, iter_status_changes, iter_status_transitions


def _average_verification_time(qe_backlog_bugs, verified_bugs, now):
    time_to_verify_list = []

    for bug in qe_backlog_bugs:
        for change_time, status in iter_status_changes(bug):
            if status == "ON_QA" and change_time is not None:
                time_diff = (now - change_time).total_seconds() / 86400
                time_to_verify_list.append(time_diff)
                break

    for bug in verified_bugs:
        on_qa_time = None
        verified_time = None
        for change_time, status in iter_status_changes(bug):
            if status == "ON_QA" and change_time is not None:
                on_qa_time = change_time
            if status == "Verified" and change_time is not None:
                verified_time = change_time
        if on_qa_time and verified_time:
            time_diff = (verified_time - on_qa_time).total_seconds() / 86400
            time_to_verify_list.append(time_diff)

    if not time_to_verify_list:
        return None

    lower_limit = scoreatpercentile(time_to_verify_list, 10)
    upper_limit = scoreatpercentile(time_to_verify_list, 90)
    average = tmean(time_to_verify_list, limits=(lower_limit, upper_limit))
    return round(average, 2)


def _fast_mode_enabled():
    return os.environ.get("JIRA_RELEASE_READINESS_FAST", "").lower() in {
        "1",
        "true",
        "yes",
    }


def main(spreadsheet_name):
    config = load_config(spreadsheet_name)
    sheet = GoogleSheet(spreadsheet_name, "Release Readiness Criteria")
    now_utc = datetime.now(timezone.utc)  # for verification-time math (changelog is UTC)
    now_local = datetime.now().astimezone()  # for "Last updated" display (IST/local)
    updates = []

    fast_mode = _fast_mode_enabled()
    qe_backlog_bugs = get_qe_backlog(config, expand_changelog=not fast_mode)
    verified_bugs = get_all_verified_bugs(config, expand_changelog=not fast_mode)

    updates.append(
        (
            6,
            3,
            issues_navigator_hyperlink_formula(
                config, jql_qe_backlog(config), len(qe_backlog_bugs)
            ),
        )
    )

    if not fast_mode:
        average_verification_time = _average_verification_time(
            qe_backlog_bugs, verified_bugs, now_utc
        )
        if average_verification_time is not None:
            updates.append((25, 2, average_verification_time))

    dev_backlog_bugs = get_dev_backlog(config)
    open_blockers = get_open_blockers_by_priority(config)
    candidate_blockers = get_open_candidate_blockers(config)
    critical = get_critical_bugs(config)
    regressions = get_regression_bugs(config)
    untriaged = get_untriaged_bugs(config)
    doc = get_doc_bugs(config)
    updates.append(
        (
            6,
            4,
            issues_navigator_hyperlink_formula(
                config, jql_dev_backlog(config), len(dev_backlog_bugs)
            ),
        )
    )
    updates.append(
        (
            6,
            5,
            issues_navigator_hyperlink_formula(
                config, jql_open_blockers_by_priority(config), len(open_blockers)
            ),
        )
    )
    updates.append(
        (
            6,
            6,
            issues_navigator_hyperlink_formula(
                config, jql_open_candidate_blockers(config), len(candidate_blockers)
            ),
        )
    )
    updates.append(
        (
            6,
            7,
            issues_navigator_hyperlink_formula(
                config, jql_critical_bugs(config), len(critical)
            ),
        )
    )
    updates.append(
        (
            6,
            8,
            issues_navigator_hyperlink_formula(
                config, jql_regression_bugs(config), len(regressions)
            ),
        )
    )
    updates.append(
        (
            6,
            9,
            issues_navigator_hyperlink_formula(
                config, jql_untriaged_bugs(config), len(untriaged)
            ),
        )
    )
    updates.append(
        (
            6,
            10,
            issues_navigator_hyperlink_formula(config, jql_doc_bugs(config), len(doc)),
        )
    )

    # Regression rate: of all bugs in affected version (open or done, non-doc), what fraction are regressions?
    # Always 0–1 (0–100%); regressions are a subset of all_bugs.
    all_bugs = len(get_all_bugs_in_version(config))
    all_regressions = len(get_all_regression_bugs(config))
    if all_bugs > 0:
        regression_rate = round((all_regressions / float(all_bugs)), 4)
        updates.append((10, 2, regression_rate))

    ready_for_testing = set()
    failed_qa_bug_keys = set()  # bugs that have ever been failed back from ON_QA to ASSIGNED
    if not fast_mode:
        targeted_bugs = get_all_bugs_targeted_to_version(config, expand_changelog=True)
        fixed_bugs = 0  # count of transitions to ON_QA
        for bug in targeted_bugs:
            key = get_issue_key(bug)
            for _when, from_status, to_status in iter_status_transitions(bug):
                if to_status == config.qe_status:
                    fixed_bugs += 1
                    if key:
                        ready_for_testing.add(key)
                if from_status == config.qe_status and to_status == "ASSIGNED":
                    if key:
                        failed_qa_bug_keys.add(key)

        # Failed QA rate: of bugs that reached ON_QA, what fraction have ever been failed back? (0–100%)
        if ready_for_testing:
            failed_qa_rate = round(
                len(ready_for_testing & failed_qa_bug_keys) / float(len(ready_for_testing)), 4
            )
            updates.append((13, 2, failed_qa_rate))

        # Verification rate: of bugs that reached ON_QA (ready_for_testing), what fraction are verified?
        # 0% = none of those bugs are currently Verified/Closed; 100% = all of them are.
        if ready_for_testing:
            verified_keys = {get_issue_key(b) for b in verified_bugs}
            verified_keys.discard("")
            verified_from_ready = len(ready_for_testing & verified_keys)
            verification_rate = round(
                verified_from_ready / float(len(ready_for_testing)), 4
            )
            updates.append((16, 2, verification_rate))

    if fast_mode:
        verified_weekly = len(
            get_verified_bugs(config, changed_from="-8w", changed_to="-0d")
        )
        updates.append((19, 2, round(verified_weekly / 8, 2)))
    else:
        verified_weekly = 0
        for c_from, c_to in [
            ("-1w", "-0d"),
            ("-2w", "-1w"),
            ("-3w", "-2w"),
            ("-4w", "-3w"),
            ("-5w", "-4w"),
            ("-6w", "-5w"),
            ("-7w", "-6w"),
            ("-8w", "-7w"),
        ]:
            verified_weekly += len(
                get_verified_bugs(config, changed_from=c_from, changed_to=c_to)
            )
        updates.append((19, 2, verified_weekly / 8))
    updates.append((1, 1, f"Last updated: {now_local.strftime('%Y-%m-%d %H:%M')}"))

    if updates:
        sheet.batch_update_cells(updates)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise IndexError("You must provide the spreadsheet name to work with")
    main(sys.argv[1])
