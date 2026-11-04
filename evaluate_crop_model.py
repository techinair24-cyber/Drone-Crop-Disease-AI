from pathlib import Path
import json
import numpy as np
import pandas as pd
import tensorflow as tf

from sklearn.metrics import (
    classification_report,
    confusion_matrix
)

PROJECT = Path(__file__).resolve().parent
OUTPUT = PROJECT / "training_outputs"

IMAGE_SIZE = (160, 160)
BATCH_SIZE = 16

df = pd.read_csv(PROJECT / "split_manifest_experiment.csv")
test_df = df[df["split"] == "test"].copy()

with open(OUTPUT / "crop_class_names.json") as f:
    class_names = json.load(f)

model = tf.keras.models.load_model(
    OUTPUT / "crop_classifier_best.keras"
)

class_to_index = {
    name: index for index, name in enumerate(class_names)
}

def load_image(path, label):
    image = tf.io.read_file(path)
    image = tf.io.decode_image(
        image, channels=3, expand_animations=False
    )
    image.set_shape([None, None, 3])
    image = tf.image.resize(image, IMAGE_SIZE)
    image = tf.cast(image, tf.float32)
    image = tf.keras.applications.mobilenet_v2.preprocess_input(image)
    return image, label

paths = test_df["image_path"].astype(str).values

labels = test_df["crop"].map(
    class_to_index
).values.astype("int32")

dataset = tf.data.Dataset.from_tensor_slices((paths, labels))

dataset = dataset.map(
    load_image,
    num_parallel_calls=2
).batch(BATCH_SIZE).prefetch(1)

y_true = []
y_pred = []

for images, targets in dataset:
    predictions = model.predict(images, verbose=0)
    y_true.extend(targets.numpy())
    y_pred.extend(np.argmax(predictions, axis=1))

print("\n========== CLASSIFICATION REPORT ==========")

print(classification_report(
    y_true,
    y_pred,
    labels=list(range(len(class_names))),
    target_names=class_names,
    digits=4,
    zero_division=0
))

print("\n========== CONFUSION MATRIX ==========")

matrix = confusion_matrix(
    y_true,
    y_pred,
    labels=list(range(len(class_names)))
)

print(pd.DataFrame(
    matrix,
    index=class_names,
    columns=class_names
))

print("\nEvaluation completed.")
