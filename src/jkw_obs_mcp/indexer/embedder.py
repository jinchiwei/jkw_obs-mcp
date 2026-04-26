"""Embedder abstraction. Default implementation uses fastembed (ONNX)."""

from __future__ import annotations

from typing import Protocol

from fastembed import TextEmbedding


class Embedder(Protocol):
    """Protocol for any embedder. Returns Python lists of floats so callers
    don't need to know about numpy."""

    @property
    def dimension(self) -> int: ...
    def embed_one(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class FastembedEmbedder:
    """fastembed-backed embedder. ONNX, no torch required."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)
        # Probe the dim with a tiny sentence so we don't bake assumptions in.
        sample = next(iter(self._model.embed(["dim probe"])))
        self._dimension = len(sample)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_one(self, text: str) -> list[float]:
        vec = next(iter(self._model.embed([text])))
        return [float(x) for x in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._model.embed(texts)]
