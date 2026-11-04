from pathlib import Path
from collections import defaultdict
import hashlib

DATASET = Path.home() / "Desktop" / "Leaf Dataset"

EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

hashes = defaultdict(list)

print("Checking exact duplicate images...")

for path in DATASET.rglob("*"):
    if path.is_file() and path.suffix.lower() in EXTENSIONS:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hashes[digest].append(path)
        except Exception as e:
            print("Could not read:", path, e)

duplicates = {
    digest: paths
    for digest, paths in hashes.items()
    if len(paths) > 1
}

duplicate_copies = sum(len(paths) - 1 for paths in duplicates.values())

print("\n========== DUPLICATE REPORT ==========")
print("Unique image contents:", len(hashes))
print("Duplicate groups:", len(duplicates))
print("Extra duplicate copies:", duplicate_copies)

for paths in list(duplicates.values())[:20]:
    print("\nDuplicate group:")
    for path in paths:
        print(" ", path)

print("\nCheck completed. No files were deleted.")
