"""Experiment: do sentences with similar meaning get similar embeddings?

Run from the repo root with your keys loaded:
    set -a; source .env; set +a
    python scripts/explore_embeddings.py
"""
from __future__ import annotations

import numpy as np
from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"

SENTENCES = [
    # about debt / leverage
    "The company carries a lot of debt relative to its equity.",
    "Its balance sheet is highly leveraged.",
    "Borrowings have grown faster than shareholder capital.",
    # about margins / profitability
    "Gross margins expanded as production costs fell.",
    "The business keeps a large share of each sales dollar as profit.",
    "Profitability improved compared with last year.",
]


def main() -> None:
    client = OpenAI()  # reads OPENAI_API_KEY
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=SENTENCES)
    vectors = np.array([item.embedding for item in response.data])
    print(
        f"{len(SENTENCES)} sentences -> {vectors.shape[1]} numbers each "
        f"({response.usage.total_tokens} tokens)\n"
    )

    # Cosine similarity: scale every vector to length 1, then dot products give the cosine.
    unit = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    similarity = unit @ unit.T

    labels = [f"S{i + 1}" for i in range(len(SENTENCES))]
    print("      " + "".join(f"{label:>7}" for label in labels))
    for label, row in zip(labels, similarity):
        print(f"{label:<6}" + "".join(f"{value:>7.2f}" for value in row))

    print()
    for label, sentence in zip(labels, SENTENCES):
        print(f"{label}: {sentence}")


if __name__ == "__main__":
    main()