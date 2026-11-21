"""How long does nginx answer 5xx while the api container is recreated?

Recreates only the api container of the marcus-v2 compose project (`up -d --force-recreate
--no-deps api`) while polling GET /api/v2/health through nginx every 0.5 s, then prints the
longest stretch of failed polls (5xx or no answer) and the status timeline. Standard library only.

    python ops/check_api_recreate.py                       # base stack
    python ops/check_api_recreate.py -f docker-compose.yml -f docker-compose.fake.yml

Run from backend-v2/. Touches nothing but the api container of the project given with -p.
"""

import argparse
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request


def poll(url: str, timeout: float) -> str:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception as exc:  # noqa: BLE001 - every failure is a data point
        return f"error:{type(exc).__name__}"


def api_health(project: str) -> str:
    out = subprocess.run(
        ["docker", "compose", "-p", project, "ps", "--format", "json", "api"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not out:
        return "absent"
    row = json.loads(out.splitlines()[0])
    return row.get("Health") or row.get("State") or "?"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-p", "--project", default="marcus-v2")
    ap.add_argument("-f", "--file", action="append", dest="files")
    ap.add_argument("--project-directory", default=None)
    ap.add_argument("--url", default="http://127.0.0.1:18090/api/v2/health")
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--settle", type=int, default=20, help="consecutive 200s to stop after")
    ap.add_argument("--max-seconds", type=float, default=240)
    args = ap.parse_args()

    files = ["--project-directory", args.project_directory] if args.project_directory else []
    for name in args.files or ["docker-compose.yml"]:
        files += ["-f", name]
    cmd = ["docker", "compose", "-p", args.project, *files,
           "up", "-d", "--force-recreate", "--no-deps", "api"]

    samples: list[tuple[float, str]] = []
    done = threading.Event()
    recreate: dict = {}

    def run_recreate() -> None:
        recreate["start"] = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        recreate["end"] = time.monotonic()
        recreate["rc"] = proc.returncode
        recreate["stderr"] = proc.stderr[-2000:]
        done.set()

    t0 = time.monotonic()
    for _ in range(4):  # baseline: healthy before
        samples.append((time.monotonic() - t0, poll(args.url, args.timeout)))
        time.sleep(args.interval)
    threading.Thread(target=run_recreate, daemon=True).start()

    healthy_at = None
    ok_run = 0
    next_at = time.monotonic()
    while time.monotonic() - t0 < args.max_seconds:
        status = poll(args.url, args.timeout)
        samples.append((time.monotonic() - t0, status))
        ok_run = ok_run + 1 if status == "200" else 0
        if done.is_set() and healthy_at is None and api_health(args.project) == "healthy":
            healthy_at = time.monotonic() - t0
        if done.is_set() and healthy_at is not None and ok_run >= args.settle:
            break
        next_at = max(next_at + args.interval, time.monotonic())  # no burst after a slow poll
        time.sleep(max(0.0, next_at - time.monotonic()))

    # longest stretch of failed polls: first failed poll .. first 200 after it
    longest, start, worst = 0.0, None, None
    for t, status in samples:
        if status != "200" and start is None:
            start = t
        elif status == "200" and start is not None:
            if t - start > longest:
                longest, worst = t - start, (start, t)
            start = None
    if start is not None:
        longest, worst = samples[-1][0] - start, (start, None)

    runs: list[list] = []  # [status, first t, last t, count]
    for t, status in samples:
        if runs and runs[-1][0] == status:
            runs[-1][2], runs[-1][3] = t, runs[-1][3] + 1
        else:
            runs.append([status, t, t, 1])
    summary = {
        "recreate_command": " ".join(cmd),
        "recreate_rc": recreate.get("rc"),
        "recreate_s": round(recreate["end"] - recreate["start"], 1) if "end" in recreate else None,
        "recreate_started_at_s": round(recreate["start"] - t0, 1) if "start" in recreate else None,
        "api_healthy_at_s": round(healthy_at, 1) if healthy_at else None,
        "polls": len(samples),
        "failed_polls": sum(1 for _, s in samples if s != "200"),
        "longest_failed_stretch_s": round(longest, 1),
        "longest_stretch_window_s": [round(x, 1) if x is not None else None for x in worst]
        if worst else None,
        "timeline": [
            f"{s:>22} x{n:<3} {a:6.1f}-{b:6.1f} s" for s, a, b, n in runs
        ],
    }
    if recreate.get("rc"):
        summary["recreate_stderr"] = recreate["stderr"]
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
