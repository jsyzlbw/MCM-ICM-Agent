from fastapi.testclient import TestClient

from mcm_agent.server.app import create_app


def _client(tmp_path):
    return TestClient(
        create_app(workspace_base=tmp_path / "ws", knowledge_base_dir=tmp_path / "kb")
    )


def test_list_upload_preview_delete_knowledge_files(tmp_path) -> None:
    client = _client(tmp_path)

    # initially empty
    assert client.get("/api/knowledge/files").json()["files"] == []

    # upload a markdown note into a subdir
    up = client.post(
        "/api/knowledge/files",
        data={"subdir": "methods"},
        files={"files": ("note.md", b"# Method\n\nUse weighted TOPSIS for evaluation.", "text/markdown")},
    )
    assert up.status_code == 200
    assert "methods/note.md" in up.json()["saved"]

    # list shows it as ingestible
    listing = client.get("/api/knowledge/files").json()
    entry = next(f for f in listing["files"] if f["path"] == "methods/note.md")
    assert entry["ingestible"] is True
    assert listing["ingestible_count"] == 1

    # index preview ingests the markdown into a throwaway store
    preview = client.get("/api/knowledge/index-preview").json()
    assert preview["total_chunks"] >= 1

    # delete it
    deleted = client.delete("/api/knowledge/files", params={"path": "methods/note.md"})
    assert deleted.status_code == 200
    assert client.get("/api/knowledge/files").json()["files"] == []


def test_knowledge_marks_unsupported_extension_not_ingestible(tmp_path) -> None:
    client = _client(tmp_path)
    client.post(
        "/api/knowledge/files",
        files={"files": ("data.bin", b"\x00\x01", "application/octet-stream")},
    )
    entry = next(f for f in client.get("/api/knowledge/files").json()["files"] if f["path"] == "data.bin")
    assert entry["ingestible"] is False


def test_knowledge_path_traversal_rejected(tmp_path) -> None:
    client = _client(tmp_path)
    assert client.delete("/api/knowledge/files", params={"path": "../secret.txt"}).status_code == 400
