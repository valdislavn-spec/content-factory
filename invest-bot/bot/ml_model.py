"""Tiny JSON logistic-regression model (stdlib only)."""
from __future__ import annotations

import json
import math
from pathlib import Path


class LogitModel:
    def __init__(self, payload: dict):
        self.features: list[str] = payload["features"]
        self.mean: list[float] = payload["mean"]
        self.std: list[float] = payload["std"]
        self.weights: list[float] = payload["weights"]
        self.bias: float = payload["bias"]
        self.horizon: int = payload.get("horizon", 6)
        self.threshold: float = payload.get("threshold", 0.55)

    @classmethod
    def load(cls, path: str | Path) -> "LogitModel":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def predict(self, features: dict[str, float]) -> float:
        z = self.bias
        for name, mean, std, weight in zip(self.features, self.mean, self.std, self.weights):
            x = (float(features.get(name, 0.0)) - mean) / (std or 1.0)
            z += weight * x
        return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))
