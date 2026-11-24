from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import uuid

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_NAME = "BAAI/bge-small-en-v1.5"
COLLECTION = "pharma_chunks_bge_small_v1"
DIMENSIONS = 384
BATCH_SIZE = 32


def api(session: requests.Session, method: str, base_url: str, path: str, *, payload=None, timeout=90):
    url = base_url.rstrip("/") + path
    response = session.request(method, url, json=payload, timeout=timeout)
    if not response.ok:
        raise RuntimeError(f"Qdrant API {method} {path}: HTTP {response.status_code}: {response.text[:1000]}")
    data = response.json()
    if data.get("status") == "error":
        raise RuntimeError(f"Qdrant API {method} {path}: {data}")
    return data


def load_chunks(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}. Run scripts/02_prepare_dataset.py first.")
    chunks = []
    seen = set()
    with path.open("r", encoding="utf-8") as src:
        for lineno, line in enumerate(src, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            for field in ("chunk_id", "drug_id", "text", "section_type"):
                if not row.get(field):
                    raise ValueError(f"Line {lineno}: required field {field!r} missing")
            if row["chunk_id"] in seen:
                raise ValueError(f"Duplicate chunk_id at line {lineno}: {row['chunk_id']}")
            seen.add(row["chunk_id"])
            chunks.append(row)
    if not chunks:
        raise ValueError("No chunks to index")
    return chunks


def batches(items: list[dict], size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def ensure_collection(session, base_url: str, collection: str) -> None:
    existing = session.get(base_url.rstrip("/") + f"/collections/{collection}", timeout=20)
    if existing.status_code == 404:
        api(session, "PUT", base_url, f"/collections/{collection}", payload={
            "vectors": {"size": DIMENSIONS, "distance": "Cosine"},
            "hnsw_config": {"m": 16, "ef_construct": 100},
            # 100 KiB threshold makes HNSW likely for this ~1000-vector pilot.
            "optimizers_config": {"indexing_threshold": 100},
        })
        print(f"Created collection {collection!r} (Cosine, {DIMENSIONS} dimensions)", flush=True)
    else:
        if not existing.ok:
            raise RuntimeError(f"Qdrant unavailable: HTTP {existing.status_code}: {existing.text[:500]}")
        cfg = existing.json().get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
        if cfg.get("size") != DIMENSIONS or str(cfg.get("distance", "")).lower() != "cosine":
            raise RuntimeError(
                f"Collection {collection!r} already exists with incompatible vector configuration: {cfg}. "
                "Use a NEW collection name via --collection; do not delete your data by accident."
            )
        # Avoid retaining default indexing threshold if collection existed before this script.
        api(session, "PATCH", base_url, f"/collections/{collection}",
            payload={"optimizers_config": {"indexing_threshold": 100}})
        print(f"Using existing collection {collection!r}", flush=True)


def upload_chunks(session, base_url: str, collection: str, chunks: list[dict], model) -> None:
    total = len(chunks)
    for start, rows in enumerate(batches(chunks, BATCH_SIZE)):
        texts = [row["text"] for row in rows]
        vectors = list(model.embed(texts, batch_size=BATCH_SIZE))
        if len(vectors) != len(rows):
            raise RuntimeError("Embedding model returned the wrong number of vectors")
        points = []
        for row, vector in zip(rows, vectors):
            embedding = vector.tolist()
            if len(embedding) != DIMENSIONS:
                raise RuntimeError("Incorrect embedding dimension")
            # Stable Qdrant point ID, while original chunk_id remains searchable metadata.
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, row["chunk_id"]))
            points.append({
                "id": point_id,
                "vector": embedding,
                "payload": {key: row.get(key) for key in (
                    "chunk_id", "drug_id", "label_id", "set_id", "section_id",
                    "section_type", "chunk_index", "text", "document_id"
                )},
            })
        api(session, "PUT", base_url, f"/collections/{collection}/points?wait=true",
            payload={"points": points}, timeout=120)
        print(f"Uploaded {min(start + len(rows), total)}/{total} chunks", flush=True)


def report(session, base_url: str, collection: str, expected: int) -> None:
    # Optimizer works asynchronously. A positive value supports the presence of HNSW indexing;
    # point count by itself does NOT establish HNSW was built.
    info = {}
    for retry in range(16):
        info = api(session, "GET", base_url, f"/collections/{collection}")["result"]
        indexed = info.get("indexed_vectors_count") or 0
        if indexed > 0:
            break
        if retry < 15:
            time.sleep(3)
    count = api(session, "POST", base_url, f"/collections/{collection}/points/count",
                payload={"exact": True})["result"]["count"]
    print(f"\nCollection: {collection}")
    print(f"Exact points count: {count} (input chunks: {expected})")
    print(f"Collection status: {info.get('status')}; optimizer: {info.get('optimizer_status')}")
    print(f"indexed_vectors_count: {info.get('indexed_vectors_count')}")
    if count != expected:
        print("WARNING: Count differs; old points from a previous dataset may exist in this collection.")
    if (info.get("indexed_vectors_count") or 0) == 0:
        print("WARNING: HNSW not confirmed. Do NOT claim HNSW benchmarking yet.")
    else:
        print("Nonzero indexed_vectors_count: HNSW indexing has been performed on at least some vectors.")


def example_search(session, base_url: str, collection: str, model) -> None:
    query = "contraindications and bleeding risks of warfarin"
    query_vector = list(model.embed([query]))[0].tolist()
    data = api(session, "POST", base_url, f"/collections/{collection}/points/query", payload={
        "query": query_vector,
        "limit": 3,
        "with_payload": True,
        "params": {"hnsw_ef": 64, "exact": False},
    })
    print(f"\nExample Vector-only query: {query}")
    for rank, point in enumerate(data.get("result", {}).get("points", []), start=1):
        p = point.get("payload") or {}
        print(f"{rank}. score={point.get('score', 0):.4f}; drug_id={p.get('drug_id')}; "
              f"section={p.get('section_type')}; chunk_id={p.get('chunk_id')}")
    print("These are retrieval results, not clinical recommendations or benchmark accuracy figures.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=pathlib.Path,
                        default=ROOT / "data" / "processed" / "chunks.jsonl")
    parser.add_argument("--url", default="http://127.0.0.1:6333")
    parser.add_argument("--collection", default=COLLECTION)
    args = parser.parse_args()
    chunks = load_chunks(args.chunks)
    session = requests.Session()
    try:
        health = api(session, "GET", args.url, "/collections", timeout=10)
    except requests.RequestException as exc:
        raise SystemExit(f"Cannot connect to Qdrant at {args.url}: {exc}. Is Docker Compose running?")
    print(f"Qdrant reachable. Source corpus: {len(chunks)} authentic chunks.", flush=True)
    ensure_collection(session, args.url, args.collection)
    try:
        from fastembed import TextEmbedding
    except ImportError:
        raise SystemExit("Missing fastembed. Run: py -m pip install fastembed")
    print(f"Loading embedding model {MODEL_NAME} (first run may download model files)...", flush=True)
    model = TextEmbedding(model_name=MODEL_NAME)
    upload_chunks(session, args.url, args.collection, chunks, model)
    report(session, args.url, args.collection, len(chunks))
    example_search(session, args.url, args.collection, model)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
