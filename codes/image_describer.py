#!/usr/bin/env python3
"""
Image Describer + Verifier for FireReport

Generates detailed descriptions for extracted images using a vision LLM.
Can use a second "different LLM" (or different prompt/model) to verify accuracy,
completeness, and perform additional OCR.

Primary: OpenAI (gpt-4o / gpt-4o-mini) for vision
Verification: Can switch model or use a judge prompt.

Requires: OPENAI_API_KEY in env, or pass via --api-key

Usage:
  python image_describer.py --limit 20
  python image_describer.py --verify   # double-check existing descriptions
"""

import json
import base64
import os
import argparse
from pathlib import Path
from datetime import datetime
import time

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Project root: works whether this script lives at the project root or in codes/
_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent if _HERE.name == "codes" else _HERE
BASE = ROOT
DATA = BASE / "data"
MANIFEST = DATA / "manifest.json"
MD_DIR = DATA / "markdown"

DEFAULT_MODEL = "gpt-4o-mini"   # fast + cheap for descriptions
VERIFY_MODEL = "gpt-4o"         # stronger for verification

def load_key():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        # Try to extract from GoogleAccess.md as fallback (user may put OpenAI key there too)
        keyfile = Path("/Users/simonwang/Documents/FITE/GoogleAccess.md")
        if keyfile.exists():
            content = keyfile.read_text()
            for line in content.splitlines():
                if "openai" in line.lower() and "key" in line.lower() and "=" in line:
                    key = line.split("=", 1)[1].strip()
                    break
    return key

def encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def get_page_context(md_path: Path, page_num: int, max_chars: int = 800) -> str:
    """Pull a bit of text from around the page marker for context."""
    if not md_path.exists():
        return ""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        marker = f"--- Page {page_num} ---"
        idx = text.find(marker)
        if idx == -1:
            return ""
        snippet = text[idx:idx + max_chars]
        return snippet[:max_chars].strip()
    except Exception:
        return ""

def describe_image(client, image_path: Path, context: str, model: str) -> str:
    """Call vision model to describe the image in context of the inquiry."""
    b64 = encode_image(image_path)
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

    prompt = f"""You are an expert analyst for a Hong Kong government fire inquiry (Wang Fuk Court, Tai Po, Nov 2025).

The image comes from an official PDF document in the Independent Committee materials.

Context from the same page:
{context[:600] if context else "(no surrounding text)"}

Task:
1. Provide a clear, factual, detailed description of what the image shows.
2. If it contains text (signs, tables, diagrams, letters, forms, photos with captions), transcribe the visible text accurately (this helps with OCR).
3. Note the type: photo, diagram, table, scanned letter, slide, floor plan, etc.
4. Highlight anything relevant to: causes of fire, building maintenance/renovation, fire safety installations, supervision, materials, conflicts of interest, or recommendations.
5. Be precise and neutral. Do not speculate.

Output format (concise but complete):
**Type**: ...
**Visible text / OCR**:
...
**Description**:
...
**Relevance to inquiry**:
..."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"}
                        }
                    ]
                }
            ],
            max_tokens=800,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[ERROR describing image: {e}]"

def verify_description(client, original_desc: str, image_path: Path, context: str, model: str) -> str:
    """Use a stronger/different model to critique and improve the description."""
    b64 = encode_image(image_path)
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

    prompt = f"""You are a senior fact-checker for an official inquiry report.

Original AI-generated description of this image:
{original_desc}

Surrounding page text (for context):
{context[:500] if context else "N/A"}

Your job:
- Check the description for accuracy, completeness, and missed details (especially text/OCR).
- Correct any errors.
- Add any important details the first description missed.
- Rate the original description quality (1-5) and explain why.
- Provide an improved, more precise version.

Output:
**Quality rating**: X/5
**Issues found**:
- ...
**Improved description**:
..."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                    ]
                }
            ],
            max_tokens=900,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[VERIFY ERROR: {e}]"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of images to process")
    parser.add_argument("--verify", action="store_true", help="Run verification pass on existing descriptions using stronger model")
    parser.add_argument("--api-key", type=str, default=None)
    args = parser.parse_args()

    key = args.api_key or load_key()
    if not key:
        print("ERROR: No OpenAI API key found. Set OPENAI_API_KEY or pass --api-key")
        return

    if OpenAI is None:
        print("ERROR: openai package not installed. pip install openai")
        return

    client = OpenAI(api_key=key)

    m = json.loads(MANIFEST.read_text())
    pdfs = m.get("pdfs", [])

    images_to_do = []
    for pdf in pdfs:
        if not pdf.get("md_path"):
            continue
        for img in pdf.get("images", []):
            if args.verify:
                if img.get("description"):
                    images_to_do.append((pdf, img))
            else:
                if not img.get("description"):
                    images_to_do.append((pdf, img))

    if args.limit:
        images_to_do = images_to_do[:args.limit]

    print(f"Found {len(images_to_do)} images to {'verify' if args.verify else 'describe'}")

    count = 0
    for pdf_entry, img_entry in images_to_do:
        img_path = DATA / img_entry["local_path"]
        md_path = DATA / pdf_entry["md_path"]
        page = img_entry.get("page", 1)
        context = get_page_context(md_path, page)

        if args.verify:
            original = img_entry.get("description", "")
            new_desc = verify_description(client, original, img_path, context, VERIFY_MODEL)
            img_entry["verified_description"] = new_desc
            img_entry["verified_at"] = datetime.now().isoformat()
            print(f"  ✓ Verified: {img_path.name}")
        else:
            desc = describe_image(client, img_path, context, DEFAULT_MODEL)
            img_entry["description"] = desc
            img_entry["described_at"] = datetime.now().isoformat()
            print(f"  ✓ Described: {img_path.name}")

        count += 1
        if count % 10 == 0:
            MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False))

        time.sleep(0.6)  # rate limit politeness

    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False))
    print(f"\nDone. Updated {count} images. Manifest saved.")

if __name__ == "__main__":
    main()
