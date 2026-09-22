"""Canonical telemetry-processing package for the backend.

The Firebase client is loaded lazily so importing a Layer1 processor does not
require Firebase credentials or the optional admin SDK at module-import time.
"""

from .layer0 import Layer0IngestionPipeline, Layer0IngestionResult
from .layer1.pipelines import Layer1Result, PreprocessingPipeline


def __getattr__(name: str):
    if name == "FirebaseRTDBClient":
        from .infrastructure import FirebaseRTDBClient

        return FirebaseRTDBClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "FirebaseRTDBClient",
    "Layer0IngestionPipeline",
    "Layer0IngestionResult",
    "Layer1Result",
    "PreprocessingPipeline",
]
