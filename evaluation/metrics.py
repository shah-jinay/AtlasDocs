"""Retrieval and answer/citation scoring (blueprint sections 15.2, 15.3).

Pure functions over plain ids/strings so they're testable without any live
service, plus a small `MetricsAccumulator` that matches the pseudocode
shape from section 15.4 (`metrics.add_recall_at_k(...)`, `.write_json(...)`).
"""
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def recall_at_k(relevant_ids: set[str], retrieved_ids_in_rank_order: list[str], k: int) -> float:
    """1.0 if at least one labeled-relevant id appears in the top k, else 0.0
    -- this is per-question recall; average it across a dataset for the
    dataset-level Recall@K.
    """
    if not relevant_ids:
        return 1.0  # nothing to find; vacuously satisfied
    return 1.0 if set(retrieved_ids_in_rank_order[:k]) & relevant_ids else 0.0


def mrr(relevant_ids: set[str], retrieved_ids_in_rank_order: list[str]) -> float:
    for rank, chunk_id in enumerate(retrieved_ids_in_rank_order, start=1):
        if chunk_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def precision_at_k(relevant_ids: set[str], retrieved_ids_in_rank_order: list[str], k: int) -> float:
    top_k = retrieved_ids_in_rank_order[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for c in top_k if c in relevant_ids)
    return hits / len(top_k)


def citation_precision(cited_ids: set[str], relevant_ids: set[str]) -> float:
    if not cited_ids:
        return 0.0
    return len(cited_ids & relevant_ids) / len(cited_ids)


def citation_recall(cited_ids: set[str], relevant_ids: set[str]) -> float:
    if not relevant_ids:
        return 1.0
    return len(cited_ids & relevant_ids) / len(relevant_ids)


def answer_score(*, answer: str, must_include: list[str], must_not_claim: list[str]) -> int:
    """0/1/2 rubric (section 15.3), automated as a substring heuristic.

    This is a coarse proxy meant to catch regressions cheaply on every run
    -- the blueprint is explicit that it should be spot-checked manually,
    not trusted as ground truth on its own.
    """
    lowered = answer.lower()
    violates = any(phrase.lower() in lowered for phrase in must_not_claim)
    if violates:
        return 0
    if not must_include:
        return 2 if answer.strip() else 0
    included = sum(1 for phrase in must_include if phrase.lower() in lowered)
    if included == len(must_include):
        return 2
    if included > 0:
        return 1
    return 0


@dataclass
class MetricsAccumulator:
    recall_at_5: list[float] = field(default_factory=list)
    mrr_scores: list[float] = field(default_factory=list)
    precision_at_5: list[float] = field(default_factory=list)
    citation_precisions: list[float] = field(default_factory=list)
    citation_recalls: list[float] = field(default_factory=list)
    answer_scores: list[int] = field(default_factory=list)
    abstention_accuracies: list[float] = field(default_factory=list)
    per_case: list[dict[str, Any]] = field(default_factory=list)

    def add_case(
        self,
        *,
        case_id: str,
        relevant_ids: set[str],
        retrieved_ids: list[str],
        cited_ids: set[str],
        answer: str,
        must_include: list[str],
        must_not_claim: list[str],
        k: int = 5,
        expect_abstention: bool | None = None,
        actual_abstained: bool = False,
        relevant_cited_ids: set[str] | None = None,
    ) -> None:
        """`relevant_ids`/`retrieved_ids` drive Recall@K, MRR, Precision@K
        and must share one id space (chunk ids). `cited_ids`/
        `relevant_cited_ids` drive citation precision/recall and may use a
        *different* id space (e.g. document ids) when the client-facing
        citation payload doesn't expose chunk ids -- see
        evaluation/run_eval.py. Defaults to `relevant_ids` when omitted, for
        callers where both use the same granularity.
        """
        relevant_cited_ids = relevant_ids if relevant_cited_ids is None else relevant_cited_ids
        r_at_k = recall_at_k(relevant_ids, retrieved_ids, k)
        m = mrr(relevant_ids, retrieved_ids)
        p_at_k = precision_at_k(relevant_ids, retrieved_ids, k)
        c_prec = citation_precision(cited_ids, relevant_cited_ids)
        c_rec = citation_recall(cited_ids, relevant_cited_ids)
        a_score = answer_score(answer=answer, must_include=must_include, must_not_claim=must_not_claim)
        abstention_correct = None
        if expect_abstention is not None:
            abstention_correct = 1.0 if actual_abstained == expect_abstention else 0.0
            self.abstention_accuracies.append(abstention_correct)

        self.recall_at_5.append(r_at_k)
        self.mrr_scores.append(m)
        self.precision_at_5.append(p_at_k)
        self.citation_precisions.append(c_prec)
        self.citation_recalls.append(c_rec)
        self.answer_scores.append(a_score)
        self.per_case.append(
            {
                "case_id": case_id,
                "recall_at_5": r_at_k,
                "mrr": m,
                "precision_at_5": p_at_k,
                "citation_precision": c_prec,
                "citation_recall": c_rec,
                "answer_score": a_score,
                "abstention_correct": abstention_correct,
                "answer": answer,
            }
        )

    def summary(self) -> dict[str, Any]:
        def avg(values: list[float]) -> float | None:
            return round(statistics.fmean(values), 4) if values else None

        return {
            "n_cases": len(self.per_case),
            "recall_at_5": avg(self.recall_at_5),
            "mrr": avg(self.mrr_scores),
            "precision_at_5": avg(self.precision_at_5),
            "citation_precision": avg(self.citation_precisions),
            "citation_recall": avg(self.citation_recalls),
            "answer_score_avg": avg([float(s) for s in self.answer_scores]),
            "abstention_accuracy": avg(self.abstention_accuracies),
        }

    def write_json(self, path: str, *, extra_meta: dict[str, Any] | None = None) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"summary": self.summary(), "cases": self.per_case, "meta": extra_meta or {}}
        out.write_text(json.dumps(payload, indent=2))
