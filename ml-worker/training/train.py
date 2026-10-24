import argparse
import os
from pathlib import Path
import random
import time

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


def evaluate(model, loader, device, use_amp=False):
    model.eval()
    correct = 0
    total = 0
    with torch.inference_mode():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            with torch.amp.autocast("cuda", enabled=(use_amp and device.type == "cuda")):
                predictions = model(images).argmax(dim=1)
            correct += (predictions == labels).sum().item()
            total += labels.size(0)
    return correct / total if total else 0.0


def main():
    parser = argparse.ArgumentParser(description="Parallel GPU training for Waste Classification")
    parser.add_argument("--data", required=True, help="Path to image dataset folder")
    parser.add_argument("--epochs", type=int, default=10, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size per training step")
    parser.add_argument("--workers", type=int, default=4, help="DataLoader parallel CPU workers")
    parser.add_argument("--output", default="models/waste_mobilenet.pt", help="Path to save trained weights")
    parser.add_argument("--no-pretrained", action="store_true", help="Train from scratch without ImageNet weights")
    parser.add_argument("--no-amp", action="store_true", help="Disable Automatic Mixed Precision (Tensor Cores)")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = (device.type == "cuda") and not args.no_amp

    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
        gpu_name = torch.cuda.get_device_name(0)
        gpu_capability = torch.cuda.get_device_capability(0)
        print("=" * 60)
        print(f"Parallel GPU Training: {gpu_name}")
        print(f"Compute Capability: {gpu_capability[0]}.{gpu_capability[1]}")
        print(f"cuDNN Autotuner Benchmark: ENABLED")
        print(f"Automatic Mixed Precision (Tensor Cores): {'ENABLED' if use_amp else 'DISABLED'}")
        print(f"Host-to-Device Memory Pinning: ENABLED")
        print(f"DataLoader CPU Worker Threads: {args.workers}")
        print("=" * 60)
    else:
        print("=" * 60)
        print("Running on CPU (CUDA is not available)")
        print(f"DataLoader CPU Worker Threads: {args.workers}")
        print("=" * 60)

    train_set, val_set, test_set, class_names = make_datasets(args.data)

    pin_mem = (device.type == "cuda")
    persist_workers = (args.workers > 0)

    train_loader = DataLoader(
        train_set,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.workers,
        pin_memory=pin_mem,
        persistent_workers=persist_workers
    )
    val_loader = DataLoader(
        val_set,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=pin_mem,
        persistent_workers=persist_workers
    )
    test_loader = DataLoader(
        test_set,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=pin_mem,
        persistent_workers=persist_workers
    )

    weights = None if args.no_pretrained else EfficientNet_V2_S_Weights.DEFAULT
    model = efficientnet_v2_s(weights=weights)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(class_names))
    model.to(device)

    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    criterion = nn.CrossEntropyLoss()

    best_val = -1.0
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"\nStarting training on {len(train_set)} images (Validation: {len(val_set)}, Test: {len(test_set)})...")

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_start = time.perf_counter()
        running_loss = 0.0
        total_train_samples = 0

        for images, labels in train_loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            optimizer.zero_grad(set_to_none=True)

            with torch.amp.autocast("cuda", enabled=use_amp):
                outputs = model(images)
                loss = criterion(outputs, labels)

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            running_loss += loss.item() * images.size(0)
            total_train_samples += images.size(0)

        epoch_time = time.perf_counter() - epoch_start
        throughput = total_train_samples / epoch_time if epoch_time > 0 else 0.0
        avg_loss = running_loss / total_train_samples if total_train_samples > 0 else 0.0

        val_accuracy = evaluate(model, val_loader, device, use_amp=use_amp)
        print(f"epoch={epoch:02d}/{args.epochs:02d} | loss={avg_loss:.4f} | val_accuracy={val_accuracy:.4f} | time={epoch_time:.2f}s ({throughput:.1f} imgs/s)")

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
    test_accuracy = evaluate(model, test_loader, device, use_amp=use_amp)

    print("\n" + "=" * 60)
    print("TRAINING COMPLETED")
    print(f"Best Validation Accuracy: {best_val:.4f}")
    print(f"Final Test Accuracy:       {test_accuracy:.4f}")
    print(f"Model saved to:            {output.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
