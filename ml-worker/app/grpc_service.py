from concurrent import futures
from io import BytesIO
import os
import time

import grpc
from PIL import Image

from app.model import WasteModel
from app.proto import waste_inference_pb2, waste_inference_pb2_grpc

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024  # 100 MB


class WasteInferenceServicer(waste_inference_pb2_grpc.WasteInferenceServiceServicer):
    def __init__(self, model: WasteModel, worker_id: str):
        self.model = model
        self.worker_id = worker_id

    def CheckHealth(self, request, context):
        return waste_inference_pb2.HealthResponse(
            status="UP",
            worker_id=self.worker_id,
            model_loaded=self.model.loaded,
            device=str(self.model.device),
        )

    def PredictBatch(self, request, context):
        start = time.perf_counter()
        predictions = []

        for item in request.images:
            try:
                image = Image.open(BytesIO(item.image_data))
                result = self.model.predict(image)
                if result is None:
                    predictions.append(
                        waste_inference_pb2.PredictionItem(
                            filename=item.filename,
                            status="MODEL_NOT_LOADED",
                            label="",
                            confidence=0.0,
                        )
                    )
                else:
                    label, confidence = result
                    predictions.append(
                        waste_inference_pb2.PredictionItem(
                            filename=item.filename,
                            status="OK",
                            label=label,
                            confidence=confidence,
                        )
                    )
            except Exception:
                predictions.append(
                    waste_inference_pb2.PredictionItem(
                        filename=item.filename,
                        status="INVALID_IMAGE",
                        label="",
                        confidence=0.0,
                    )
                )

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return waste_inference_pb2.BatchInferenceResponse(
            worker_id=self.worker_id,
            model_loaded=self.model.loaded,
            elapsed_ms=elapsed_ms,
            predictions=predictions,
        )


def create_grpc_server(model: WasteModel, worker_id: str, port: int = 50051) -> grpc.Server:
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_receive_message_length", MAX_MESSAGE_LENGTH),
            ("grpc.max_send_message_length", MAX_MESSAGE_LENGTH),
        ],
    )
    servicer = WasteInferenceServicer(model, worker_id)
    waste_inference_pb2_grpc.add_WasteInferenceServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    return server


if __name__ == "__main__":
    port = int(os.getenv("GRPC_PORT", "50051"))
    worker_id = os.getenv("WORKER_ID", "worker-grpc-standalone")
    model = WasteModel()
    server = create_grpc_server(model, worker_id, port)
    server.start()
    print(f"gRPC server [{worker_id}] listening on port {port}...")
    server.wait_for_termination()

