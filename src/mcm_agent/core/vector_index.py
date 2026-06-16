from __future__ import annotations

from pathlib import Path


class VectorIndex:
    def __init__(
        self,
        *,
        persist_dir: Path | None = None,
        collection_name: str = "methodology",
        client: object | None = None,
    ) -> None:
        import chromadb

        if client is not None:
            self._client = client
        elif persist_dir is not None:
            Path(persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(persist_dir))
        else:
            self._client = chromadb.EphemeralClient()
        self._collection = self._client.get_or_create_collection(collection_name)

    def add_chunks(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        self._collection.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def query(self, embedding: list[float], top_n: int) -> list[dict]:
        result = self._collection.query(query_embeddings=[embedding], n_results=top_n)
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        hits = []
        for index, chunk_id in enumerate(ids):
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "content": documents[index] if index < len(documents) else "",
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                }
            )
        return hits
