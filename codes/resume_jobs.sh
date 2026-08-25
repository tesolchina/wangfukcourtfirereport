#!/bin/bash
# Watchdog: wait for the HKBU GenAI soft-ban to lift, then resume the pending
# LLM jobs ONE AT A TIME (never concurrently, to avoid re-triggering the ban):
#   1. doc_meta retry  (4 workers, ~44 docs)
#   2. image_vision resume (3 workers, then a second pass for any leftovers)
set -u
cd /Users/simonwang/Workspace/AI4news/projects/FireReport
PY=/Library/Frameworks/Python.framework/Versions/3.10/bin/python3

test_gateway() {
  "$PY" - <<'PYEOF'
import json, urllib.request, urllib.error, ssl, sys
try:
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
except Exception:
    ctx = ssl._create_unverified_context()
payload = {"messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}
req = urllib.request.Request(
    "https://genai.hkbu.edu.hk/general/rest/deployments/gpt-4.1-mini/chat/completions?api-version=2024-02-01",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json",
             "api-key": "REPLACE_WITH_HKBU_GENAI_KEY"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        json.loads(r.read())
    sys.exit(0)
except Exception:
    sys.exit(1)
PYEOF
}

echo "$(date) watchdog start" >> data/watchdog.log
while ! test_gateway; do
  echo "$(date) gateway still banned - waiting 300s" >> data/watchdog.log
  sleep 300
done
echo "$(date) gateway OK - resuming doc_meta retry" >> data/watchdog.log
DOC_META_WORKERS=4 "$PY" codes/doc_meta.py >> data/doc_meta.log 2>&1
echo "$(date) doc_meta done - resuming image_vision pass 1" >> data/watchdog.log
IMAGE_VISION_WORKERS=3 "$PY" codes/image_vision.py >> data/image_vision.log 2>&1
echo "$(date) image_vision pass 1 done - pass 2 (leftovers)" >> data/watchdog.log
IMAGE_VISION_WORKERS=3 "$PY" codes/image_vision.py >> data/image_vision.log 2>&1
echo "$(date) image_vision pass 2 done - ALL RESUMED" >> data/watchdog.log
