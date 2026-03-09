"""Tests for tool pipeline web API."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.web.app import create_app


@pytest.fixture
def deployer_mock(tmp_path: Path) -> MagicMock:
    deployer = MagicMock()
    deployer.user_tools_dir = tmp_path / "user-tools"
    deployer.list_deployed.return_value = []
    deployer.deploy.return_value = tmp_path / "user-tools" / "my-tool"
    return deployer


@pytest.fixture
def client(deployer_mock: MagicMock) -> Generator[TestClient]:
    config = CortexConfig()
    app = create_app(
        config=config,
        enable_auth=False,
        tool_deployer=deployer_mock,
    )
    with TestClient(app) as c:
        yield c


class TestCreateTool:
    def test_create_success(self, client: TestClient) -> None:
        resp = client.post(
            "/api/pipeline/create",
            json={"name": "my-tool", "description": "A test tool"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["name"] == "my-tool"
        assert "manifest_yaml" in data
        assert "script_code" in data

    def test_create_missing_name(self, client: TestClient) -> None:
        resp = client.post(
            "/api/pipeline/create",
            json={"description": "No name"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_create_missing_description(self, client: TestClient) -> None:
        resp = client.post(
            "/api/pipeline/create",
            json={"name": "my-tool"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_create_invalid_name(self, client: TestClient) -> None:
        resp = client.post(
            "/api/pipeline/create",
            json={"name": "A", "description": "Bad name"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_create_with_parameters(self, client: TestClient) -> None:
        resp = client.post(
            "/api/pipeline/create",
            json={
                "name": "search-tool",
                "description": "Search",
                "parameters": {"query": {"type": "string"}},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"


class TestListDrafts:
    def test_empty_drafts(self, client: TestClient) -> None:
        resp = client.get("/api/pipeline/drafts")
        assert resp.status_code == 200
        assert resp.json()["drafts"] == []

    def test_lists_created_drafts(self, client: TestClient) -> None:
        client.post(
            "/api/pipeline/create",
            json={"name": "my-tool", "description": "Test"},
        )
        resp = client.get("/api/pipeline/drafts")
        assert resp.status_code == 200
        assert len(resp.json()["drafts"]) == 1


class TestReviewTool:
    def test_review_success(self, client: TestClient) -> None:
        client.post(
            "/api/pipeline/create",
            json={"name": "my-tool", "description": "Test"},
        )
        resp = client.post("/api/pipeline/my-tool/review")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reviewed"
        assert data["passed"] is True

    def test_review_nonexistent(self, client: TestClient) -> None:
        resp = client.post("/api/pipeline/nonexistent/review")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"


class TestApproveTool:
    def test_approve_reviewed(self, client: TestClient) -> None:
        client.post(
            "/api/pipeline/create",
            json={"name": "my-tool", "description": "Test"},
        )
        client.post("/api/pipeline/my-tool/review")
        resp = client.post("/api/pipeline/my-tool/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_approve_unreviewed(self, client: TestClient) -> None:
        client.post(
            "/api/pipeline/create",
            json={"name": "my-tool", "description": "Test"},
        )
        resp = client.post("/api/pipeline/my-tool/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"


class TestDeployTool:
    def test_deploy_approved(self, client: TestClient) -> None:
        client.post(
            "/api/pipeline/create",
            json={"name": "my-tool", "description": "Test"},
        )
        client.post("/api/pipeline/my-tool/review")
        client.post("/api/pipeline/my-tool/approve")
        resp = client.post("/api/pipeline/my-tool/deploy")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deployed"

    def test_deploy_nonexistent(self, client: TestClient) -> None:
        resp = client.post("/api/pipeline/nonexistent/deploy")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"


class TestPromoteTool:
    def test_promote_no_tracker(self, client: TestClient) -> None:
        resp = client.post("/api/pipeline/my-tool/promote")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"


class TestDisableTool:
    def test_disable_no_registry(self, client: TestClient) -> None:
        resp = client.post("/api/pipeline/my-tool/disable")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("error", "disabled")


class TestCatalog:
    def test_catalog_no_service(self, client: TestClient) -> None:
        resp = client.get("/api/pipeline/catalog")
        assert resp.status_code == 200
        assert resp.json()["tools"] == []
