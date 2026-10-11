from contextlib import asynccontextmanager
from io import BytesIO
import os
import time

from fastapi import FastAPI, File, UploadFile
from PIL import Image

from app.grpc_service import create_grpc_server
from app.model import WasteModel

worker_id = os.getenv("WORKER_ID", "worker-local")
grpc_port = int(os.getenv("GRPC_PORT", "50051"))
model = WasteModel()
grpc_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global grpc_server
    grpc_server = create_grpc_server(model, worker_id, grpc_port)
    grpc_server.start()
    print(f"[{worker_id}] gRPC server running on port {grpc_port}")
    try:
        yield
    finally:
        if grpc_server:
            grpc_server.stop(grace=1.0)
            print(f"[{worker_id}] gRPC server stopped")


app = FastAPI(title="Waste ML Worker", version="0.2.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "UP",
        "workerId": worker_id,
        "modelLoaded": model.loaded,
        "device": str(model.device),
    }


@app.post("/predict/batch")
async def predict_batch(files: list[UploadFile] = File(...)):
    start = time.perf_counter()
    predictions = []

    for file in files:
        content = await file.read()
        try:
            image = Image.open(BytesIO(content))
            result = model.predict(image)
            if result is None:
                predictions.append({
                    "filename": file.filename,
                    "status": "MODEL_NOT_LOADED",
                    "label": None,
                    "confidence": None,
                })
            else:
                label, confidence = result
                predictions.append({
                    "filename": file.filename,
                    "status": "OK",
                    "label": label,
                    "confidence": confidence,
                })
        except Exception:
            predictions.append({
                "filename": file.filename,
                "status": "INVALID_IMAGE",
                "label": None,
                "confidence": None,
            })

    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "workerId": worker_id,
        "modelLoaded": model.loaded,
        "elapsedMs": elapsed_ms,
        "predictions": predictions,
    }
