#!/usr/bin/env python3
"""Gateway watchdog: wait for the HKBU GenAI soft-ban to lift, then resume the
pending LLM jobs ONE AT A TIME (never concurrently) to avoid re-triggering it:

  1. doc_meta retry       (4 workers, ~44 docs)
  2. image_vision pass 1  (3 workers)
  3. image_vision pass 2  (3 workers, picks up leftovers)

Logs to data/watchdog.log. Run: nohup python3 codes/gateway_watch.py > /dev/null 2>&1 &
"""
import json, os, subprocess, sys, time
import urllib.request, urllib.error, ssl

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl._create_unverified_context()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "watchdog.log")
PY = "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3"
ENDPOINT = ("https://genai.hkbu.edu.hk/general/rest/deployments/gpt-4.1-mini/"
            "chat/completions?api-version=2024-02-01")
API_KEY = "REPLACE_WITH_HKBU_GENAI_KEY"
POLL_SECONDS = 300


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def gateway_ok():
    payload = {"messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "api-key": API_KEY}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            json.loads(r.read())
        return True
    except Exception:
        return False


def run_job(script, workers_env, label):
    log(f"starting {label} (workers={workers_env})")
    env = dict(os.environ)
    env["DOC_META_WORKERS"] = str(workers_env)
    env["IMAGE_VISION_WORKERS"] = str(workers_env)
    out = open(os.path.join(ROOT, "data", "watchdog_run.log"), "a")
    p = subprocess.run([PY, os.path.join(ROOT, "codes", script)],
                       cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
    log(f"finished {label} rc={p.returncode}")


def main():
    log("watchdog start")
    while not gateway_ok():
        log("gateway still banned - waiting %ss" % POLL_SECONDS)
        time.sleep(POLL_SECONDS)
    log("gateway OK - resuming")
    run_job("doc_meta.py", 4, "doc_meta retry")
    run_job("image_vision.py", 3, "image_vision pass 1")
    run_job("image_vision.py", 3, "image_vision pass 2")
    log("ALL RESUMED DONE")


if __name__ == "__main__":
    main()
