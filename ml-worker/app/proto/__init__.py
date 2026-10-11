import sys
from pathlib import Path

# Ensure proto directory is in sys.path for protoc-generated imports
_proto_dir = str(Path(__file__).resolve().parent)
if _proto_dir not in sys.path:
    sys.path.insert(0, _proto_dir)

from . import waste_inference_pb2, waste_inference_pb2_grpc

__all__ = ["waste_inference_pb2", "waste_inference_pb2_grpc"]

