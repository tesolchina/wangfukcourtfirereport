#!/usr/bin/env python3
"""FINISH PIPELINE — wait for the gaps-OCR job, then rebuild + deploy.

Waits for codes/ocr_gaps.py to finish (its log gains a "done." line), then runs
the full rebuild chain (EN -> search index -> TC) and deploys to Aliyun OSS,
writing data/finish_deploy.log + a data/finish_done.json marker.

Usage: nohup python3 codes/finish_deploy.py > data/finish_deploy.log 2>&1 &
"""
import json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
PY = sys.executable
GAPS_LOG = os.path.join(ROOT, "data", "ocr_gaps.log")


def wait_for_gaps(timeout_h=6):
    t0 = time.time()
    while time.time() - t0 < timeout_h * 3600:
        if os.path.exists(GAPS_LOG):
            tail = open(GAPS_LOG).read().strip().splitlines()
            if tail and tail[-1].startswith("done."):
                print("[1/4] gaps OCR finished", flush=True)
                return True
        # process gone?
        r = subprocess.run(["pgrep", "-f", "ocr_gaps.py"], capture_output=True, text=True)
        if r.returncode != 0:
            if os.path.exists(GAPS_LOG):
                tail = open(GAPS_LOG).read().strip().splitlines()
                if tail and tail[-1].startswith("done."):
                    print("[1/4] gaps OCR finished (process exited)", flush=True)
                    return True
            print("[1/4] gaps OCR process not running and no done marker — continuing anyway", flush=True)
            return True
        print(f"[1/4] waiting for gaps OCR... ({int(time.time()-t0)}s)", flush=True)
        time.sleep(120)
    print("[1/4] TIMEOUT waiting for gaps OCR — proceeding anyway", flush=True)
    return True


def run(step, cmd):
    print(f"[{step}] {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, cwd=ROOT)
    if r.returncode != 0:
        print(f"[{step}] FAILED rc={r.returncode}", flush=True)
        sys.exit(1)
    return r


def main():
    wait_for_gaps()
    run("2/4 build EN", f"{PY} codes/build_site.py")
    run("3/4 build search index", f"{PY} codes/search_build.py")
    run("3/4 build TC", f"{PY} codes/tc_site.py")
    run("4/4 deploy", f"{PY} codes/deploy_site.py")
    json.dump({"done": time.strftime("%Y-%m-%dT%H:%M:%S")},
              open(os.path.join(ROOT, "data", "finish_done.json"), "w"), indent=1)
    print("ALL DONE — site rebuilt and deployed", flush=True)


if __name__ == "__main__":
    main()
