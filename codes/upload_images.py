#!/usr/bin/env python3
"""Upload all extracted images to the OSS bucket under images/ (background job).

Usage: nohup python3 codes/upload_images.py > data/upload_images.log 2>&1 &
"""
import re, os, glob, sys
import oss2

CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUCKET = "wangfukcourtfirereport-hk"
ENDPOINT = "https://oss-cn-hongkong.aliyuncs.com"


def main():
    with open(CREDS) as f:
        content = f.read()
    ak = re.search(r"AccessKey ID=\s*([A-Za-z0-9]+)", content).group(1)
    sk = re.search(r"AccessKey Secret=\s*([A-Za-z0-9/+=]+)", content).group(1)
    auth = oss2.Auth(ak, sk)
    bucket = oss2.Bucket(auth, ENDPOINT, BUCKET)

    files = sorted(glob.glob(os.path.join(ROOT, "data", "images", "*")))
    print(f"images to upload: {len(files)}")
    ok = fail = 0
    for i, f in enumerate(files, 1):
        key = "images/" + os.path.basename(f)
        try:
            with open(f, "rb") as fh:
                bucket.put_object(key, fh, headers={"Content-Type": "image/jpeg" if f.endswith(".jpeg") else "image/png"})
            ok += 1
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"FAIL {key}: {e}")
        if i % 500 == 0:
            print(f"[{i}/{len(files)}] ok={ok} fail={fail}", flush=True)
    print(f"done. ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
