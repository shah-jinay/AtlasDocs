"""Unit tests for the pure scoring functions -- no live service needed.
Run with: pytest evaluation/test_metrics.py
"""
from metrics import (
    MetricsAccumulator,
    answer_score,
    citation_precision,
    citation_recall,
    mrr,
    precision_at_k,
    recall_at_k,
)


def test_recall_at_k_hit():
    assert recall_at_k({"a", "b"}, ["x", "a", "y"], k=5) == 1.0


def test_recall_at_k_miss_outside_k():
    assert recall_at_k({"a"}, ["x", "y", "a"], k=2) == 0.0


def test_recall_at_k_vacuous_when_nothing_relevant():
    assert recall_at_k(set(), ["x", "y"], k=5) == 1.0


def test_mrr_rewards_early_rank():
    assert mrr({"a"}, ["a", "b", "c"]) == 1.0
    assert mrr({"a"}, ["b", "a", "c"]) == 0.5
    assert mrr({"a"}, ["b", "c"]) == 0.0


def test_precision_at_k():
    assert precision_at_k({"a", "b"}, ["a", "x", "y"], k=3) == 1 / 3


def test_citation_precision_and_recall():
    assert citation_precision({"a", "b"}, {"a"}) == 0.5
    assert citation_recall({"a", "b"}, {"a", "b", "c"}) == 2 / 3
    assert citation_recall({"a"}, set()) == 1.0  # nothing expected -> vacuously satisfied
    assert citation_precision(set(), {"a"}) == 0.0


def test_answer_score_full_match():
    assert answer_score(answer="It takes 90 days.", must_include=["90 days"], must_not_claim=["forever"]) == 2


def test_answer_score_violation_is_zero_even_with_includes():
    assert (
        answer_score(answer="It takes 90 days, or forever if unpaid.", must_include=["90 days"], must_not_claim=["forever"])
        == 0
    )


def test_answer_score_partial_match():
    assert answer_score(answer="I don't know the exact number.", must_include=["90 days", "30 days"], must_not_claim=[]) == 0
    assert answer_score(answer="It's 90 days probably.", must_include=["90 days", "unrelated phrase"], must_not_claim=[]) == 1


def test_accumulator_summary_averages_across_cases():
    acc = MetricsAccumulator()
    acc.add_case(
        case_id="q1",
        relevant_ids={"c1"},
        retrieved_ids=["c1", "c2"],
        cited_ids={"c1"},
        answer="answer with fact",
        must_include=["fact"],
        must_not_claim=[],
        k=5,
    )
    acc.add_case(
        case_id="q2",
        relevant_ids={"c9"},
        retrieved_ids=["c2", "c3"],
        cited_ids=set(),
        answer="wrong",
        must_include=["fact"],
        must_not_claim=[],
        k=5,
    )
    summary = acc.summary()
    assert summary["n_cases"] == 2
    assert summary["recall_at_5"] == 0.5


def test_accumulator_tracks_abstention_accuracy():
    acc = MetricsAccumulator()
    acc.add_case(
        case_id="q1",
        relevant_ids=set(),
        retrieved_ids=[],
        cited_ids=set(),
        answer="I don't know",
        must_include=[],
        must_not_claim=[],
        expect_abstention=True,
        actual_abstained=True,
    )
    assert acc.summary()["abstention_accuracy"] == 1.0
