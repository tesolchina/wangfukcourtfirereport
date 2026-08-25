#!/usr/bin/env python3
"""Real-time logger for the LLM document analysis.

Polls data/analysis.json every 20s and appends a timestamped line to
docs/analysis_log.md whenever the analysed count changes. Exits when the
analysis reaches 243/243 or after 90 minutes.
Run in background: nohup python3 codes/analysis_logger.py > /dev/null 2>&1 &
"""
import json, os, time, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AN = os.path.join(ROOT, "data", "analysis.json")
OUT = os.path.join(ROOT, "docs", "analysis_log.md")
TOTAL = 243


def count():
    try:
        with open(AN) as f:
            return len(json.load(f))
    except Exception:
        return None


def log_line(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(OUT, "a") as f:
        f.write(f"- {ts} — {msg}\n")
        f.flush()


def main():
    last = None
    t0 = time.time()
    while time.time() - t0 < 90 * 60:
        c = count()
        if c is not None and c != last:
            pct = c / TOTAL * 100
            status = "COMPLETE" if c >= TOTAL else "running"
            log_line(f"**{c}/{TOTAL} docs analysed ({pct:.0f}%) — {status}**")
            last = c
            if c >= TOTAL:
                log_line("**ANALYSIS COMPLETE — all 243 docs analysed.**")
                return
        time.sleep(20)
    log_line(f"Logger timed out (90 min) at {last}/{TOTAL} — check `data/analysis.json` / `data/analysis_run.log`.")


if __name__ == "__main__":
    main()
