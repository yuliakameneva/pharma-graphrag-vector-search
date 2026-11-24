from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FIELDS = [
    "query_id", "category", "query_en", "graph_filter_json", "proposed_drug_ids",
    "proposed_evidence_ids", "gold_drug_ids", "review_status", "reviewer_note",
]


def load_jsonl(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Not found: {path}. Run 02_prepare_dataset.py first.")
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_csv(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def pair_ids(rows, key):
    return sorted(set(row[key] for row in rows if row.get(key)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "benchmark")
    args = ap.parse_args()

    nodes = load_jsonl(ROOT / "data" / "processed" / "nodes.jsonl")
    edges = load_jsonl(ROOT / "data" / "processed" / "edges.jsonl")
    annotations = load_csv(ROOT / "annotations" / "verified_constraints.csv")
    semantics = load_csv(ROOT / "annotations" / "interaction_semantics_9.csv")

    by_id = {n["id"]: n for n in nodes}
    drug_ids = {n["id"] for n in nodes if n["kind"] == "Drug"}
    props = lambda node_id: by_id[node_id]["properties"]
    if len(drug_ids) < 20:
        raise ValueError("Expected >=20 Drug nodes from real dataset; inspect processed files.")
    if not any(e["relationship"] == "INTERACTS_WITH" for e in edges):
        raise ValueError("No INTERACTS_WITH edges. Confirm 06_review_interactions step.")
    verified = [r for r in annotations if r.get("status", "").strip().lower() == "verified"]
    contraind = [r for r in verified if r.get("relation") == "HAS_CONTRAINDICATION"]
    interact = [r for r in verified if r.get("relation") == "INTERACTS_WITH"]
    if len(contraind) < 11 or len(interact) < 9:
        raise ValueError(f"Expected >=11 verified contraindications and >=9 verified interactions, got {len(contraind)} and {len(interact)}")
    sem_by_pair = {(r["drug_id"], r["target_id"]): r for r in semantics}
    if len(sem_by_pair) < 9:
        raise ValueError("Missing reviewed 9-interaction semantics CSV")
    # The original annotation sheet intentionally permits empty concept_id.
    # Reconstruct it ONLY through the exact, existing Drug->Concept graph edge.
    for r in verified:
        rel = r["relation"]
        label = r["concept_label"].strip().casefold()
        linked = [e["target_id"] for e in edges if e["relationship"] == rel
                  and e["source_id"] == r["drug_id"]
                  and e["target_id"] in by_id
                  and props(e["target_id"]).get("name", "").strip().casefold() == label]
        if len(set(linked)) != 1:
            raise ValueError(f"Cannot resolve exactly one verified concept: {r['drug_id']} / {rel} / {label}")
        resolved = linked[0]
        if r.get("concept_id", "").strip() and r["concept_id"] != resolved:
            raise ValueError("Annotation concept ID contradicts imported graph")
        r["concept_id"] = resolved
    for r in verified:
        if r["drug_id"] not in drug_ids or r["evidence_chunk_id"] not in by_id:
            raise ValueError(f"Broken verified claim linkage: {r.get('concept_label')}")

    edges_by_rel = defaultdict(list)
    for e in edges:
        edges_by_rel[e["relationship"]].append(e)
    ingredients_by_drug = defaultdict(list)
    drugs_by_ingredient = defaultdict(set)
    for e in edges_by_rel["HAS_ACTIVE_INGREDIENT"]:
        ingredients_by_drug[e["source_id"]].append(e["target_id"])
        drugs_by_ingredient[e["target_id"]].add(e["source_id"])
    classes_by_drug = defaultdict(list)
    for e in edges_by_rel["BELONGS_TO_CLASS"]:
        classes_by_drug[e["source_id"]].append(e["target_id"])
    drug_contras = defaultdict(list)
    for e in edges_by_rel["HAS_CONTRAINDICATION"]:
        drug_contras[e["source_id"]].append(e["target_id"])
    drug_interacts = defaultdict(list)
    for e in edges_by_rel["INTERACTS_WITH"]:
        drug_interacts[e["source_id"]].append(e["target_id"])

    def query_row(category, query, filt, proposed, evidence=(), note=""):
        ids = sorted(set(proposed))
        if any(d not in drug_ids for d in ids):
            raise ValueError(f"Non-Drug candidate result: {ids}")
        if not ids:
            raise ValueError(f"No supporting answer candidates for: {query}")
        return {
            "query_id": "", "category": category, "query_en": query,
            "graph_filter_json": json.dumps(filt, ensure_ascii=False, sort_keys=True),
            "proposed_drug_ids": "|".join(ids),
            "proposed_evidence_ids": "|".join(sorted(set(evidence))),
            "gold_drug_ids": "", "review_status": "pending", "reviewer_note": note,
        }

    rows = []
    # Eight genuine paraphrase/semantic queries. Gold candidates are sourced
    # from reviewed evidence; we do NOT inject these answers into graph_filters.
    cases = [
        ("malignant hypertension as a reason not to take a medicine", "contra", "malignant hypertension"),
        ("avoidance of an anti-inflammatory drug around coronary bypass surgery", "contra", "coronary artery bypass"),
        ("drug combination with pimozide that is contraindicated", "contra", "pimozide"),
        ("bacterial endocarditis listed among situations where a medicine must not be used", "contra", "bacterial endocarditis"),
        ("a medicine prohibited in patients with a past allergic response to aspirin or other NSAIDs", "contra", "history of asthma"),
        ("drug restriction involving monoamine oxidase inhibitors and a fourteen-day interval", "contra", "maoi"),
        ("interference with the antiplatelet effect of low-dose aspirin", "interact", "aspirin"),
        ("an increase of INR potentially caused by enzyme inhibition", "interact", "cyp2c9/cyp1a2/cyp3a4 inhibitors"),
    ]
    for idea, kind, key in cases:
        source = contraind if kind == "contra" else interact
        hits = [r for r in source if key in r["concept_label"].casefold()]
        if not hits:
            raise ValueError(f"Cannot ground a semantic question in reviewed claims: {key}")
        rows.append(query_row("semantic", f"Which official drug labels discuss {idea}?",
                              {"kind": "semantic_unconstrained"},
                              [r["drug_id"] for r in hits],
                              [r["evidence_chunk_id"] for r in hits],
                              "Candidate is evidence-based, NOT approved gold. Review all plausible labels."))

    # Seven structured metadata questions. Choose ingredients with cross-drug
    # overlap first, then deterministic alphabetical order for reproducibility.
    ingredients = sorted(drugs_by_ingredient, key=lambda ing: (-len(drugs_by_ingredient[ing]), props(ing).get("name", ""), ing))
    if len(ingredients) < 7:
        raise ValueError("Not enough distinct ActiveIngredient nodes")
    for ing in ingredients[:7]:
        name = props(ing).get("name", "")
        links = [e for e in edges_by_rel["HAS_ACTIVE_INGREDIENT"] if e["target_id"] == ing]
        rows.append(query_row("structural", f"Which drug labels in this collection contain {name} as an active ingredient?",
                              {"kind": "ingredient", "ingredient_id": ing}, drugs_by_ingredient[ing],
                              [e.get("evidence_id", "") for e in links],
                              "Check ingredient membership against openFDA label metadata."))

    # Eight STRICT constraints based on explicitly verified contraindications.
    # Spread queries across medicines; do not treat absent edges as negation.
    grouped = defaultdict(list)
    for r in contraind:
        grouped[r["drug_id"]].append(r)
    for group in grouped.values():
        group.sort(key=lambda r: r["concept_label"])
    selected = []
    while len(selected) < 8 and any(grouped.values()):
        for drug_id in sorted(grouped):
            if grouped[drug_id] and len(selected) < 8:
                selected.append(grouped[drug_id].pop(0))
    if len(selected) != 8:
        raise ValueError("Not enough contraindications to build 8 strict queries")
    for r in selected:
        concept = r["concept_id"]
        ids = {e["source_id"] for e in edges_by_rel["HAS_CONTRAINDICATION"] if e["target_id"] == concept}
        label = r["concept_label"]
        rows.append(query_row("strict", f"Which drug labels explicitly list '{label}' as a verified contraindication?",
                              {"kind": "contraindication", "contraindication_id": concept}, ids,
                              [r["evidence_chunk_id"]],
                              "Only positive documented contraindications; absence is unknown, not safe."))

    # Two more strict queries make explicit distinctions between interaction
    # categories rather than falsely equating every interaction with prohibition.
    maoi_sem = [s for s in semantics if s["interaction_type"] == "CONTRAINDICATED_COADMINISTRATION" and "MAOI" in s["interaction_target"].upper()]
    if not maoi_sem:
        raise ValueError("No documented contraindicated MAOI combination")
    m = maoi_sem[0]
    rows.append(query_row("strict", "Which drug labels explicitly prohibit coadministration with monoamine oxidase inhibitors?",
                          {"kind": "interaction", "target_id": m["target_id"], "interaction_type": "CONTRAINDICATED_COADMINISTRATION"},
                          [s["drug_id"] for s in maoi_sem], [s["chunk_id"] for s in maoi_sem],
                          "Prohibition is based on reviewed interaction type, not on vector similarity."))
    warfarin_sem = [s for s in semantics if s["interaction_target"].strip().casefold() == "warfarin sodium"
                    and s["interaction_type"] != "CONTRAINDICATED_COADMINISTRATION"
                    and s["action_type"] in {"MONITOR_INR", "MONITOR_BLEEDING"}]
    if not warfarin_sem:
        raise ValueError("No monitored (non-prohibited) interaction with warfarin")
    rows.append(query_row("strict",
                          "Which drug labels have a documented interaction with warfarin that requires monitoring but is NOT classified as contraindicated coadministration in the reviewed records?",
                          {"kind": "interaction_monitor_not_prohibited", "target_id": warfarin_sem[0]["target_id"]},
                          [s["drug_id"] for s in warfarin_sem], [s["chunk_id"] for s in warfarin_sem],
                          "NOT contraindicated *among reviewed interactions* does not imply clinically safe."))

    # Five genuine conjunctive graph filters with multiple independent relations.
    relevant_drugs = sorted(set(drug_contras) & set(ingredients_by_drug))
    if len(relevant_drugs) < 3:
        raise ValueError("Need contraindicated drugs with structured ingredients")
    for d in relevant_drugs[:3]:
        ing = sorted(ingredients_by_drug[d])[0]
        con = sorted(drug_contras[d])[0]
        qualifying = {x for x in drug_ids if ing in ingredients_by_drug[x] and con in drug_contras[x]}
        rows.append(query_row("multi_hop",
                              f"Which drug labels contain {props(ing).get('name')} AND explicitly list '{props(con).get('name')}' as a contraindication?",
                              {"kind": "ingredient_and_contraindication", "ingredient_id": ing, "contraindication_id": con},
                              qualifying, [a["evidence_chunk_id"] for a in contraind if a["concept_id"] == con],
                              "Requires Drug->Ingredient AND Drug->Contraindication."))
    relevant_interactions = sorted(set(drug_interacts) & set(ingredients_by_drug))
    if len(relevant_interactions) < 2:
        raise ValueError("Need interacting drugs with structured ingredients")
    for d in relevant_interactions[:2]:
        ing = sorted(ingredients_by_drug[d])[0]
        target = sorted(drug_interacts[d])[0]
        qualifying = {x for x in drug_ids if ing in ingredients_by_drug[x] and target in drug_interacts[x]}
        rows.append(query_row("multi_hop",
                              f"Which drug labels contain {props(ing).get('name')} AND have a verified interaction with {props(target).get('name')}?",
                              {"kind": "ingredient_and_interaction", "ingredient_id": ing, "target_id": target},
                              qualifying,
                              [a["evidence_chunk_id"] for a in interact if a["drug_id"] in qualifying and a["concept_id"] == target],
                              "Requires Drug->Ingredient AND Drug->InteractionTarget."))

    expected = {"semantic": 8, "structural": 7, "strict": 10, "multi_hop": 5}
    counts = dict(Counter(r["category"] for r in rows))
    if len(rows) != 30 or counts != expected:
        raise AssertionError(f"Expected 30 queries {expected}, got {len(rows)} {counts}")
    for idx, r in enumerate(rows, 1):
        r["query_id"] = f"Q{idx:02d}"
        if r["review_status"] != "pending" or r["gold_drug_ids"]:
            raise AssertionError("Never auto-approve gold judgments")

    args.out.mkdir(parents=True, exist_ok=True)
    output = args.out / "queries_to_review.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "status": "DRAFT_ONLY_NOT_BENCHMARK_SCORES", "queries_total": 30,
        "categories": expected, "corpus_drugs": len(drug_ids),
        "verified_claims": len(verified), "gold_approved": 0,
        "retrieval_unit": "distinct Drug ID",
        "source_of_proposals": "Neo4j-import JSONL + locally verified annotations",
        "limitations": [
            "The 8 semantic questions require human review of all potentially relevant drug labels.",
            "Graph-derived candidates are not independent ground truth and may omit true relevant labels.",
            "Several questions share underlying source chunks; benchmark cases are correlated.",
            "Only explicitly documented interactions can be negated within the reviewed interaction subset.",
            "No Precision@k/Recall@k should be reported until gold_drug_ids have been manually adjudicated.",
            "This is a retrieval benchmark, not clinical treatment or drug-safety advice."
        ],
    }
    (args.out / "overview.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Prepared 30 draft questions:", counts)
    print("Verified claims available:", len(verified))
    print("Gold reference answers APPROVED: 0 (intentionally)")
    print("Saved:", output)
    print("Saved:", args.out / "overview.json")
    print("Next: manually adjudicate gold_drug_ids; do not interpret suggestions as benchmark results.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, AssertionError, json.JSONDecodeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
