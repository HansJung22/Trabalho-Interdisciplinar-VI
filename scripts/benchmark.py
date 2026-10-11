import argparse
import csv
from io import BytesIO
import json
from pathlib import Path
import time
import urllib.request
import uuid

BACKEND_URL = "http://localhost:8080/api/v1"


def collect_images(dataset_dir: Path, max_count: int = 64) -> list[Path]:
    extensions = ("*.jpg", "*.jpeg", "*.png")
    images = []
    for ext in extensions:
        images.extend(dataset_dir.rglob(ext))
        if len(images) >= max_count:
            break
    return images[:max_count]


def run_experiment(images: list[Path], strategy: str, protocol: str) -> dict:
    boundary = uuid.uuid4().hex
    data = bytearray()

    for img in images:
        data.extend(f"--{boundary}\r\n".encode("utf-8"))
        data.extend(f'Content-Disposition: form-data; name="files"; filename="{img.name}"\r\n'.encode("utf-8"))
        data.extend(b"Content-Type: image/jpeg\r\n\r\n")
        with open(img, "rb") as f:
            data.extend(f.read())
        data.extend(b"\r\n")

    data.extend(f"--{boundary}--\r\n".encode("utf-8"))

    url = f"{BACKEND_URL}/classifications?strategy={strategy}&protocol={protocol}"
    req = urllib.request.Request(
        url,
        data=bytes(data),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )

    start = time.perf_counter()
    with urllib.request.urlopen(req) as resp:
        body = resp.read()
    client_elapsed_ms = (time.perf_counter() - start) * 1000.0

    parsed = json.loads(body.decode("utf-8"))
    parsed["clientElapsedMs"] = client_elapsed_ms
    return parsed


def benchmark(dataset_dir: str, batch_sizes: list[int], protocol: str = "grpc", repetitions: int = 3):
    img_paths = collect_images(Path(dataset_dir), max(batch_sizes))
    if len(img_paths) < max(batch_sizes):
        print(f"Warning: Found {len(img_paths)} images, which is less than max batch {max(batch_sizes)}")

    print("=" * 80)
    print(f" BENCHMARK: 1 Worker (Baseline) vs 2 Workers (Distributed) [{protocol.upper()}]")
    print(f" Repetitions per batch: {repetitions} | Dataset: {dataset_dir}")
    print("=" * 80 + "\n")

    # Warmup run
    print("Executing warmup run...")
    run_experiment(img_paths[:2], "single-worker", protocol)
    run_experiment(img_paths[:2], "distributed", protocol)
    print("Warmup complete.\n")

    results = []

    print(f"{'Batch Size':<12} | {'T1 (1 Worker)':<22} | {'T2 (2 Workers)':<22} | {'Speedup':<10} | {'Efficiency':<10}")
    print("-" * 88)

    for b in batch_sizes:
        current_images = img_paths[:b]
        t1_times = []
        t2_times = []

        for _ in range(repetitions):
            res_single = run_experiment(current_images, "single-worker", protocol)
            res_dist = run_experiment(current_images, "distributed", protocol)
            t1_times.append(res_single["elapsedMs"])
            t2_times.append(res_dist["elapsedMs"])

        avg_t1 = sum(t1_times) / len(t1_times)
        avg_t2 = sum(t2_times) / len(t2_times)
        speedup = avg_t1 / avg_t2 if avg_t2 > 0 else 0.0
        efficiency = (speedup / 2.0) * 100.0  # N = 2 workers

        row = {
            "batch_size": b,
            "t1_ms": round(avg_t1, 2),
            "t2_ms": round(avg_t2, 2),
            "speedup": round(speedup, 3),
            "efficiency_pct": round(efficiency, 1),
            "t1_throughput": round(b / (avg_t1 / 1000.0), 2),
            "t2_throughput": round(b / (avg_t2 / 1000.0), 2),
        }
        results.append(row)

        print(f"{b:<12} | {avg_t1:>8.2f} ms ({row['t1_throughput']:>5.1f} img/s) | {avg_t2:>8.2f} ms ({row['t2_throughput']:>5.1f} img/s) | {speedup:>8.2f}x | {efficiency:>8.1f}%")

    # Save to CSV
    csv_file = Path("benchmark_results.csv")
    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults successfully exported to '{csv_file.resolve()}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="dataset/Train_base", help="Dataset directory path")
    parser.add_argument("--protocol", default="grpc", choices=["grpc", "rest"], help="Communication protocol")
    parser.add_argument("--runs", type=int, default=3, help="Repetitions per batch size")
    args = parser.parse_args()

    # Standard batch size scaling: 2, 4, 8, 16, 32
    benchmark(args.data, [2, 4, 8, 16, 32], protocol=args.protocol, repetitions=args.runs)

