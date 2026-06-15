"""
RAG Engine for RTI Act Legal Corpus.

Handles section-aware retrieval of statutory clauses (Sections 8, 9, 11) using
locnal nomic-embed-text embeddings and cosine similarity. Degrades gracefully
to keyword-matching search if Ollama is unavailable.
"""

import json
import logging
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent
_DATA_DIR = _BASE_DIR.parent / "data"
_SECTIONS_FILE = _DATA_DIR / "rti_act_sections.json"
_EMBEDDINGS_CACHE_FILE = _DATA_DIR / "rti_sections_embeddings.json"

# ---------------------------------------------------------------------------
# Ollama Probe
# ---------------------------------------------------------------------------
_OLLAMA_AVAILABLE: bool = False
try:
    import ollama as _ollama_client
    _OLLAMA_AVAILABLE = True
except ImportError:
    logger.warning("ollama package not installed. RAG engine will run in keyword mode.")


def _check_ollama_server() -> bool:
    if not _OLLAMA_AVAILABLE:
        return False
    try:
        _ollama_client.list()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Similarity Helper
# ---------------------------------------------------------------------------
def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Embedding Logic
# ---------------------------------------------------------------------------
def _get_embedding(text: str) -> Optional[List[float]]:
    if not _OLLAMA_AVAILABLE:
        return None
    try:
        response = _ollama_client.embed(model="nomic-embed-text", input=text)
        embeddings = response.get("embeddings")
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
        return None
    except Exception as exc:
        logger.warning(f"Ollama embedding failed in RAG engine: {exc}")
        return None


def _load_sections() -> List[Dict[str, Any]]:
    if not _SECTIONS_FILE.exists():
        logger.error(f"Statutory text file not found at {_SECTIONS_FILE}")
        return []
    with open(_SECTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_or_compute_embeddings() -> Optional[Dict[str, List[float]]]:
    """Load cached statutory embeddings or compute them via nomic-embed-text."""
    if _EMBEDDINGS_CACHE_FILE.exists():
        try:
            with open(_EMBEDDINGS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load RAG embeddings cache: {e}")

    if not _check_ollama_server():
        logger.warning("Ollama not running - skipping embedding computation.")
        return None

    sections = _load_sections()
    if not sections:
        return None

    logger.info("Computing legal corpus embeddings for the first time...")
    cache: Dict[str, List[float]] = {}
    for sec in sections:
        sec_id = sec["section"]
        # Rich representation: Section title + Section text
        text_to_embed = f"{sec_id}: {sec['title']}. {sec['text']}"
        emb = _get_embedding(text_to_embed)
        if emb:
            cache[sec_id] = emb
        else:
            logger.warning(f"Failed to embed section {sec_id}. Aborting cache creation.")
            return None

    try:
        with open(_EMBEDDINGS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        logger.info(f"Legal corpus embeddings cached to {_EMBEDDINGS_CACHE_FILE}")
    except Exception as e:
        logger.warning(f"Failed to write RAG embeddings cache: {e}")

    return cache


# ---------------------------------------------------------------------------
# Fallback Keyword Search
# ---------------------------------------------------------------------------
def _keyword_search(query: str, sections: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """Heuristic keyword search based on overlap of words."""
    query_words = set(query.lower().split())
    results = []
    
    for sec in sections:
        # Check text and section number matches (Section numbers get higher priority)
        text_lower = sec["text"].lower()
        title_lower = sec["title"].lower()
        sec_num = sec["section"].lower()

        score = 0.0
        # Check direct section number matches (e.g. '8(1)(j)' or '8(1)(d)')
        clean_num = sec_num.replace("section ", "")
        if clean_num in query.lower() or sec_num in query.lower():
            score += 10.0  # Strong boost for exact section citation
            
        # Add score for keyword hits
        for word in query_words:
            if len(word) > 2:
                if word in text_lower:
                    score += 1.0
                if word in title_lower:
                    score += 1.5

        if score > 0:
            # Map score to a pseudo cosine similarity score [0.5, 0.99]
            mapped_similarity = min(0.99, 0.5 + (score / 20.0))
            results.append((sec, mapped_similarity))

    # Sort and return top_k
    results.sort(key=lambda x: x[1], reverse=True)
    
    # If no matches, return first top_k
    if not results:
        return [{"section": s["section"], "title": s["title"], "text": s["text"], "similarity": 0.5} for s in sections[:top_k]]

    return [{"section": r["section"], "title": r["title"], "text": r["text"], "similarity": round(sim, 4)} for r, sim in results[:top_k]]


# ---------------------------------------------------------------------------
# Main Retrieval Function
# ---------------------------------------------------------------------------
def retrieve_relevant_sections(query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Retrieve top-k relevant RTI Act sections for the given query.
    
    Tries semantic dense retrieval, falls back to keyword matching.
    """
    sections = _load_sections()
    if not sections:
        return []

    # Try semantic search
    cache = _load_or_compute_embeddings()
    if cache is not None:
        query_emb = _get_embedding(query_text)
        if query_emb is not None:
            results = []
            for sec in sections:
                sec_id = sec["section"]
                sec_emb = cache.get(sec_id)
                if sec_emb:
                    sim = _cosine_similarity(query_emb, sec_emb)
                    # Boost score if query explicitly cites the section
                    clean_sec_id = sec_id.lower().replace("section ", "")
                    if clean_sec_id in query_text.lower():
                        sim = min(0.99, sim + 0.15)
                    results.append((sec, sim))
            
            results.sort(key=lambda x: x[1], reverse=True)
            return [
                {
                    "section": r["section"],
                    "title": r["title"],
                    "text": r["text"],
                    "similarity": round(sim, 4)
                }
                for r, sim in results[:top_k]
            ]


    # Fallback keyword matching
    logger.info("Falling back to keyword-based legal chunk retrieval.")
    return _keyword_search(query_text, sections, top_k)


# ---------------------------------------------------------------------------
# Module Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing RAG Engine retrieval...")
    res = retrieve_relevant_sections("personal privacy and medical records of employee")
    for r in res:
        print(f"\n- {r['section']}: {r['title']} (sim: {r['similarity']})")
        print(f"  {r['text'][:120]}...")
