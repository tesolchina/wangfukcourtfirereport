#!/usr/bin/env python3
"""
Bind custom domain to Aliyun OSS bucket.
Requires DNS TXT verification first.

Usage:
1. Run this to get the verification token.
2. Add the DNS TXT record as instructed.
3. Wait for propagation (use dig or nslookup).
4. Run this again to bind.
"""

import oss2
import sys

# Credentials loaded from GoogleAccess.md (never hardcode)
import re, os
creds_path = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")
with open(creds_path) as f:
    content = f.read()
ACCESS_KEY_ID = re.search(r"AccessKey ID=\s*([A-Za-z0-9]+)", content).group(1)
ACCESS_KEY_SECRET = re.search(r"AccessKey Secret=\s*([A-Za-z0-9/+=]+)", content).group(1)

BUCKET_NAME = "wangfukcourtfirereport"
ENDPOINT = "oss-cn-hangzhou.aliyuncs.com"
DOMAIN = "wangfukcourtfirereport.simonsays.hk"

def main():
    auth = oss2.Auth(ACCESS_KEY_ID, ACCESS_KEY_SECRET)
    bucket = oss2.Bucket(auth, ENDPOINT, BUCKET_NAME)

    print(f"Bucket: {BUCKET_NAME}")
    print(f"Domain: {DOMAIN}\n")

    # Step 1: Get/Create verification token
    print("Creating verification token...")
    token_result = bucket.create_bucket_cname_token(DOMAIN)
    token = token_result.token
    print(f"Token: {token}")
    print(f"Expires: {token_result.expire_time}")

    # Check if already bound
    print("\nChecking current bindings...")
    cname_result = bucket.list_bucket_cname()
    bound = False
    if hasattr(cname_result, 'cname') and cname_result.cname:
        for c in cname_result.cname:
            if c.domain == DOMAIN:
                print(f"Already bound: {c.domain} (status: {c.status})")
                bound = True
                break

    if bound:
        print("Domain is already bound.")
        return

    print("\n=== DNS VERIFICATION REQUIRED ===")
    print(f"Add this DNS TXT record at your DNS provider (for simonsays.hk):")
    print(f"  Host: _dnsauth.{DOMAIN}")
    print(f"  Type: TXT")
    print(f"  Value: {token}")
    print("\nAfter adding the record, wait 5-30 minutes for propagation.")
    print("Then re-run this script to complete the binding.\n")

    # Try to bind (will fail until verified)
    try:
        print("Attempting to bind (will fail until DNS is set)...")
        req = oss2.models.PutBucketCnameRequest(domain=DOMAIN)
        result = bucket.put_bucket_cname(req)
        print(f"✅ Success! Status: {result.status}")
    except oss2.exceptions.ServerError as e:
        if "NeedVerifyDomainOwnership" in str(e) or "verify" in str(e).lower():
            print("⏳ Verification pending (as expected). Add the DNS record above.")
        else:
            print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
