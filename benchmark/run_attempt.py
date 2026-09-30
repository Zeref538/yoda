"""Run the pre-registered attempt in docs/ATTEMPT_NEXT.md, resumably.

Each run writes benchmark/results/instructions/attempt/<name>.{json,md}. A run
whose .json exists is skipped, so re-running this after a crash picks up where
it stopped. A lockfile keeps two copies from racing.

    python -m benchmark.run_attempt
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUT = Path(__file__).parent / "results" / "instructions" / "attempt"
RUNS = ([("baseline", "single", i) for i in (2, 3)]      # run 1 is the timing run
        + [("vote3", "vote3", i) for i in (1, 2, 3)]
        + [("intent", "intent", i) for i in (1, 2, 3)])
VOTE3_FIRST_RUN_LIMIT_S = 60 * 60  # ATTEMPT_NEXT.md: over an hour -> stop, re-plan


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    lock = OUT / ".lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(f"another run holds {lock}; delete it only if no run is going")
        return 1
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    timings_path = OUT / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}
    try:
        for label, strategy, i in RUNS:
            name = f"{label}_run{i}"
            if (OUT / f"{name}.json").exists():
                print(f"skip {name} (done)", flush=True)
                continue
            print(f"start {name} {time.strftime('%H:%M:%S')}", flush=True)
            t0 = time.time()
            r = subprocess.run([sys.executable, "-u", "-m", "benchmark.run_instructions",
                                "--model", "qwen3.5:4b", "--strategy", strategy,
                                "--out", str(OUT / name)])
            secs = round(time.time() - t0)
            if r.returncode != 0:
                print(f"FAILED {name} exit {r.returncode}; stopping", flush=True)
                return r.returncode
            timings[name] = secs
            tmp = timings_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(timings, indent=1))
            os.replace(tmp, timings_path)
            score = sum(x["result"]["pass"] for x in
                        json.loads((OUT / f"{name}.json").read_text(encoding="utf-8")))
            print(f"done {name} {score}/39 in {secs // 60} min", flush=True)
            if name == "vote3_run1" and secs > VOTE3_FIRST_RUN_LIMIT_S:
                print("STOP: vote3 run 1 took over an hour, per the plan", flush=True)
                return 3
        print("ALL DONE", flush=True)
        return 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
