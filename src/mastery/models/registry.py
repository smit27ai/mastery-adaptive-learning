"""Model registry and the inference fallback chain.

Two rules this file exists to enforce:

1. Models are loaded ONCE at startup, never per request. Loading per request turns a
   50ms endpoint into a 3s endpoint.
2. Inference degrades instead of failing. DKT -> BKT -> item difficulty -> uniform.
   The live demo must never return a 500.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from mastery.common.config import get_settings
from mastery.common.logging import get_logger
from mastery.features.builder import FEATURE_NAMES
from mastery.models.bkt import BKTParams, predict_correct

log = get_logger(__name__)


class Predictor(Protocol):
    name: str

    def p_correct(self, features: dict[str, float], mastery: float, params: BKTParams) -> float: ...


@dataclass
class DKTPredictor:
    """Deep knowledge tracing served through ONNX Runtime.

    Training happens in PyTorch on a free Colab/Kaggle GPU; only the exported .onnx file
    ships in the image. That keeps the container ~250MB instead of ~2.5GB and removes
    torch from the production dependency tree entirely.
    """

    session: Any
    name: str = "dkt-onnx"

    def p_correct(self, features: dict[str, float], mastery: float, params: BKTParams) -> float:
        import numpy as np

        vector = np.array([[features[n] for n in FEATURE_NAMES]], dtype=np.float32)
        out = self.session.run(None, {self.session.get_inputs()[0].name: vector})
        return float(min(max(out[0].ravel()[0], 0.0), 1.0))

    @classmethod
    def try_load(cls, path: Path) -> DKTPredictor | None:
        if not path.exists():
            log.info("model.dkt.absent", path=str(path))
            return None
        try:
            import onnxruntime as ort

            sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            log.info("model.dkt.loaded", path=str(path))
            return cls(session=sess)
        except Exception as exc:
            log.warning("model.dkt.load_failed", error=str(exc))
            return None


@dataclass
class BKTPredictor:
    """Always available. Pure arithmetic, no artifacts, cannot fail to load."""

    name: str = "bkt"

    def p_correct(self, features: dict[str, float], mastery: float, params: BKTParams) -> float:
        return predict_correct(mastery, params)


@dataclass
class ItemDifficultyPredictor:
    """Last resort before uniform: the population p-value of the item."""

    name: str = "item-p-value"

    def p_correct(self, features: dict[str, float], mastery: float, params: BKTParams) -> float:
        return float(features.get("item_p_value", 0.5))


class ModelRegistry:
    """Holds every loaded model for the lifetime of the process."""

    def __init__(self) -> None:
        self.version: str = "unloaded"
        self.chain: list[Predictor] = []
        self.embedder: Any | None = None
        self.risk_model: Any | None = None

    def load(self) -> None:
        settings = get_settings()
        self.version = settings.model_version

        chain: list[Predictor] = []
        dkt = DKTPredictor.try_load(settings.model_dir / "dkt.onnx")
        if dkt is not None:
            chain.append(dkt)
        chain.append(BKTPredictor())
        chain.append(ItemDifficultyPredictor())
        self.chain = chain

        log.info("model.registry.loaded", version=self.version, chain=[p.name for p in chain])

    def predict(
        self, features: dict[str, float], mastery: float, params: BKTParams
    ) -> tuple[float, str]:
        """Walk the fallback chain. Return (probability, which model actually answered)."""
        for predictor in self.chain:
            try:
                value = predictor.p_correct(features, mastery, params)
                if 0.0 <= value <= 1.0:
                    return value, predictor.name
                log.warning("model.out_of_range", model=predictor.name, value=value)
            except Exception as exc:
                log.warning("model.predict_failed", model=predictor.name, error=str(exc))
        return 0.5, "uniform-fallback"

    @property
    def ready(self) -> bool:
        return bool(self.chain)


registry = ModelRegistry()
