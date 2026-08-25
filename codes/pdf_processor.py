#!/usr/bin/env python3
"""
PDF Processor for FireReport
- Converts downloaded PDFs to Markdown (with page markers)
- Extracts images per page (with numbering)
- Updates manifest with processing status

Run with the Python that has PyMuPDF + Pillow:
  /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 pdf_processor.py
"""

import json
import logging
from pathlib import Path
from datetime import datetime
import fitz  # PyMuPDF
from PIL import Image
import io
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Project root: works whether this script lives at the project root or in codes/
_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent if _HERE.name == "codes" else _HERE
BASE = ROOT
DATA = BASE / "data"
PDF_DIR = DATA / "pdfs"
MD_DIR = DATA / "markdown"
IMG_DIR = DATA / "images"
MANIFEST = DATA / "manifest.json"

class FireReportPDFProcessor:
    def __init__(self):
        MD_DIR.mkdir(parents=True, exist_ok=True)
        IMG_DIR.mkdir(parents=True, exist_ok=True)

    def load_manifest(self):
        return json.loads(MANIFEST.read_text())

    def save_manifest(self, m):
        MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False))

    def clean_text(self, text: str) -> str:
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        return text.strip()

    def process_one(self, pdf_entry: dict) -> bool:
        pdf_path = DATA / pdf_entry["local_path"]
        if not pdf_path.exists():
            logger.warning(f"Missing PDF: {pdf_path}")
            return False

        stem = pdf_path.stem
        md_path = MD_DIR / f"{stem}.md"
        if md_path.exists() and md_path.stat().st_size > 200:
            logger.info(f"Skip (already converted): {stem}")
            return True

        try:
            doc = fitz.open(pdf_path)
            num_pages = len(doc)

            # Metadata
            meta = doc.metadata or {}

            # Extract text + images
            md_parts = []
            image_count = 0
            image_records = []

            for page_num in range(num_pages):
                page = doc[page_num]
                page_label = page_num + 1

                # Text
                text = page.get_text()
                md_parts.append(f"\n\n--- Page {page_label} ---\n\n{text}")

                # Images on this page
                images = page.get_images(full=True)
                for img_idx, img in enumerate(images):
                    xref = img[0]
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        ext = base_image.get("ext", "png")

                        img_name = f"{stem}_p{page_label:03d}_img{img_idx+1:03d}.{ext}"
                        img_path = IMG_DIR / img_name

                        # Save image
                        with open(img_path, "wb") as f:
                            f.write(image_bytes)

                        image_count += 1
                        image_records.append({
                            "page": page_label,
                            "index_on_page": img_idx + 1,
                            "filename": img_name,
                            "local_path": str(img_path.relative_to(DATA)),
                            "size": len(image_bytes),
                            "description": None  # to be filled by LLM later
                        })
                    except Exception as ie:
                        logger.debug(f"Image extract fail page {page_label}: {ie}")

            # Build markdown
            title = meta.get("title") or stem.replace("_", " ")
            md_content = f"""# {title}

**Source**: {pdf_entry.get("url", "")}
**Local PDF**: {pdf_entry["local_path"]}
**Pages**: {num_pages}
**Images extracted**: {image_count}
**Converted**: {datetime.now().isoformat()}

## Metadata
- Author: {meta.get("author", "N/A")}
- Subject: {meta.get("subject", "N/A")}
- Creator: {meta.get("creator", "N/A")}
- Producer: {meta.get("producer", "N/A")}

---

## Content

{self.clean_text("".join(md_parts))}
"""

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            # Update entry
            pdf_entry["md_path"] = str(md_path.relative_to(DATA))
            pdf_entry["num_pages"] = num_pages
            pdf_entry["num_images"] = image_count
            pdf_entry["images"] = image_records
            pdf_entry["processed_at"] = datetime.now().isoformat()

            doc.close()
            logger.info(f"✓ {stem} -> {num_pages}p, {image_count} images")
            return True

        except Exception as e:
            logger.error(f"Failed {stem}: {e}")
            return False

    def run(self, limit: int | None = None):
        m = self.load_manifest()
        pdfs = m.get("pdfs", [])

        to_process = [p for p in pdfs if not p.get("md_path")]
        if limit:
            to_process = to_process[:limit]

        logger.info(f"Processing {len(to_process)} PDFs (limit={limit}) ...")

        success = 0
        for entry in to_process:
            if self.process_one(entry):
                success += 1

        self.save_manifest(m)
        logger.info(f"Done: {success}/{len(to_process)} successful")
        logger.info(f"Markdown in: {MD_DIR}")
        logger.info(f"Images in: {IMG_DIR}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Process only first N unprocessed PDFs (for testing)")
    args = parser.parse_args()

    proc = FireReportPDFProcessor()
    proc.run(limit=args.limit)
