from pathlib import Path
from collections import defaultdict, Counter
import hashlib
import random
import csv

DATASET = Path.home() / "Desktop" / "Leaf Dataset"
OUTPUT = Path.cwd() / "split_manifest.csv"

CROPS = [
    "Maize", "Hibiscus", "Tomato", "Chilli", "Wheat",
    "Apple", "Grape", "Potato", "Peach", "Strawberry"
]

LABELS = ["Healthy", "Unhealthy"]
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

SEED = 42
rng = random.Random(SEED)

rows = []
summary = Counter()

for crop in CROPS:
    for label in LABELS:
        folder = DATASET / crop / label

        if not folder.is_dir():
            raise FileNotFoundError(f"Missing folder: {folder}")

        # Group byte-identical files together
        groups = defaultdict(list)

        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                groups[digest].append(path)

        unique_groups = list(groups.items())
        rng.shuffle(unique_groups)

        n = len(unique_groups)
        train_end = int(n * 0.70)
        val_end = train_end + int(n * 0.15)

        assignments = [
            ("train", unique_groups[:train_end]),
            ("validation", unique_groups[train_end:val_end]),
            ("test", unique_groups[val_end:])
        ]

        for split, assigned_groups in assignments:
            for digest, paths in assigned_groups:
                # Use one representative; retain original files untouched
                rows.append({
                    "image_path": str(paths[0]),
                    "crop": crop,
                    "health": label,
                    "split": split,
                    "sha256": digest,
                    "duplicate_copies_excluded": len(paths) - 1
                })

                summary[(crop, label, split)] += 1

with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=[
            "image_path", "crop", "health", "split",
            "sha256", "duplicate_copies_excluded"
        ]
    )
    writer.writeheader()
    writer.writerows(rows)

print("\n========== SPLIT SUMMARY ==========")

for split in ["train", "validation", "test"]:
    count = sum(
        value for (crop, label, part), value in summary.items()
        if part == split
    )
    print(f"{split}: {count} images")

print("\n========== TOTAL ==========")
print("Unique images included:", len(rows))
print("Duplicate copies excluded:", sum(
    row["duplicate_copies_excluded"] for row in rows
))

print("\n========== CROP AND CLASS COUNTS ==========")

for crop in CROPS:
    print(f"\n{crop}")
    for label in LABELS:
        counts = [
            summary[(crop, label, split)]
            for split in ["train", "validation", "test"]
        ]
        print(
            f"  {label}: "
            f"Train={counts[0]}, "
            f"Validation={counts[1]}, "
            f"Test={counts[2]}"
        )

print("\nManifest saved to:", OUTPUT)
print("Original dataset was not modified.")
