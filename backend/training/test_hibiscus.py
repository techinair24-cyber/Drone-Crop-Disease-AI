
from pathlib import Path
import json

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms, models

BASE_DIR = Path(__file__).parent
MODEL_PATH = BASE_DIR / "hibiscus_model.pth"
INFO_PATH = BASE_DIR / "hibiscus_model_info.json"

DEVICE = torch.device("cpu")

info = json.loads(INFO_PATH.read_text())
classes = info["classes"]

model = models.mobilenet_v2(weights=None)
model.classifier[1] = nn.Linear(model.last_channel, len(classes))

model.load_state_dict(
    torch.load(MODEL_PATH, map_location=DEVICE, weights_only=True)
)
model.eval()

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        [0.485, 0.456, 0.406],
        [0.229, 0.224, 0.225]
    )
])

image_path = Path(
    r"C:\Users\Deepthi MG\Desktop\Leaf Dataset\Hibiscus\Healthy\WhatsApp Image 2026-10-31 at 9.28.21 AM.jpeg"
)

image = Image.open(image_path).convert("RGB")
tensor = transform(image).unsqueeze(0)

with torch.no_grad():
    output = model(tensor)
    probabilities = torch.softmax(output, dim=1)[0]

print("\nHIBISCUS PREDICTION")
for index, class_name in enumerate(classes):
    print(f"{class_name}: {probabilities[index].item() * 100:.2f}%")

print("\nPredicted class:", classes[probabilities.argmax().item()])
print("\nNote: Experimental prediction, not a reliable diagnosis.")
