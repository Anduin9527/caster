"""Evaluate the deployed RetrievalService path against labelled wiki queries.

Unlike the strategy probes, this imports the application adapter, reads the
same config and tag dictionary as the API process, and records the final source
ranking after any exact-tag Qwen fusion. It is read-only: no collections,
aliases, manifests, or business records are changed.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path


def score(rows: list[tuple[list[int], list[int]]]) -> dict:
    result = {}
    for k in (1, 5, 10):
        result[f"hit@{k}"] = round(
            sum(any(source_id in wanted for source_id in ranking[:k]) for ranking, wanted in rows)
            / max(1, len(rows)),
            4,
        )
        result[f"coverage@{k}"] = round(
            sum(
                wanted and all(source_id in ranking[:k] for source_id in wanted)
                for ranking, wanted in rows
            )
            / max(1, len(rows)),
            4,
        )
    reciprocal = []
    for ranking, wanted in rows:
        rank = next(
            (
                position + 1
                for position, source_id in enumerate(ranking[:10])
                if source_id in wanted
            ),
            None,
        )
        reciprocal.append(1.0 / rank if rank else 0.0)
    result["mrr@10"] = round(sum(reciprocal) / max(1, len(rows)), 4)
    return result


def normalize_canonical(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").casefold().strip()
    return re.sub(r"\s+", "_", value)


def load_tag_ids(path: Path | None) -> dict[str, list[int]]:
    result: dict[str, list[int]] = defaultdict(list)
    if path is None:
        return result
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            result[normalize_canonical(str(row.get("title") or ""))].append(int(row["source_id"]))
    return result


def ids_for(
    query: dict, field: str, source_field: str, tag_ids: dict[str, list[int]]
) -> tuple[list[int], list[str]]:
    values = [int(value) for value in query.get(source_field) or []]
    missing = []
    for tag in query.get(field) or []:
        matches = tag_ids.get(normalize_canonical(str(tag)), [])
        if len(matches) == 1:
            values.append(matches[0])
        else:
            missing.append(str(tag))
    return list(dict.fromkeys(values)), missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--queries", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--wiki-names", type=Path, help="required when v2 labels use expected_tags/required_tags"
    )
    args = parser.parse_args()
    sys.path.insert(0, str(args.package_root))

    from aigc.agent.retrieval import RetrievalService
    from aigc.config import load
    from aigc.rag import build_backend
    from aigc.store import Store

    config = load()
    backend = build_backend(config)
    if backend is None:
        raise SystemExit("semantic backend is not configured")
    service = RetrievalService(Store(config["AIGC_DATA_DIR"]), backend)
    queries = []
    for path in args.queries:
        queries.extend(json.loads(path.read_text())["queries"])
    tag_ids = load_tag_ids(args.wiki_names)

    rows = []
    by_category = defaultdict(list)
    timings = []
    details = []
    no_match = []
    ambiguity = []
    forbidden_conflicts = []
    unresolved_tags = []
    for query in queries:
        wanted, missing_expected = ids_for(query, "expected_tags", "expected_source_ids", tag_ids)
        required, missing_required = ids_for(query, "required_tags", "", tag_ids)
        wanted = list(dict.fromkeys([*wanted, *required]))
        forbidden, missing_forbidden = ids_for(
            query, "forbidden_tags", "excluded_source_ids", tag_ids
        )
        if missing_expected or missing_required or missing_forbidden:
            unresolved_tags.append(
                {"id": query["id"], "tags": missing_expected + missing_required + missing_forbidden}
            )
        started = time.perf_counter()
        result = service.search_wiki(query["query"], args.limit)
        elapsed = (time.perf_counter() - started) * 1000.0
        timings.append(elapsed)
        ranking = [int(hit.source_id) for hit in result.hits if hit.source_id]
        top1_score = round(float(result.hits[0].score), 6) if result.hits else None
        score_stage = "rrf" if "精确标签映射" in result.semantic_reason else "dense"
        conflict = [source_id for source_id in forbidden if source_id in ranking[:5]]
        if forbidden:
            forbidden_conflicts.append({"id": query["id"], "forbidden_in_top5": conflict})
        details.append(
            {
                "id": query["id"],
                "query": query["query"],
                "category": query["category"],
                "wanted": wanted,
                "ranking": ranking,
                "reason": result.semantic_reason,
                "top1_score": top1_score,
                "score_stage": score_stage,
                "forbidden_in_top5": conflict,
                "latency_ms": round(elapsed, 1),
            }
        )
        if wanted:
            row = (ranking, wanted)
            rows.append(row)
            by_category[query["category"]].append(row)
        elif query.get("expect_no_match") is True:
            no_match.append(details[-1])
        elif query.get("expect_ambiguity") is True:
            ambiguity.append(details[-1])

    dense_positive_scores = [
        row["top1_score"]
        for row in details
        if row["wanted"] and row["score_stage"] == "dense" and row["top1_score"] is not None
    ]
    dense_no_match_scores = [
        row["top1_score"]
        for row in no_match
        if row["score_stage"] == "dense" and row["top1_score"] is not None
    ]
    report = {
        "queries": len(queries),
        "scored": len(rows),
        "limit": args.limit,
        "overall": score(rows),
        "by_category": {name: score(bucket) for name, bucket in sorted(by_category.items())},
        "latency_ms": {
            "p50": round(statistics.median(timings), 1),
            "p95": round(sorted(timings)[max(0, int(len(timings) * 0.95) - 1)], 1),
            "max": round(max(timings), 1),
        },
        "exact_tag_queries": sum("精确标签映射" in row["reason"] for row in details),
        "no_match_queries": len(no_match),
        "ambiguity_queries": len(ambiguity),
        "no_match_separation": {
            "score_stage": "dense_only",
            "max_no_match_top1": (max(dense_no_match_scores) if dense_no_match_scores else None),
            "min_positive_top1": (min(dense_positive_scores) if dense_positive_scores else None),
            "any_no_match_outscored_a_positive": bool(
                dense_no_match_scores
                and dense_positive_scores
                and max(dense_no_match_scores) > min(dense_positive_scores)
            ),
        },
        "unresolved_tags": unresolved_tags,
        "forbidden": {
            "queries": len(forbidden_conflicts),
            "violations": sum(bool(row["forbidden_in_top5"]) for row in forbidden_conflicts),
            "details": forbidden_conflicts,
        },
        "details": details,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {key: report[key] for key in ("overall", "latency_ms", "exact_tag_queries")},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
