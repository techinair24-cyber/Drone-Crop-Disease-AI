from pathlib import Path
import csv
import json

import numpy as np
import pandas as pd
import tensorflow as tf


PROJECT = Path(__file__).resolve().parent
MANIFEST = PROJECT / "split_manifest_experiment.csv"
OUTPUT = PROJECT / "training_outputs"

IMAGE_SIZE = (160, 160)
BATCH_SIZE = 16
EPOCHS = 10
SEED = 42
CLASS_NAMES = ["Healthy", "Unhealthy"]
CLASS_TO_INDEX = {name: index for index, name in enumerate(CLASS_NAMES)}
SPLITS = ("train", "validation", "test")

tf.keras.utils.set_random_seed(SEED)
OUTPUT.mkdir(parents=True, exist_ok=True)


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


def make_dataset(frame, training=False):
    paths = frame["image_path"].astype(str).values
    labels = frame["health"].map(CLASS_TO_INDEX).values.astype("int32")

    dataset = tf.data.Dataset.from_tensor_slices((paths, labels))
    if training:
        dataset = dataset.shuffle(
            len(frame), seed=SEED, reshuffle_each_iteration=True
        )

    return (
        dataset
        .map(load_image, num_parallel_calls=2)
        .batch(BATCH_SIZE)
        .prefetch(1)
    )


def write_evaluation_report(y_true, y_pred):
    confusion = np.zeros((len(CLASS_NAMES), len(CLASS_NAMES)), dtype=np.int64)
    for actual, predicted in zip(y_true, y_pred):
        confusion[int(actual), int(predicted)] += 1

    confusion_path = OUTPUT / "health_confusion_matrix.csv"
    with confusion_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["actual/predicted", *CLASS_NAMES])
        for class_name, row in zip(CLASS_NAMES, confusion):
            writer.writerow([class_name, *row.tolist()])

    report_path = OUTPUT / "health_classification_report.csv"
    report_rows = []
    for index, class_name in enumerate(CLASS_NAMES):
        true_positive = int(confusion[index, index])
        false_positive = int(confusion[:, index].sum() - true_positive)
        false_negative = int(confusion[index, :].sum() - true_positive)
        support = int(confusion[index, :].sum())
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive else 0.0
        )
        recall = true_positive / support if support else 0.0
        f1_score = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
        report_rows.append({
            "class": class_name,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "support": support,
        })

    pd.DataFrame(report_rows).to_csv(report_path, index=False)
    return confusion


def main():
    if not MANIFEST.is_file():
        raise FileNotFoundError(f"Split manifest not found: {MANIFEST}")

    print("TensorFlow:", tf.__version__)
    print("Loading split manifest:", MANIFEST)
    frame = pd.read_csv(MANIFEST)

    required_columns = {"image_path", "health", "split"}
    missing_columns = required_columns - set(frame.columns)
    if missing_columns:
        raise ValueError(
            f"Manifest is missing required columns: {sorted(missing_columns)}"
        )

    frame["health"] = frame["health"].astype("string").str.strip()
    unknown_labels = sorted(
        set(frame["health"].dropna().unique()) - set(CLASS_NAMES)
    )
    if unknown_labels or frame["health"].isna().any():
        raise ValueError(
            f"Manifest contains missing or unsupported health labels: {unknown_labels}"
        )

    unknown_splits = sorted(
        set(frame["split"].dropna().unique()) - set(SPLITS)
    )
    if unknown_splits or frame["split"].isna().any():
        raise ValueError(f"Manifest contains unsupported splits: {unknown_splits}")

    frames = {
        split: frame[frame["split"] == split].copy()
        for split in SPLITS
    }
    for split, split_frame in frames.items():
        if split_frame.empty:
            raise ValueError(f"The manifest has no {split} images.")
        if split_frame["image_path"].isna().any():
            raise ValueError(f"The {split} split contains empty image paths.")

    train_frame = frames["train"]
    train_counts = train_frame["health"].value_counts()
    missing_training_labels = set(CLASS_NAMES) - set(train_counts.index)
    if missing_training_labels:
        raise ValueError(
            f"Training split is missing classes: {sorted(missing_training_labels)}"
        )

    train_dataset = make_dataset(train_frame, training=True)
    validation_dataset = make_dataset(frames["validation"])
    test_dataset = make_dataset(frames["test"])

    class_weights = {
        CLASS_TO_INDEX[class_name]:
            len(train_frame) / (len(CLASS_NAMES) * int(train_counts[class_name]))
        for class_name in CLASS_NAMES
    }
    print("Split sizes:", {split: len(data) for split, data in frames.items()})
    print("Training class weights:", class_weights)

    base_model = tf.keras.applications.MobileNetV2(
        input_shape=(*IMAGE_SIZE, 3),
        include_top=False,
        weights="imagenet",
    )
    base_model.trainable = False

    inputs = tf.keras.Input(shape=(*IMAGE_SIZE, 3))
    features = base_model(inputs, training=False)
    features = tf.keras.layers.GlobalAveragePooling2D()(features)
    features = tf.keras.layers.Dropout(0.25)(features)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid")(features)
    model = tf.keras.Model(inputs, outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="binary_crossentropy",
        metrics=["accuracy"],
    )
    model.summary()

    best_model_path = OUTPUT / "health_classifier_best.keras"
    final_model_path = OUTPUT / "health_classifier_final.keras"
    callbacks = [
        tf.keras.callbacks.ModelCheckpoint(
            best_model_path,
            monitor="val_loss",
            save_best_only=True,
            verbose=1,
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=3,
            restore_best_weights=True,
            verbose=1,
        ),
        tf.keras.callbacks.CSVLogger(
            OUTPUT / "health_training_history.csv"
        ),
    ]

    model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=EPOCHS,
        class_weight=class_weights,
        callbacks=callbacks,
    )

    model.save(final_model_path)
    with (OUTPUT / "health_class_names.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(CLASS_NAMES, file, indent=4)

    best_model = tf.keras.models.load_model(best_model_path)
    test_loss, test_accuracy = best_model.evaluate(test_dataset, verbose=1)
    probabilities = best_model.predict(test_dataset, verbose=1).reshape(-1)
    y_true = frames["test"]["health"].map(CLASS_TO_INDEX).values.astype("int32")
    y_pred = (probabilities >= 0.5).astype("int32")
    confusion = write_evaluation_report(y_true, y_pred)

    metrics = {
        "test_loss": float(test_loss),
        "test_accuracy": float(test_accuracy),
        "test_images": int(len(y_true)),
        "class_names": CLASS_NAMES,
        "confusion_matrix": confusion.tolist(),
        "decision_threshold": 0.5,
    }
    metrics_path = OUTPUT / "health_test_metrics.json"
    with metrics_path.open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=4)

    print("\n========== HEALTH CLASSIFIER TEST RESULTS ==========")
    print("Test loss:", round(float(test_loss), 4))
    print("Test accuracy:", round(float(test_accuracy) * 100, 2), "%")
    print("Best model:", best_model_path)
    print("Final model:", final_model_path)
    print("Classification report:", OUTPUT / "health_classification_report.csv")
    print("Confusion matrix:", OUTPUT / "health_confusion_matrix.csv")
    print("Test metrics:", metrics_path)


if __name__ == "__main__":
    main()
