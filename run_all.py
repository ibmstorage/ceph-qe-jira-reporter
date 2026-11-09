import subprocess
import sys, time


SCRIPTS = [
    "scripts/action_items.py",
    "scripts/arrivals_vs_resolved.py",
    "scripts/average_qa_score.py",
    "scripts/blocker_resolution_time.py",
    "scripts/component_distribution.py",
    "scripts/customer_bugs_release_tracking.py",
    "scripts/pqi_report.py",
    "scripts/release_readiness_criteria.py",
    "scripts/scale_n_perf_defects.py",
    "scripts/tracking_dashboard.py",
]


def main(spreadsheet_name):
    for script in SCRIPTS:
        print(f"Running {script}")
        result = subprocess.run(
            [sys.executable, script, spreadsheet_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            raise SystemExit(result.returncode)
        time.sleep(2)

if __name__ == "__main__":
    main("IBMCEPH JIRA QE - 9.1 Quality Dashboard")
