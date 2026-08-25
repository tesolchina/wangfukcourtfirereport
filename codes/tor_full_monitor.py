#!/usr/bin/env python3
"""Monitor for codes/tor_full_scan.py — checks progress every 20 minutes.

Polls data/tor_full.json and appends a timestamped line to
docs/tor_full_monitor.log whenever the scanned count changes. Also watches the
scan's own log (data/tor_full_scan.log) for 429/retry events and for
completion ("Done."). On completion it prints a summary of per-ToR doc counts
and reminds the next steps (aggregate → rebuild → deploy).

Run in background:
  nohup python3 codes/tor_full_monitor.py > /dev/null 2>&1 &

Interval is 20 minutes by default (--interval 1200); use --once to take a
single reading (useful for a one-off status check).
"""
import argparse, json, os, re, sys, time, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FULL = os.path.join(ROOT, "data", "tor_full.json")
SCANLOG = os.path.join(ROOT, "data", "tor_full_scan.log")
OUT = os.path.join(ROOT, "docs", "tor_full_monitor.log")
TOTAL = 243

TOR_ALL = [
    "ToR1: Causes & Circumstances of Fire",
    "ToR2: Fire Service Installations & Equipment",
    "ToR3: Building Maintenance & Renovation Works",
    "ToR4: Supervision, Roles & Responsibilities",
    "ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)",
    "ToR6: Adequacy of Laws & Penalties",
    "ToR7: Recommendations & Improvement Measures",
    "General / Other",
]


def status():
    try:
        with open(FULL) as f:
            r = json.load(f)
    except Exception:
        return None, None
    ok = sum(1 for v in r.values() if v.get("ok"))
    return len(r), ok


def scanlog_tail():
    """Last few lines of the scan's own log (for 429 / retry / completion)."""
    try:
        with open(SCANLOG) as f:
            lines = f.read().strip().splitlines()
        return lines[-6:]
    except Exception:
        return []


def scan_done():
    try:
        with open(SCANLOG) as f:
            return "Done." in f.read()
    except Exception:
        return False


def log_line(msg, also_print=True):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} — {msg}"
    if also_print:
        print(line, flush=True)
    with open(OUT, "a") as f:
        f.write(line + "\n")
        f.flush()


def per_tor_summary():
    try:
        with open(FULL) as f:
            r = json.load(f)
    except Exception:
        return ""
    from collections import Counter
    c = Counter()
    for v in r.values():
        for t in (v.get("doc_tor_tags") or []):
            c[t] += 1
    parts = []
    for t in TOR_ALL:
        parts.append(f"{t.split(':')[0]}={c.get(t, 0)}")
    return " | ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=1200,
                    help="seconds between checks (default 1200 = 20 min)")
    ap.add_argument("--max_hours", type=float, default=24,
                    help="stop after this many hours (default 24)")
    ap.add_argument("--once", action="store_true", help="single check then exit")
    args = ap.parse_args()

    last = None
    t0 = time.time()
    max_secs = args.max_hours * 3600

    while True:
        n, ok = status()
        done = scan_done()
        tail = scanlog_tail()
        rate_limited = any("429" in ln or "Retry round" in ln or "cooling down" in ln
                           for ln in tail)

        if n is not None and n != last:
            pct = n / TOTAL * 100
            msg = (f"tor_full_scan: {n}/{TOTAL} docs scanned ({pct:.0f}%), ok={ok}"
                   + (f" | rate-limit/retry events in scan log" if rate_limited else "")
                   + f"\n  ToR counts: {per_tor_summary()}")
            log_line(msg)
            last = n

        if done and n is not None and n >= TOTAL:
            log_line(f"**tor_full_scan COMPLETE — {n}/{TOTAL} docs. "
                     f"Next: python3 codes/tor_aggregate.py → rebuild (build_site, "
                     f"tc_site, search_build) → deploy_site.py**")
            log_line(f"Final ToR counts: {per_tor_summary()}")
            return
        if done and n is not None and n < TOTAL:
            # scan exited early (errors exhausted) — flag it
            log_line(f"**tor_full_scan exited with {n}/{TOTAL} — check data/tor_full_scan.log; "
                     f"rerun to resume (script is idempotent/resumable).**")
            return

        if args.once:
            break
        if time.time() - t0 > max_secs:
            log_line(f"Monitor timed out after {args.max_hours}h at {n}/{TOTAL} — rerun to keep watching.")
            return

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
