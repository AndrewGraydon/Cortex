"""Knowledge store types — documents, chunks, and search results."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray


@dataclass
class Document:
    """A document stored in the knowledge base."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    title: str = ""
    source_path: str = ""
    format: str = "txt"
    ingested_at: float = field(default_factory=time.time)
    chunk_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentChunk:
    """A chunk of a document with its embedding."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    document_id: str = ""
    chunk_index: int = 0
    content: str = ""
    embedding: NDArray[np.float32] | None = None
    token_count: int = 0


@dataclass
class KnowledgeSearchResult:
    """A search result from the knowledge store."""

    chunk: DocumentChunk
    similarity: float
    document_title: str = ""
