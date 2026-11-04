from pathlib import Path
import pandas as pd

project = Path(__file__).resolve().parent

manifest = pd.read_csv(project / "split_manifest.csv")
errors = pd.read_csv(
    project / "training_outputs" / "crop_misclassified_images.csv"
)

# Select the 53 Tomato → Potato test images
mistakes = errors[
    (errors["actual_crop"] == "Tomato") &
    (errors["predicted_crop"] == "Potato")
]

excluded_paths = set(mistakes["image_path"])

# Create a separate experimental manifest
experiment = manifest[
    ~manifest["image_path"].isin(excluded_paths)
].copy()

output = project / "split_manifest_experiment.csv"
experiment.to_csv(output, index=False)

print("Images excluded:", len(manifest) - len(experiment))
print("Remaining images:", len(experiment))
print("Saved:", output)
