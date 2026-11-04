from pathlib import Path
import json
import numpy as np
import pandas as pd
import tensorflow as tf

# ---------------- CONFIGURATION ----------------

PROJECT = Path(__file__).resolve().parent
MANIFEST = PROJECT / "split_manifest_experiment.csv"
OUTPUT = PROJECT / "training_outputs"

OUTPUT.mkdir(exist_ok=True)

IMAGE_SIZE = (160, 160)
BATCH_SIZE = 16
EPOCHS = 10
SEED = 42

tf.keras.utils.set_random_seed(SEED)

print("TensorFlow:", tf.__version__)
print("Training device: CPU")
print("Loading split manifest...")

df = pd.read_csv(MANIFEST)

CROPS = sorted(df["crop"].unique().tolist())

print("Crop classes:", CROPS)

# ---------------- DATA PREPARATION ----------------

def load_image(path, label):
    image = tf.io.read_file(path)
    image = tf.io.decode_image(
        image, channels=3, expand_animations=False
    )
    image.set_shape([None, None, 3])

    image = tf.image.resize(image, IMAGE_SIZE)
    image = tf.cast(image, tf.float32)

    # MobileNetV2 preprocessing: pixels from [0,255] to [-1,1]
    image = tf.keras.applications.mobilenet_v2.preprocess_input(image)

    return image, label


def make_dataset(frame, training=False):
    paths = frame["image_path"].astype(str).values
    labels = frame["crop"].map(
        {name: i for i, name in enumerate(CROPS)}
    ).values.astype("int32")

    dataset = tf.data.Dataset.from_tensor_slices((paths, labels))

    if training:
        dataset = dataset.shuffle(
            len(frame), seed=SEED, reshuffle_each_iteration=True
        )

    dataset = dataset.map(
        load_image,
        num_parallel_calls=2
    )

    dataset = dataset.batch(BATCH_SIZE)
    dataset = dataset.prefetch(1)

    return dataset


train_df = df[df["split"] == "train"].copy()
val_df = df[df["split"] == "validation"].copy()
test_df = df[df["split"] == "test"].copy()

train_ds = make_dataset(train_df, training=True)
val_ds = make_dataset(val_df)
test_ds = make_dataset(test_df)

# ---------------- CLASS WEIGHTS ----------------

counts = train_df["crop"].value_counts()

class_weights = {
    i: len(train_df) / (len(CROPS) * counts[crop])
    for i, crop in enumerate(CROPS)
}

print("\nClass weights:")
print(class_weights)

# ---------------- MODEL ----------------

print("\nLoading MobileNetV2 base model...")

base_model = tf.keras.applications.MobileNetV2(
    input_shape=(160, 160, 3),
    include_top=False,
    weights="imagenet"
)

base_model.trainable = False

inputs = tf.keras.Input(shape=(160, 160, 3))

x = base_model(inputs, training=False)
x = tf.keras.layers.GlobalAveragePooling2D()(x)
x = tf.keras.layers.Dropout(0.25)(x)

outputs = tf.keras.layers.Dense(
    len(CROPS),
    activation="softmax"
)(x)

model = tf.keras.Model(inputs, outputs)

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

model.summary()

# ---------------- CALLBACKS ----------------

best_model_path = OUTPUT / "crop_classifier_best.keras"

callbacks = [
    tf.keras.callbacks.ModelCheckpoint(
        best_model_path,
        monitor="val_accuracy",
        save_best_only=True,
        verbose=1
    ),
    tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=3,
        restore_best_weights=True,
        verbose=1
    ),
    tf.keras.callbacks.CSVLogger(
        OUTPUT / "crop_training_history.csv"
    )
]

# ---------------- TRAINING ----------------

print("\nStarting crop classification training...")

history = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS,
    class_weight=class_weights,
    callbacks=callbacks
)

# ---------------- SAVE FINAL MODEL ----------------

final_path = OUTPUT / "crop_classifier_final.keras"
model.save(final_path)

with open(OUTPUT / "crop_class_names.json", "w") as f:
    json.dump(CROPS, f, indent=4)

print("\nEvaluating on untouched test data...")

best_model = tf.keras.models.load_model(best_model_path)

test_loss, test_accuracy = best_model.evaluate(test_ds)

print("\n========== TEST RESULTS ==========")
print("Test loss:", round(float(test_loss), 4))
print("Test accuracy:", round(float(test_accuracy) * 100, 2), "%")

print("\nCrop classifier training completed.")
print("Best model:", best_model_path)
print("Final model:", final_path)
