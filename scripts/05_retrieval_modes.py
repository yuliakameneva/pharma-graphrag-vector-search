from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import uuid

import requests
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION = "pharma_chunks_bge_small_v1"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

GRAPH_QUERY = """
MATCH (d:Drug)
WHERE toLower(trim(d.generic_name)) = toLower(trim($drug))
  AND (
    $required_contraindication = ''
    OR EXISTS {
      MATCH (d)-[r:HAS_CONTRAINDICATION]->(con:Contraindication)
      WHERE toLower(trim(con.name)) = toLower(trim($required_contraindication))
        AND r.verification_status STARTS WITH 'reviewed:'
    }
  )
MATCH (d)-[:HAS_LABEL]->(:DrugLabel)
         -[:HAS_SECTION]->(section:TextSection)
         -[:HAS_CHUNK]->(chunk:TextChunk)
WHERE section.section_type = $section
RETURN d.id AS drug_id,
       d.generic_name AS drug,
       chunk.id AS chunk_id,
       chunk.text AS text,
       chunk.chunk_index AS chunk_index,
       section.section_type AS section_type
ORDER BY chunk.chunk_index, chunk.id
"""


def read_local_password() -> str:
    """Read local .env only as fallback; never print its contents."""
    env_value = os.environ.get("NEO4J_PASSWORD", "").strip()
    if env_value:
        return env_value
    config = ROOT / ".env"
    if config.exists():
        for line in config.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("NEO4J_PASSWORD="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value and value != "change_this_local_password":
                    return value
    raise ValueError("NEO4J_PASSWORD missing. Configure it in the project's .env file.")


def graph_candidates(driver, *, drug: str, section: str, required: str) -> list[dict]:
    with driver.session(database="neo4j") as session:
        rows = session.run(
            GRAPH_QUERY,
            drug=drug,
            section=section,
            required_contraindication=required,
        )
        return [dict(r) for r in rows]


def qdrant_query(http: requests.Session, *, url: str, collection: str,
                 embedding: list[float], k: int, allowed_chunk_ids=None) -> list[dict]:
    data = {
        "query": embedding,
        "limit": k,
        "with_payload": True,
        "params": {"hnsw_ef": 64, "exact": False},
    }
    if allowed_chunk_ids is not None:
        if not allowed_chunk_ids:
            return []  # fail closed if no graph-approved candidates
        # Uses exactly the same UUID5 mapping as 04_index_qdrant.py.
        point_ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, x)) for x in allowed_chunk_ids]
        data["filter"] = {"must": [{"has_id": point_ids}]}
    response = http.post(
        f"{url.rstrip('/')}/collections/{collection}/points/query",
        json=data,
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(f"Qdrant returned HTTP {response.status_code}: {response.text[:900]}")
    result = response.json()
    return [
        {"chunk_id": (point.get("payload") or {}).get("chunk_id", ""),
         "drug_id": (point.get("payload") or {}).get("drug_id", ""),
         "section_type": (point.get("payload") or {}).get("section_type", ""),
         "text": (point.get("payload") or {}).get("text", ""),
         "score": point.get("score")}
        for point in result.get("result", {}).get("points", [])
    ]


def print_results(mode: str, results: list[dict], k: int) -> None:
    print(f"\n{'=' * 18} {mode} {'=' * 18}")
    if not results:
        print("No results matching this mode's constraints.")
        return
    for index, row in enumerate(results[:k], start=1):
        prefix = f"  score={row['score']:.4f}" if row.get("score") is not None else ""
        excerpt = " ".join(str(row.get("text", "")).split())[:180]
        print(f"{index}. {row.get('chunk_id')} [{row.get('section_type')}]" + prefix)
        print(f"   {excerpt}...")
    print(f"Returned: {min(len(results), k)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="First controlled demonstration of 3 retrieval modes")
    parser.add_argument("--query", default=(
        "What are the contraindications of warfarin sodium, including malignant "
        "hypertension and bleeding risks?"))
    parser.add_argument("--drug", default="WARFARIN SODIUM",
                        help="Exact generic drug name in Neo4j (explicitly supplied)")
    parser.add_argument("--section", default="contraindications")
    parser.add_argument("--required-contraindication", default="Malignant hypertension",
                        help="An exact verified contraindication label; use '' for none")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--neo4j-uri", default="bolt://127.0.0.1:7687")
    args = parser.parse_args()
    if not 1 <= args.k <= 50:
        parser.error("--k must be between 1 and 50")

    # Qdrant contains real saved vectors; this stage only embeds one search query.
    with requests.Session() as http:
        try:
            r = http.get(f"{args.qdrant_url}/collections/{args.collection}", timeout=12)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError("Cannot access Qdrant. Check Ubuntu: sudo docker compose ps") from exc
        info = r.json().get("result", {})
        print("Qdrant collection:", args.collection,
              "| vectors:", info.get("points_count"),
              "| indexed:", info.get("indexed_vectors_count"))
        print("Query:", args.query)
        print("Graph criteria: drug=", args.drug, "; section=", args.section,
              "; confirmed contraindication=", args.required_contraindication)

        driver = GraphDatabase.driver(
            args.neo4j_uri, auth=("neo4j", read_local_password()),
            connection_timeout=12,
        )
        try:
            driver.verify_connectivity()
            candidates = graph_candidates(
                driver, drug=args.drug, section=args.section,
                required=args.required_contraindication)
        finally:
            driver.close()
        print("Graph-approved text chunks:", len(candidates))
        if not candidates:
            print("No graph-approved candidates: Hybrid will return nothing (no fallback).")
        print("Loading local embedding model", DEFAULT_MODEL)
        from fastembed import TextEmbedding
        model = TextEmbedding(model_name=DEFAULT_MODEL)
        vector = list(model.embed([args.query]))[0].tolist()
        if len(vector) != 384:
            raise ValueError("Unexpected embedding dimension; expected 384")

        # Mode A: semantic similarity alone, ignoring the explicit graph criteria.
        a = qdrant_query(http, url=args.qdrant_url, collection=args.collection,
                         embedding=vector, k=args.k)
        # Mode B: Cypher traversal + explicit conditions, deterministic graph ordering.
        b = candidates[:args.k]
        # Mode C: Neo4j-approved set, then cosine ANN ranking only within that set.
        c = qdrant_query(
            http, url=args.qdrant_url, collection=args.collection, embedding=vector,
            k=args.k, allowed_chunk_ids=[row["chunk_id"] for row in candidates])
        print_results("A — Vector-only", a, args.k)
        print_results("B — Graph-only", b, args.k)
        print_results("C — Hybrid GraphRAG", c, args.k)
        print("\nThis is a functional pilot, NOT benchmark accuracy or a medical recommendation.")
        print("Unknown / missing contraindication relationships are NOT interpreted as safe.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError, ImportError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
