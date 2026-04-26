"""Tests for the embedder. Uses the real fastembed model — slow on first run
(downloads ~30MB), fast thereafter (cached in ~/.cache/fastembed/)."""

import pytest

from jkw_obs_mcp.indexer.embedder import FastembedEmbedder


@pytest.fixture(scope="module")
def embedder() -> FastembedEmbedder:
    return FastembedEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")


def test_embedder_returns_correct_dim(embedder):
    vec = embedder.embed_one("hello world")
    assert len(vec) == 384  # MiniLM-L6 dim


def test_embedder_returns_floats(embedder):
    vec = embedder.embed_one("hello world")
    assert all(isinstance(x, float) for x in vec)


def test_embedder_batch_embeds_consistently(embedder):
    texts = ["alpha", "beta", "gamma"]
    vecs = embedder.embed_batch(texts)
    assert len(vecs) == 3
    assert all(len(v) == 384 for v in vecs)


def test_embedder_dimension_property(embedder):
    assert embedder.dimension == 384
