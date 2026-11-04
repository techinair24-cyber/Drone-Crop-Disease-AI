from pathlib import Path
from PIL import Image
from collections import Counter

DATASET = Path.home() / "Desktop" / "Leaf Dataset"

CROPS = [
    "Maize", "Hibiscus", "Tomato", "Chilli", "Wheat",
    "Apple", "Grape", "Potato", "Peach", "Strawberry"
]

EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

total = 0
invalid = []
extensions = Counter()

print("\nLEAF DATASET AUDIT\n")

for crop in CROPS:
    print(f"\n{crop}")

    for label in ["Healthy", "Unhealthy"]:
        folder = DATASET / crop / label

        if not folder.is_dir():
            print(f"  ERROR: Missing {folder}")
            continue

        files = [
            p for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() in EXTENSIONS
        ]

        valid = 0

        for path in files:
            try:
                with Image.open(path) as image:
                    image.verify()
                valid += 1
                extensions[path.suffix.lower()] += 1
            except Exception:
                invalid.append(str(path))

        total += len(files)
        print(f"  {label}: {len(files)} files, {valid} readable")

print("\n========== AUDIT SUMMARY ==========")
print("Total image files:", total)
print("Unreadable images:", len(invalid))
print("Extensions:", dict(extensions))

if invalid:
    print("\nFirst 20 unreadable files:")
    for path in invalid[:20]:
        print(path)
