"""Validation module for crawled VinFast Markdown files (P-150 project)."""

import re
from pathlib import Path

OUTPUT_DIR = Path("data-p150/car_pdf")
EXPECTED_DOCS: dict[str, dict[str, str]] = {
    "VF2": {
        "file": "VF2.md",
        "title": "Xe điện VinFast VF2",
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-2/",
    },
    "VF3": {
        "file": "VF3.md",
        "title": "Xe điện VinFast VF3",
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-3/",
    },
    "VF5": {
        "file": "VF5.md",
        "title": "Xe điện VinFast VF5",
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-5/",
    },
    "VF6": {
        "file": "VF6.md",
        "title": "Xe điện VinFast VF6",
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-6/",
    },
    "MPV7": {
        "file": "MPV7.md",
        "title": "Xe điện VinFast MPV7",
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-mpv-7/",
    },
    "VF7": {
        "file": "VF7.md",
        "title": "Xe điện VinFast VF7",
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-7/",
    },
    "VF8": {
        "file": "VF8.md",
        "title": "Xe điện VinFast VF8",
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-8/",
    },
    "VF8_2026": {
        "file": "VF8_2026.md",
        "title": "Xe điện VinFast VF8 The All-New 2026",
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-8-all-new/",
    },
    "VF9": {
        "file": "VF9.md",
        "title": "Xe điện VinFast VF9",
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-9/",
    },
}


def validate() -> bool:
    """Validate all generated Markdown files against P-150 requirements."""
    print("Starting validation...")
    errors: list[str] = []

    # 1. Check directory & file count
    files = list(OUTPUT_DIR.glob("*.md"))
    if len(files) != 9:
        errors.append(f"Expected 9 files, found {len(files)}")
    else:
        print("PASS: Found 9 Markdown files.")

    for doc_id, expected in EXPECTED_DOCS.items():
        file_path = OUTPUT_DIR / expected["file"]
        if not file_path.exists():
            errors.append(f"Missing file: {expected['file']}")
            continue

        content = file_path.read_text(encoding="utf-8")

        # 2. Check front matter format
        if not content.startswith("---"):
            errors.append(f"{file_path.name}: Missing YAML front matter start '---'")

        # 3. Check metadata fields
        if f"doc_id: {doc_id}" not in content:
            errors.append(f"{file_path.name}: Incorrect doc_id")
        if f"title: {expected['title']}" not in content:
            errors.append(f"{file_path.name}: Incorrect title")
        if f"source_url: {expected['url']}" not in content:
            errors.append(f"{file_path.name}: Incorrect source_url")
        if "category: car" not in content:
            errors.append(f"{file_path.name}: Missing category: car")
        if "language: vi" not in content:
            errors.append(f"{file_path.name}: Missing language: vi")

        # 4. Check non-empty content
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if len(lines) < 10:
            errors.append(f"{file_path.name}: Content too short ({len(lines)} lines)")

        # 5. Check removed comparison section
        if re.search(r"so\s*sánh.*động\s*cơ\s*đốt\s*trong", content, re.IGNORECASE):
            errors.append(f"{file_path.name}: Found comparison section 'So sánh với động cơ đốt trong'")

        # 6. Check for raw HTML tags
        if re.search(r"<(script|style|div|span|p|a|iframe)\b", content, re.IGNORECASE):
            errors.append(f"{file_path.name}: Contains raw HTML tags")

    if errors:
        print("Validation FAILED with errors:")
        for err in errors:
            print(f" - [FAIL] {err}")
        return False

    print("Validation SUCCESSFUL: All 9 vehicle Markdown files passed all checks.")
    return True


if __name__ == "__main__":
    validate()
