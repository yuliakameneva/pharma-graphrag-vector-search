import argparse
import csv
import os
from pathlib import Path
import re
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
CSV_FILE = ROOT / "annotations" / "interaction_semantics_9.csv"
FIELDS = {
    "drug_id", "drug", "target_id", "interaction_target", "chunk_id",
    "target_type", "interaction_type", "action_type", "clinical_effect", "evidence_quote"
}
TYPES = {
    "ANTIPLATELET_EFFECT_INTERFERENCE", "BLEEDING_RISK",
    "CONTRAINDICATED_COADMINISTRATION", "POTENTIAL_INR_INCREASE", "POTENTIAL_INR_DECREASE"
}
TARGET_TYPES = {"ACTIVE_SUBSTANCE", "NAMED_DRUG", "DRUG_CLASS", "DRUG_CLASS_GROUP", "ENZYME_MODULATOR_GROUP"}
ACTIONS = {"NOT_SPECIFIED_IN_EXCERPT", "MONITOR_BLEEDING", "INFORM_BLEEDING_RISK",
           "DO_NOT_COADMINISTER", "MONITOR_INR"}


def normalized(s):
    return re.sub(r"\s+", " ", str(s)).strip().casefold()


def load_semantics():
    with CSV_FILE.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not FIELDS.issubset(reader.fieldnames):
            raise ValueError("Missing CSV columns in " + str(CSV_FILE))
        rows = list(reader)
    if len(rows) != 9:
        raise ValueError(f"Expected exactly 9 reviewed interaction rows, got {len(rows)}")
    keys = set()
    for num, row in enumerate(rows, start=2):
        if any(not row.get(k, "").strip() for k in FIELDS):
            raise ValueError(f"Empty required CSV cell at row {num}")
        key = (row["drug_id"], row["target_id"], row["chunk_id"])
        if key in keys:
            raise ValueError(f"Duplicate interaction at row {num}")
        keys.add(key)
        if row["interaction_type"] not in TYPES or row["target_type"] not in TARGET_TYPES or row["action_type"] not in ACTIONS:
            raise ValueError(f"Unexpected category at row {num}")
        if (row["interaction_type"] == "CONTRAINDICATED_COADMINISTRATION") != (row["action_type"] == "DO_NOT_COADMINISTER"):
            raise ValueError(f"Contraindication/action disagreement at row {num}")
    return rows


