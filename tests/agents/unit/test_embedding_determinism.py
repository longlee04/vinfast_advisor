"""A9-2: adapter mang ten Deterministic phai tat dinh ca giua hai tien trinh."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from src.agents.adapters.embedding import DeterministicEmbeddingAdapter

PROBE = (
    "import asyncio, json, sys;"
    "sys.path.insert(0, '.');"
    "from src.agents.adapters.embedding import DeterministicEmbeddingAdapter;"
    "print(json.dumps(asyncio.run(DeterministicEmbeddingAdapter().embed(['cua so troi toan canh']))[0]))"
)


@pytest.mark.asyncio
async def test_same_text_gives_the_same_vector_in_one_process():
    adapter = DeterministicEmbeddingAdapter()

    first, second = await adapter.embed(["cua so troi"]), await adapter.embed(["cua so troi"])

    assert first == second


def test_same_text_gives_the_same_vector_across_processes():
    runs = [
        subprocess.run(
            [sys.executable, "-c", PROBE],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "2")
    ]

    assert runs[0] == runs[1]
