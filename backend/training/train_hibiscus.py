
from pathlib import Path
import json
import random

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split
from torchvision import datasets, transforms, models

# Dataset and output paths
DATASET_DIR = Path(
    r"C:\Users\Deepthi MG\Desktop\Leaf Dataset\Hibiscus"
)
OUTPUT_DIR = Path(__file__).parent
MODEL_PATH = OUTPUT_DIR / "hibiscus_model.pth"
INFO_PATH = OUTPUT_DIR / "hibiscus_model_info.json"

# Reproducibility
SEED = 42
random.seed(SEED)
torch.manual_seed(SEED)

# Training settings
IMAGE_SIZE = 224
BATCH_SIZE = 2
EPOCHS = 5
LEARNING_RATE = 0.001

DEVICE = torch.device("cpu")

# Image preprocessing and augmentation
train_transform = transforms.Compose([
    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomRotation(15),
    transforms.ColorJitter(
        brightness=0.15, contrast=0.15, saturation=0.15
    ),
    transforms.ToTensor(),
    transforms.Normalize(
        [0.485, 0.456, 0.406],
        [0.229, 0.224, 0.225]
    )
])

eval_transform = transforms.Compose([
    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(
        [0.485, 0.456, 0.406],
        [0.229, 0.224, 0.225]
    )
])


def main():
    if not DATASET_DIR.exists():
        raise FileNotFoundError(DATASET_DIR)

    # Load dataset
    dataset = datasets.ImageFolder(DATASET_DIR)
    print("Classes:", dataset.classes)
    print("Total images:", len(dataset))

    if len(dataset) < 4:
        raise ValueError("Not enough images.")

    # Use a fixed split for this prototype
    train_size = 7
    validation_size = len(dataset) - train_size

    generator = torch.Generator().manual_seed(SEED)
    train_subset, val_subset = random_split(
        dataset, [train_size, validation_size],
        generator=generator
    )

    # Apply separate transforms
    train_subset.dataset = datasets.ImageFolder(
        DATASET_DIR, transform=train_transform
    )
    val_subset.dataset = datasets.ImageFolder(
        DATASET_DIR, transform=eval_transform
    )

    train_loader = DataLoader(
        train_subset, batch_size=BATCH_SIZE, shuffle=True
    )
    val_loader = DataLoader(
        val_subset, batch_size=BATCH_SIZE
    )

    # Pretrained MobileNetV2
    try:
        weights = models.MobileNet_V2_Weights.DEFAULT
        model = models.mobilenet_v2(weights=weights)
        print("Loaded pretrained MobileNetV2.")
    except Exception as error:
        raise RuntimeError(
            "Could not download pretrained MobileNetV2 weights. "
            "Check internet access and try again."
        ) from error

    # Freeze feature extractor
    for parameter in model.features.parameters():
        parameter.requires_grad = False

    model.classifier[1] = nn.Linear(
        model.last_channel, len(dataset.classes)
    )
    model = model.to(DEVICE)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(
        model.classifier.parameters(), lr=LEARNING_RATE
    )

    # Training
    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0.0

        for images, labels in train_loader:
            images, labels = images.to(DEVICE), labels.to(DEVICE)

            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        # Validation
        model.eval()
        correct = 0
        total = 0

        with torch.no_grad():
            for images, labels in val_loader:
                outputs = model(images.to(DEVICE))
                predictions = outputs.argmax(dim=1)
                correct += (predictions == labels).sum().item()
                total += labels.size(0)

        accuracy = correct / total if total else 0
        print(
            f"Epoch {epoch + 1}/{EPOCHS} | "
            f"Loss: {total_loss / len(train_loader):.4f} | "
            f"Validation accuracy: {accuracy:.2%}"
        )

    # Save model
    torch.save(model.state_dict(), MODEL_PATH)

    info = {
        "plant": "Hibiscus",
        "classes": dataset.classes,
        "image_size": IMAGE_SIZE,
        "architecture": "MobileNetV2",
        "prototype": True,
        "training_images": train_size,
        "validation_images": validation_size,
        "warning": "Experimental model trained on only 9 images."
    }

    INFO_PATH.write_text(json.dumps(info, indent=4))

    print("\nTraining completed.")
    print("Model saved:", MODEL_PATH)
    print("Model information saved:", INFO_PATH)
    print("WARNING: This prototype is not suitable for reliable diagnosis.")


if __name__ == "__main__":
    main()
