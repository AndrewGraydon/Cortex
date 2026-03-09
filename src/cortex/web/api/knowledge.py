"""Knowledge store API — document upload, listing, search, and deletion."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge"])


@router.get("/api/knowledge")
async def list_documents(request: Request) -> dict[str, Any]:
    """List all documents in the knowledge store."""
    services = request.app.state.services
    store = services.get("knowledge_store")

    if store is None:
        return {"documents": [], "configured": False}

    docs = await store.list_documents()
    return {
        "configured": True,
        "count": len(docs),
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "format": d.format,
                "chunk_count": d.chunk_count,
                "ingested_at": d.ingested_at,
            }
            for d in docs
        ],
    }


@router.post("/api/knowledge/upload")
async def upload_document(request: Request, file: UploadFile) -> dict[str, Any]:
    """Upload and ingest a document."""
    services = request.app.state.services
    ingester = services.get("knowledge_ingester")

    if ingester is None:
        return {"success": False, "error": "Knowledge store not configured."}

    if file.filename is None:
        return {"success": False, "error": "No filename provided."}

    # Save to temp file and ingest
    import tempfile

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        title = Path(file.filename).stem
        doc = await ingester.ingest_file(tmp_path, title=title)
        return {
            "success": True,
            "document": {
                "id": doc.id,
                "title": doc.title,
                "format": doc.format,
                "chunk_count": doc.chunk_count,
            },
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    finally:
        tmp_path.unlink(missing_ok=True)


@router.delete("/api/knowledge/{doc_id}")
async def delete_document(request: Request, doc_id: str) -> dict[str, Any]:
    """Delete a document from the knowledge store."""
    services = request.app.state.services
    store = services.get("knowledge_store")

    if store is None:
        return {"success": False, "error": "Knowledge store not configured."}

    deleted = await store.delete_document(doc_id)
    return {"success": deleted}


@router.get("/api/knowledge/search")
async def search_knowledge(request: Request, q: str = "") -> dict[str, Any]:
    """Search the knowledge store."""
    services = request.app.state.services
    retriever = services.get("knowledge_retriever")

    if retriever is None:
        return {"results": [], "configured": False}

    if not q.strip():
        return {"results": [], "query": q}

    results = await retriever.search(q)
    return {
        "query": q,
        "results": [
            {
                "content": r.chunk.content,
                "similarity": round(r.similarity, 4),
                "document_title": r.document_title,
                "chunk_index": r.chunk.chunk_index,
            }
            for r in results
        ],
    }
