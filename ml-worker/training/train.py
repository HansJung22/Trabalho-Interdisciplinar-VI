import argparse
from pathlib import Path
import random

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms
from torchvision.models import EfficientNet_V2_S_Weights, efficientnet_v2_s

def split_indices(size, seed=42):
    indices = list(range(size))
    random.Random(seed).shuffle(indices)
    train_end = int(size * 0.70)
    val_end = int(size * 0.85)
    return indices[:train_end], indices[train_end:val_end], indices[val_end:]


def make_datasets(data_dir):
    train_transform = transforms.Compose([
        transforms.Resize((384, 384)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(12),
        transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.15),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    eval_transform = transforms.Compose([
        transforms.Resize((384, 384)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    base = datasets.ImageFolder(data_dir)
    train_idx, val_idx, test_idx = split_indices(len(base))

    train_full = datasets.ImageFolder(data_dir, transform=train_transform)
    eval_full = datasets.ImageFolder(data_dir, transform=eval_transform)

    return (
        Subset(train_full, train_idx),
        Subset(eval_full, val_idx),
        Subset(eval_full, test_idx),
        base.classes,
    )


def evaluate(model, loader, device):
    model.eval()
    correct = 0
    total = 0
    with torch.inference_mode():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            predictions = model(images).argmax(dim=1)
            correct += (predictions == labels).sum().item()
            total += labels.size(0)
    return correct / total if total else 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--output", default="models/waste_mobilenet.pt")
    parser.add_argument("--no-pretrained", action="store_true")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_set, val_set, test_set, class_names = make_datasets(args.data)

    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_set, batch_size=args.batch_size, shuffle=False, num_workers=2)
    test_loader = DataLoader(test_set, batch_size=args.batch_size, shuffle=False, num_workers=2)

    weights = None if args.no_pretrained else EfficientNet_V2_S_Weights.DEFAULT
    model = efficientnet_v2_s(weights=weights)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(class_names))
    model.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    criterion = nn.CrossEntropyLoss()

    best_val = -1.0
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        for images, labels in train_loader:
            images = images.to(device)
            labels = labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()

        val_accuracy = evaluate(model, val_loader, device)
        print(f"epoch={epoch} val_accuracy={val_accuracy:.4f}")

        if val_accuracy > best_val:
            best_val = val_accuracy
            torch.save({
                "architecture": "efficientnet_v2_s",
                "class_names": class_names,
                "state_dict": model.state_dict(),
                "val_accuracy": val_accuracy,
            }, output)

    checkpoint = torch.load(output, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["state_dict"])
    test_accuracy = evaluate(model, test_loader, device)
    print(f"best_val_accuracy={best_val:.4f}")
    print(f"test_accuracy={test_accuracy:.4f}")
    print(f"model={output}")


if __name__ == "__main__":
    main()
