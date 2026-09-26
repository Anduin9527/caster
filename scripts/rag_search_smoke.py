"""Search the built index with the dev queries and print what comes back.

A smoke test that the collection, alias, vectors and payloads work together:
encode a query with the same instruction used during evaluation and print the
top hits with their payloads, so a broken index is visible without reading code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn.functional as F
from qdrant_client import QdrantClient
from transformers import AutoModel, AutoTokenizer

TASK = "Given a web search query, retrieve relevant passages that answer the query"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--alias", default="wiki")
    parser.add_argument("--dim", type=int, default=1024)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--model-key", default="qwen3-embedding-0.6b")
    args = parser.parse_args()

    manifest = json.loads((args.workspace / "models" / "manifest.json").read_text())
    snapshot = Path(manifest["models"][args.model_key]["local_path"])
    tokenizer = AutoTokenizer.from_pretrained(str(snapshot))
    model = AutoModel.from_pretrained(str(snapshot), torch_dtype=torch.bfloat16).eval()
    client = QdrantClient(url=args.qdrant_url, prefer_grpc=False, timeout=60)

    queries = args.query or ["女仆装", "比基尼", "双手举高微笑", "我们公司的考勤制度"]
    for query in queries:
        inputs = tokenizer([f"Instruct: {TASK}\nQuery:{query}"], padding=True, return_tensors="pt")
        with torch.inference_mode():
            hidden = model(**inputs).last_hidden_state
            lengths = inputs["attention_mask"].sum(dim=1) - 1
            vector = hidden[0, lengths[0]][: args.dim]
            vector = F.normalize(vector, p=2, dim=0)
        hits = client.query_points(
            collection_name=args.alias, query=vector.tolist(), limit=args.limit, with_payload=True
        ).points
        print("== %s" % query)
        for hit in hits:
            payload = hit.payload or {}
            print(
                "   %.4f %s %s %s"
                % (hit.score, payload.get("kind"), payload.get("title"), payload.get("doc_id"))
            )


if __name__ == "__main__":
    main()
