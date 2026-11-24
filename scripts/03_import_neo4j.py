import argparse
import json
import os
import pathlib
from collections import defaultdict
from neo4j import GraphDatabase

ROOT = pathlib.Path(__file__).resolve().parents[1]
KINDS = {"Drug", "DrugLabel", "ActiveIngredient", "DrugClass",
         "AdministrationRoute", "TextSection", "TextChunk",
         "Contraindication", "InteractionTarget", "Condition", "SideEffect"}
RELATIONS = {"HAS_LABEL", "HAS_ACTIVE_INGREDIENT", "BELONGS_TO_CLASS",
             "ADMINISTERED_VIA", "HAS_SECTION", "HAS_CHUNK",
             "HAS_CONTRAINDICATION", "INTERACTS_WITH", "INDICATED_FOR", "HAS_SIDE_EFFECT"}


def rows_jsonl(path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def batched(rows, size=200):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def write_batch(tx, query, rows):
    tx.run(query, rows=rows).consume()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=pathlib.Path, default=ROOT / "data" / "processed")
    ap.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    ap.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    args = ap.parse_args()
    passwd = os.getenv("NEO4J_PASSWORD")
    if not passwd:
        ap.error("Set NEO4J_PASSWORD first (same password as in .env)")
    nodes = rows_jsonl(args.input / "nodes.jsonl")
    edges = rows_jsonl(args.input / "edges.jsonl")
    grouped_nodes, grouped_edges = defaultdict(list), defaultdict(list)
    for node in nodes:
        if node["kind"] not in KINDS:
            raise ValueError("Unexpected node label: " + node["kind"])
        grouped_nodes[node["kind"]].append(node)
    for edge in edges:
        if edge["relationship"] not in RELATIONS:
            raise ValueError("Unexpected relationship: " + edge["relationship"])
        grouped_edges[edge["relationship"]].append(edge)
    with GraphDatabase.driver(args.uri, auth=(args.user, passwd)) as driver:
        driver.verify_connectivity()
        with driver.session(database="neo4j") as session:
            for line in (ROOT / "schema" / "neo4j_schema.cypher").read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("//"):
                    session.run(line).consume()
            for kind, group in grouped_nodes.items():
                # Whitelist validation above ensures label/relationship names cannot be injected.
                query = f"UNWIND $rows AS row MERGE (n:Entity:{kind} {{id: row.id}}) SET n += row.properties"
                for batch in batched(group):
                    session.execute_write(write_batch, query, batch)
            for rel, group in grouped_edges.items():
                query = ("UNWIND $rows AS row MATCH (a:Entity {id: row.source_id}) "
                         "MATCH (b:Entity {id: row.target_id}) "
                         f"MERGE (a)-[r:{rel}]->(b) "
                         "SET r.evidence_id = row.evidence_id, r.verification_status = row.verification_status")
                for batch in batched(group):
                    session.execute_write(write_batch, query, batch)
        print(f"Imported {len(nodes)} nodes and {len(edges)} relationships into Neo4j.")


if __name__ == "__main__":
    main()
