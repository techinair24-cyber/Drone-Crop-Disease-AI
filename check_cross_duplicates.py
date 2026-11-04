from pathlib import Path
from collections import defaultdict
import hashlib
import csv

DATASET = Path.home() / "Desktop" / "Leaf Dataset"
OUTPUT = Path.cwd() / "duplicate_report.csv"

EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
hashes = defaultdict(list)

print("Checking duplicates across crop and health labels...")

for path in DATASET.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
        continue

    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        crop = path.parent.parent.name
        label = path.parent.name
        hashes[digest].append((path, crop, label))
    except Exception as e:
        print("Could not read:", path, e)

cross_category = []

for digest, entries in hashes.items():
    categories = {(crop, label) for _, crop, label in entries}

    if len(categories) > 1:
        cross_category.append((digest, entries))

with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.writer(file)
    writer.writerow(["SHA256", "Crop", "Label", "File Path"])

    for digest, entries in cross_category:
        for path, crop, label in entries:
            writer.writerow([digest, crop, label, str(path)])

print("\n========== CROSS-CATEGORY REPORT ==========")
print("Duplicate groups across different categories:", len(cross_category))
print("Report saved to:", OUTPUT)

for digest, entries in cross_category[:15]:
    print("\nDuplicate group:")
    for path, crop, label in entries:
        print(f"  {crop} / {label}: {path.name}")

print("\nNo files were deleted or modified.")
