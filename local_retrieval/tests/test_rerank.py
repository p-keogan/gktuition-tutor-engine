"""Offline, model-free unit tests for the local reranker wrapper (AGENT_30).

These never load the cross-encoder or the index — they pin the score
calibration and the empty-input contract, so they run in milliseconds with no
network and no torch graph init.
"""
from __future__ import annotations

import math

from local_retrieval import rerank


def test_sigmoid_matches_logistic_and_clamps():
    # Mirrors retriever._sigmoid_normalize: order-preserving logistic on [0,1].
    assert rerank._sigmoid(0.0) == 0.5
    assert abs(rerank._sigmoid(2.0) - 1.0 / (1.0 + math.exp(-2.0))) < 1e-9
    assert rerank._sigmoid(2.0) > rerank._sigmoid(-2.0)  # monotone
    assert rerank._sigmoid(1000.0) == 1.0   # overflow clamp
    assert rerank._sigmoid(-1000.0) == 0.0
    assert rerank._sigmoid(float("nan")) == 0.0  # NaN guard


def test_empty_query_returns_empty_without_touching_model():
    # No index / model needed: empty or whitespace query short-circuits.
    assert rerank.retrieve_reranked("", top_k=5) == []
    assert rerank.retrieve_reranked("   ", top_k=5) == []
    assert rerank.retrieve_reranked("anything", top_k=0) == []
    assert rerank.rerank_detailed("", top_k=5) == []


def test_score_is_calibrated_to_unit_interval():
    # Spot-check the calibration bounds the contract promises.
    for logit in (-12.0, -3.0, 0.0, 3.0, 9.0):
        s = rerank._sigmoid(logit)
        assert 0.0 <= s <= 1.0
