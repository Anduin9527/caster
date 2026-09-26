"""The single encoder shared by evaluation, indexing and the online query path.

Evaluation, the index build and the live search must encode text the same
way, or the vectors in the collection stop matching the query vectors. Keeping
one implementation here is what prevents that: the build used to skip the
dimension truncation the evaluator applied, which would have produced 2560-dim
vectors in a 1024-dim collection.

The :func:`fingerprint` covers everything that changes a vector: model commit,
output dimension, truncation length, pooling/normalisation code version and the
query instruction. It is recorded in the index manifest and in the embedding
cache key, so a configuration change can never reuse or overwrite vectors that
were produced differently.

The heavy imports live inside :class:`Encoder` so the build scripts in
``scripts/`` can import this module for its fingerprint without pulling in
torch, and so the API process only pays for them when a query is actually made.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

ENCODER_VERSION = "last-token-pool-l2norm-bf16-v1"
DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"


def last_token_pool(last_hidden_states: Any, attention_mask: Any) -> Any:
    """Module-level form of :meth:`Encoder.last_token_pool`, for the scripts."""
    return Encoder.last_token_pool(last_hidden_states, attention_mask)


def instruct(instruction: str, query: str) -> str:
    """Qwen3's query form: the instruction is prepended, documents get none."""
    return f"Instruct: {instruction}\nQuery:{query}"


def fingerprint(
    model_commit: str, dim: int, max_length: int, instruction: str = DEFAULT_INSTRUCTION
) -> str:
    material = json.dumps(
        {
            "model_commit": model_commit,
            "dim": dim,
            "max_length": max_length,
            "encoder": ENCODER_VERSION,
            "instruction": instruction,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:32]


class Encoder:
    """Loads one model and encodes documents or queries identically every time."""

    def __init__(
        self,
        model_path: Path,
        dim: int,
        max_length: int,
        device: str,
        batch_size: int = 64,
        instruction: str = DEFAULT_INSTRUCTION,
        commit: str = "",
    ):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.model_path = Path(model_path)
        self.dim = dim
        self.max_length = max_length
        self.device = device
        self.batch_size = batch_size
        self.instruction = instruction
        self.commit = commit
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))
        self.model = AutoModel.from_pretrained(str(self.model_path), torch_dtype=torch.bfloat16)
        self.model.eval().to(device)

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.commit, self.dim, self.max_length, self.instruction)

    @property
    def native_dim(self) -> int:
        return int(self.model.config.hidden_size)

    @staticmethod
    def last_token_pool(last_hidden_states: Any, attention_mask: Any) -> Any:
        """Qwen3 pooling: the last non-padding token of each sequence."""
        import torch

        left_padding = attention_mask[:, -1].sum() == attention_mask.shape[0]
        if left_padding:
            return last_hidden_states[:, -1]
        lengths = attention_mask.sum(dim=1) - 1
        return last_hidden_states[
            torch.arange(last_hidden_states.shape[0], device=last_hidden_states.device), lengths
        ]

    def _encode(self, texts: list[str]) -> Any:
        import numpy as np
        import torch
        import torch.nn.functional as F

        out = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            inputs = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            ).to(self.device)
            with torch.inference_mode():
                hidden = self.model(**inputs).last_hidden_state
                vectors = last_token_pool(hidden, inputs["attention_mask"])
                if self.dim:
                    # Matryoshka truncation, then re-normalise so cosine stays a
                    # cosine over the truncated vector.
                    vectors = vectors[:, : self.dim]
                vectors = F.normalize(vectors, p=2, dim=1)
            out.append(vectors.float().cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, self.dim or 1), dtype=np.float32)

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return self._encode(list(texts))

    def encode_query(self, query: str) -> np.ndarray:
        return self._encode([instruct(self.instruction, query)])[0]
