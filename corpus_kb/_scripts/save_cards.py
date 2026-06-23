"""Save workflow-produced teardown cards to JSON + (re)index them into mcm_corpus."""
import json
import sys
from pathlib import Path

from mcm_agent.config import load_settings
from mcm_agent.corpus.teardown import TeardownCard, render_card_text
from mcm_agent.core.embedding_cache import EmbeddingCache
from mcm_agent.core.vector_index import VectorIndex
from mcm_agent.providers.factory import build_provider_bundle
from mcm_agent.utils.json_io import write_json

ROOT = "/Users/mac/Programming/MCM-ICM-Agent"
KB = Path(f"{ROOT}/corpus_kb")

# input: a JSON file holding either {"cards":[...]} or [...]
raw = json.loads(Path(sys.argv[1]).read_text())
cards_data = raw["cards"] if isinstance(raw, dict) and "cards" in raw else raw
cards = [TeardownCard(**c) for c in cards_data]
print(f"loaded {len(cards)} cards", flush=True)

td_dir = KB / "teardowns"
td_dir.mkdir(parents=True, exist_ok=True)
for c in cards:
    write_json(td_dir / f"{c.paper_id}.json", c.model_dump())

s = load_settings(None, f"{ROOT}/mcm_agent_config.local.json")
bundle = build_provider_bundle(s, workspace_root=Path(ROOT))
index = VectorIndex(persist_dir=KB / "chroma", collection_name="mcm_corpus")
cache = EmbeddingCache(KB / "embedding_cache.db")
ids, docs, metas, texts = [], [], [], []
for c in cards:
    text = render_card_text(c)
    ids.append(f"{c.paper_id}#teardown")
    docs.append(text)
    texts.append(text)
    metas.append({
        "paper_id": c.paper_id, "year": c.year, "problem": c.problem,
        "problem_type": c.problem_type, "section_type": "teardown",
        "award": "Outstanding", "source": "teardown_card_subagent", "chunk_index": 0,
    })
embeddings = cache.embed_with_cache(bundle.embedding, s.embedding_model, texts)
index.add_chunks(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
print(f"saved+indexed {len(cards)} teardown cards", flush=True)
