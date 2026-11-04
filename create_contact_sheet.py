from pathlib import Path
import pandas as pd
from PIL import Image, ImageDraw
import math

PROJECT = Path(__file__).resolve().parent
OUTPUT = PROJECT / "training_outputs"

# Read misclassified image report
df = pd.read_csv(OUTPUT / "crop_misclassified_images.csv")

# Select Tomato images predicted as Potato
df = df[
    (df["actual_crop"] == "Tomato") &
    (df["predicted_crop"] == "Potato")
].reset_index(drop=True)

if len(df) == 0:
    print("No Tomato-to-Potato images found.")
    raise SystemExit

# Contact sheet settings
THUMB_W = 180
THUMB_H = 180
CELL_W = 210
CELL_H = 225
COLS = 5
ROWS = math.ceil(len(df) / COLS)

sheet = Image.new(
    "RGB",
    (COLS * CELL_W, ROWS * CELL_H),
    "white"
)

draw = ImageDraw.Draw(sheet)

for i, row in df.iterrows():
    path = Path(row["image_path"])

    try:
        img = Image.open(path).convert("RGB")
        img.thumbnail((THUMB_W, THUMB_H))

        x = (i % COLS) * CELL_W
        y = (i // COLS) * CELL_H

        img_x = x + (CELL_W - img.width) // 2
        sheet.paste(img, (img_x, y))

        draw.text(
            (x + 5, y + 183),
            f"Image {i + 1} | Confidence: {row['confidence']}",
            fill="black"
        )
        draw.text(
            (x + 5, y + 200),
            path.name[:28],
            fill="black"
        )

    except Exception as e:
        print(f"Could not load {path}: {e}")

# Save contact sheet
output_path = OUTPUT / "tomato_to_potato_review.jpg"
sheet.save(output_path, quality=90)

# Save image-number mapping
mapping = df.copy()
mapping.insert(0, "review_number", range(1, len(df) + 1))
mapping.to_csv(
    OUTPUT / "tomato_to_potato_mapping.csv",
    index=False
)

print("Images included:", len(df))
print("Contact sheet saved:", output_path)
print("Image mapping saved:", OUTPUT / "tomato_to_potato_mapping.csv")
