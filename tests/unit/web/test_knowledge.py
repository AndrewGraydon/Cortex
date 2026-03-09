"""Tests for knowledge web API routes."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.knowledge.retriever import KnowledgeRetriever
from cortex.knowledge.store import KnowledgeStore
from cortex.knowledge.types import Document, DocumentChunk, KnowledgeSearchResult
from cortex.web.app import create_app


@pytest.fixture
def mock_store() -> AsyncMock:
    store = AsyncMock(spec=KnowledgeStore)
    store.list_documents = AsyncMock(return_value=[])
    store.delete_document = AsyncMock(return_value=True)
    return store


@pytest.fixture
def mock_ingester() -> AsyncMock:
    ingester = AsyncMock()
    ingester.ingest_file = AsyncMock(
        return_value=Document(id="new-doc", title="Uploaded", format="txt", chunk_count=3)
    )
    return ingester


@pytest.fixture
def mock_retriever() -> AsyncMock:
    retriever = AsyncMock(spec=KnowledgeRetriever)
    retriever.search = AsyncMock(return_value=[])
    return retriever


@pytest.fixture
def client(
    mock_store: AsyncMock,
    mock_ingester: AsyncMock,
    mock_retriever: AsyncMock,
) -> Generator[TestClient]:
    config = CortexConfig()
    app = create_app(
        config=config,
        enable_auth=False,
        knowledge_store=mock_store,
        knowledge_ingester=mock_ingester,
        knowledge_retriever=mock_retriever,
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_knowledge() -> Generator[TestClient]:
    """Client with no knowledge services configured."""
    config = CortexConfig()
    app = create_app(config=config, enable_auth=False)
    with TestClient(app) as c:
        yield c


# --- GET /api/knowledge ---


class TestListDocuments:
    def test_no_store_configured(self, client_no_knowledge: TestClient) -> None:
        resp = client_no_knowledge.get("/api/knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents"] == []
        assert data["configured"] is False

    def test_empty_store(self, client: TestClient) -> None:
        resp = client.get("/api/knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents"] == []
        assert data["configured"] is True
        assert data["count"] == 0

    def test_returns_documents(self, client: TestClient, mock_store: AsyncMock) -> None:
        mock_store.list_documents.return_value = [
            Document(id="d1", title="Doc One", format="txt", chunk_count=5, ingested_at=1000.0),
            Document(id="d2", title="Doc Two", format="pdf", chunk_count=10, ingested_at=2000.0),
        ]
        resp = client.get("/api/knowledge")
        data = resp.json()
        assert data["count"] == 2
        assert data["documents"][0]["id"] == "d1"
        assert data["documents"][0]["title"] == "Doc One"
        assert data["documents"][1]["format"] == "pdf"


# --- POST /api/knowledge/upload ---


class TestUploadDocument:
    def test_no_ingester_configured(self, client_no_knowledge: TestClient) -> None:
        resp = client_no_knowledge.post(
            "/api/knowledge/upload",
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        data = resp.json()
        assert data["success"] is False
        assert "not configured" in data["error"].lower()

    def test_upload_success(self, client: TestClient) -> None:
        resp = client.post(
            "/api/knowledge/upload",
            files={"file": ("readme.txt", b"Hello world content here.", "text/plain")},
        )
        data = resp.json()
        assert data["success"] is True
        assert data["document"]["id"] == "new-doc"
        assert data["document"]["title"] == "Uploaded"

    def test_upload_ingestion_error(self, client: TestClient, mock_ingester: AsyncMock) -> None:
        mock_ingester.ingest_file.side_effect = ValueError("Bad format")
        resp = client.post(
            "/api/knowledge/upload",
            files={"file": ("bad.xyz", b"data", "application/octet-stream")},
        )
        data = resp.json()
        assert data["success"] is False
        assert "Bad format" in data["error"]


# --- DELETE /api/knowledge/{doc_id} ---


class TestDeleteDocument:
    def test_no_store_configured(self, client_no_knowledge: TestClient) -> None:
        resp = client_no_knowledge.delete("/api/knowledge/doc-1")
        data = resp.json()
        assert data["success"] is False

    def test_delete_success(self, client: TestClient) -> None:
        resp = client.delete("/api/knowledge/doc-1")
        data = resp.json()
        assert data["success"] is True

    def test_delete_nonexistent(self, client: TestClient, mock_store: AsyncMock) -> None:
        mock_store.delete_document.return_value = False
        resp = client.delete("/api/knowledge/nonexistent")
        data = resp.json()
        assert data["success"] is False


# --- GET /api/knowledge/search ---


class TestSearchKnowledge:
    def test_no_retriever_configured(self, client_no_knowledge: TestClient) -> None:
        resp = client_no_knowledge.get("/api/knowledge/search?q=test")
        data = resp.json()
        assert data["results"] == []
        assert data["configured"] is False

    def test_empty_query(self, client: TestClient) -> None:
        resp = client.get("/api/knowledge/search?q=")
        data = resp.json()
        assert data["results"] == []
        assert data["query"] == ""

    def test_search_returns_results(self, client: TestClient, mock_retriever: AsyncMock) -> None:
        chunk = DocumentChunk(
            id="c1",
            document_id="d1",
            chunk_index=0,
            content="Relevant content here.",
            token_count=5,
        )
        mock_retriever.search.return_value = [
            KnowledgeSearchResult(chunk=chunk, similarity=0.85, document_title="My Doc")
        ]
        resp = client.get("/api/knowledge/search?q=relevant")
        data = resp.json()
        assert data["query"] == "relevant"
        assert len(data["results"]) == 1
        assert data["results"][0]["content"] == "Relevant content here."
        assert data["results"][0]["similarity"] == 0.85
        assert data["results"][0]["document_title"] == "My Doc"

    def test_whitespace_query(self, client: TestClient) -> None:
        resp = client.get("/api/knowledge/search?q=%20%20")
        data = resp.json()
        assert data["results"] == []
