#!/usr/bin/env python3
"""Deploy the generated static site (site_out/) to the Aliyun OSS bucket.

Bucket: wangfukcourtfirereport-hk (cn-hongkong, custom domain wangfukcourtfirereport.simonsays.hk)
Credentials are read from ~/Documents/FITE/GoogleAccess.md (never hardcode).

Usage: python3 codes/deploy_site.py [--dry-run]
"""
import os, sys, re, mimetypes
import oss2

CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site_out")
BUCKET = "wangfukcourtfirereport-hk"
ENDPOINT = "https://oss-cn-hongkong.aliyuncs.com"

DRY = "--dry-run" in sys.argv

# OSS serves HTML via the custom domain; ensure browsers render, never download.
CONTENT_DISPOSITION = "inline"

def content_type(path):
    mime, _ = mimetypes.guess_type(path)
    if path.endswith(".html"):
        return "text/html; charset=utf-8"
    if path.endswith(".css"):
        return "text/css; charset=utf-8"
    if path.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if path.endswith(".svg"):
        return "image/svg+xml"
    return mime or "application/octet-stream"


def main():
    with open(CREDS) as f:
        content = f.read()
    ak = re.search(r"AccessKey ID=\s*([A-Za-z0-9]+)", content).group(1)
    sk = re.search(r"AccessKey Secret=\s*([A-Za-z0-9/+=]+)", content).group(1)
    auth = oss2.Auth(ak, sk)
    bucket = oss2.Bucket(auth, ENDPOINT, BUCKET)

    files = []
    for root, dirs, names in os.walk(SITE):
        for n in sorted(names):
            p = os.path.join(root, n)
            rel = os.path.relpath(p, SITE).replace(os.sep, "/")
            files.append((p, rel))
    print(f"files to upload: {len(files)}")

    ok = fail = 0
    for p, rel in files:
        ct = content_type(p)
        headers = {"Content-Type": ct, "Content-Disposition": CONTENT_DISPOSITION}
        if DRY:
            print(f"  [dry] {rel} ({ct})")
            ok += 1
            continue
        try:
            with open(p, "rb") as fh:
                bucket.put_object(rel, fh, headers=headers)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  [FAIL] {rel}: {e}")
    print(f"done. ok={ok} fail={fail}")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
