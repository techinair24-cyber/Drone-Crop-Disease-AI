from pathlib import Path
import json
import numpy as np
import pandas as pd
import tensorflow as tf

PROJECT = Path(__file__).resolve().parent
OUTPUT = PROJECT / "training_outputs"

df = pd.read_csv(PROJECT / "split_manifest.csv")
test_df = df[df["split"] == "test"].copy()

with open(OUTPUT / "crop_class_names.json") as f:
    class_names = json.load(f)

model = tf.keras.models.load_model(
    OUTPUT / "crop_classifier_best.keras"
)

index_to_class = {i: name for i, name in enumerate(class_names)}

errors = []

for _, row in test_df.iterrows():
    image = tf.keras.utils.load_img(
        row["image_path"],
        target_size=(160, 160)
    )

    image = tf.keras.utils.img_to_array(image)
    image = tf.keras.applications.mobilenet_v2.preprocess_input(image)
    image = np.expand_dims(image, axis=0)

    probabilities = model.predict(image, verbose=0)[0]

    predicted_index = int(np.argmax(probabilities))
    predicted_crop = index_to_class[predicted_index]
    confidence = float(probabilities[predicted_index])

    if predicted_crop != row["crop"]:
        errors.append({
            "actual_crop": row["crop"],
            "predicted_crop": predicted_crop,
            "confidence": round(confidence, 4),
            "image_path": row["image_path"]
        })

error_df = pd.DataFrame(errors)

error_path = OUTPUT / "crop_misclassified_images.csv"
error_df.to_csv(error_path, index=False)

print("Total test images:", len(test_df))
print("Misclassified images:", len(errors))
print("Error report:", error_path)

if len(errors):
    print("\nMost common mistakes:")
    print(
        error_df.groupby(
            ["actual_crop", "predicted_crop"]
        ).size().sort_values(ascending=False).head(15)
    )