def find_password():
    if os.getenv("NEO4J_PASSWORD"):
        return os.environ["NEO4J_PASSWORD"]
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("NEO4J_PASSWORD="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise ValueError("NEO4J_PASSWORD missing in the environment and .env")


def preflight(session, rows):
    """All 9 checks must pass before anything is written."""
    query = """
    MATCH (d:Drug {id: $drug_id})-[r:INTERACTS_WITH]->(t:InteractionTarget {id: $target_id})
    MATCH (c:TextChunk {id: $chunk_id})
    RETURN d.generic_name AS drug, t.name AS target, r.evidence_id AS edge_evidence,
           c.drug_id AS chunk_drug_id, c.section_type AS section_type, c.text AS source_text
    """
    for idx, row in enumerate(rows, 1):
        matches = list(session.run(query, drug_id=row["drug_id"], target_id=row["target_id"], chunk_id=row["chunk_id"]))
        if len(matches) != 1:
            raise ValueError(f"Interaction {idx}: expected one matching Drug->Target edge and TextChunk; got {len(matches)}")
        result = matches[0]
        if normalized(result["drug"]) != normalized(row["drug"]) or normalized(result["target"]) != normalized(row["interaction_target"]):
            raise ValueError(f"Interaction {idx}: Drug/Target name differs from CSV")
        if result["edge_evidence"] != row["chunk_id"] or result["chunk_drug_id"] != row["drug_id"]:
            raise ValueError(f"Interaction {idx}: mismatched evidence_id or source drug")
        if result["section_type"] != "drug_interactions":
            raise ValueError(f"Interaction {idx}: supporting chunk is not a drug-interactions section")
        if normalized(row["evidence_quote"]) not in normalized(result["source_text"]):
            raise ValueError(f"Interaction {idx}: EXACT citation is missing from stored chunk")
        print(f"{idx}. {row['drug']} -> {row['interaction_target']}: {row['interaction_type']} [verified quote]")
    print("Preflight: 9/9 matches, source links and evidence quotes verified.")


def enrich(tx, rows):
    query = """
    UNWIND $rows AS row
    MATCH (:Drug {id:row.drug_id})-[r:INTERACTS_WITH]->(:InteractionTarget {id:row.target_id})
    WHERE r.evidence_id = row.chunk_id
    SET r.interaction_type = row.interaction_type,
        r.target_type = row.target_type,
        r.action_type = row.action_type,
        r.clinical_effect = row.clinical_effect,
        r.evidence_quote = row.evidence_quote,
        r.semantics_origin = 'source_reviewed_csv'
    RETURN count(r) AS updated
    """
    updated = tx.run(query, rows=rows).single()["updated"]
    if updated != len(rows):
        raise ValueError(f"Updated {updated} edges instead of {len(rows)}. Transaction aborted.")
    # Only exact (case-insensitive) matches between a NAMED_DRUG target and Drug
    # get a link. Do NOT infer membership of classes or symmetric interactions.
    links = 0
    ids = {r["target_id"] for r in rows if r["target_type"] == "NAMED_DRUG"}
    for tid in sorted(ids):
        result = tx.run("""
            MATCH (t:InteractionTarget {id:$tid})
            MATCH (d:Drug)
            WHERE toLower(trim(d.generic_name)) = toLower(trim(t.name))
            RETURN d.id AS id
        """, tid=tid).data()
        if len(result) > 1:
            raise ValueError(f"Ambiguous Drug match for interaction target {tid}")
        if len(result) == 1:
            tx.run("""
                MATCH (t:InteractionTarget {id:$tid}), (d:Drug {id:$did})
                MERGE (t)-[:RESOLVES_TO_DRUG]->(d)
            """, tid=tid, did=result[0]["id"]).consume()
            links += 1
        else:
            print(f"No exact Drug match for {tid}: RESOLVES_TO_DRUG not created")
    return updated, links


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-csv", action="store_true", help="Validate CSV without Neo4j")
    group.add_argument("--check", action="store_true", help="Read Neo4j and validate all evidence, without changing data")
    group.add_argument("--apply", action="store_true", help="Validate then update Neo4j after explicit confirmation")
    args = parser.parse_args()
    rows = load_semantics()
    print(f"Loaded {len(rows)} interaction annotations from {CSV_FILE.name}")
    print("Categories:", dict(Counter(row["interaction_type"] for row in rows)))
    if args.check_csv:
        print("CSV validation: OK. No database changes.")
        return
    from neo4j import GraphDatabase
    with GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                              auth=(os.getenv("NEO4J_USER", "neo4j"), find_password())) as driver:
        driver.verify_connectivity()
        with driver.session(database="neo4j") as session:
            preflight(session, rows)
            if args.check:
                print("Dry run complete. No data changed.")
                return
            print("\nThis operation adds properties to 9 verified INTERACTS_WITH edges.")
            print("It also links the known 'Warfarin sodium' target to its matching Drug node (one link).")
            if input("To apply changes type YES (English capitals): ").strip() != "YES":
                print("Cancelled: no changes made.")
                return
            updated, links = session.execute_write(enrich, rows)
            print(f"Success: enriched {updated} interaction edges; resolved {links} named Drug targets.")
            print("Re-run this script with --apply after a complete Neo4j rebuild to restore semantics.")
            print("The JSON dataset_stats.json does NOT change; these are Neo4j-only enrichment properties.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, csv.Error) as exc:
        print("ERROR:", exc)
        raise SystemExit(1)
