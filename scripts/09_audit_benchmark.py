from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def rows_csv(path):
    if not path.is_file():
        raise FileNotFoundError(f"Missing file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rows_jsonl(path):
    if not path.is_file():
        raise FileNotFoundError(f"Missing file: {path}")
    with path.open(encoding="utf-8-sig") as f:
        return [json.loads(x) for x in f if x.strip()]


def concept_id(kind, label):
    return kind.upper() + ":" + hashlib.sha256(label.casefold().encode("utf-8")).hexdigest()[:20]


def canonical_id(kind, label):
    # Matches 02_prepare_dataset.hash_id(prefix, label.casefold()).
    return kind.upper() + ":" + hashlib.sha256(label.casefold().encode("utf-8")).hexdigest()[:20]


def split_ids(value):
    return set(x.strip() for x in (value or "").split("|") if x.strip())


def normalize(value):
    return " ".join(str(value or "").casefold().split())


def short(value, n=220):
    s = " ".join(str(value or "").split())
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def main():
    query_file = ROOT / "benchmark" / "queries_to_review.csv"
    query_rows = rows_csv(query_file)
    raw_file = ROOT / "data" / "raw" / "openfda_pilot.json"
    if not raw_file.is_file():
        raise FileNotFoundError(f"Missing original openFDA input: {raw_file}")
    raw = json.loads(raw_file.read_text(encoding="utf-8-sig"))
    nodes = rows_jsonl(ROOT / "data" / "processed" / "nodes.jsonl")
    chunks = rows_jsonl(ROOT / "data" / "processed" / "chunks.jsonl")
    annotations = [a for a in rows_csv(ROOT / "annotations" / "verified_constraints.csv")
                   if a.get("status", "").strip().casefold() == "verified"]
    interactions = rows_csv(ROOT / "annotations" / "interaction_semantics_9.csv")

    drug_nodes = {n["id"]: n for n in nodes if n["kind"] == "Drug"}
    ingredient_nodes = {n["id"]: n for n in nodes if n["kind"] == "ActiveIngredient"}
    chunks_by_id = {c["chunk_id"]: c for c in chunks}
    raw_by_drug = {"DRUG:" + rec["set_id"]: rec for rec in raw["results"] if rec.get("set_id")}
    label_owner = {"LABEL:" + rec["id"]: "DRUG:" + rec["set_id"]
                   for rec in raw["results"] if rec.get("id") and rec.get("set_id")}
    if set(raw_by_drug) != set(drug_nodes):
        raise ValueError("Mismatch between drugs in raw openFDA file and prepared nodes; keep the same corpus snapshot.")

    # Validate source of every manually reviewed annotation: its quotation must
    # actually occur inside that same drug's source chunk.
    invalid_sources = []
    con_by_id = defaultdict(set)
    for a in annotations:
        aid = a.get("concept_id", "").strip() or canonical_id(a["concept_type"], a["concept_label"])
        ck = chunks_by_id.get(a.get("evidence_chunk_id"))
        if not ck or ck["drug_id"] != a["drug_id"] or normalize(a.get("evidence_quote")) not in normalize(ck.get("text")):
            invalid_sources.append((a["drug_id"], a["concept_label"]))
        if a["relation"] == "HAS_CONTRAINDICATION":
            con_by_id[aid].add(a["drug_id"])
    inter_by_target = defaultdict(list)
    for s in interactions:
        inter_by_target[s["target_id"]].append(s)
        ck = chunks_by_id.get(s.get("chunk_id"))
        if not ck or ck["drug_id"] != s["drug_id"] or normalize(s.get("evidence_quote")) not in normalize(ck.get("text")):
            invalid_sources.append((s["drug_id"], s["interaction_target"]))

    # Metadata-backed, direct lookup in the original openFDA snapshot (not
    # the Neo4j search result). This is evidence, not external validation.
    substance_by_drug = {}
    for d, rec in raw_by_drug.items():
        substance_by_drug[d] = {normalize(s) for s in (rec.get("openfda") or {}).get("substance_name", [])}
    ingredient_sources = defaultdict(set)
    for iid, inode in ingredient_nodes.items():
        n = normalize(inode["properties"].get("name", ""))
        ingredient_sources[iid] = {d for d, vals in substance_by_drug.items() if n in vals}

    # Simple lexical shortlists for SEMANTIC review only. These are NOT gold.
    stop = set("a an the of in on to for is are and or with without which what whose does do have has as by at who from their this that official drug drugs medicine medicines label labels discuss around including among where reason list lists are was explicitly used use".split())
    def terms(text):
        return set(t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 3 and t not in stop)
    def lexical_shortlist(query):
        q = terms(query)
        scores = defaultdict(lambda: (0, None))
        for c in chunks:
            ct = terms(c.get("text", ""))
            score = len(q & ct)
            # This is only a quick review shortlist. Text may be longer and
            # contain a lot of shared medical vocabulary.
            if score > scores[c["drug_id"]][0]:
                scores[c["drug_id"]] = (score, c)
        return [(d, sc, ck) for d, (sc, ck) in
                sorted(scores.items(), key=lambda pair: (-pair[1][0], pair[0]))[:7] if sc > 0]

    audit_rows = []
    packet = ["# Review packet — 30 draft retrieval questions", "",
              "**Corpus scope:** 25 openFDA labels; one selected revision per label.",
              "**Answer unit:** distinct Drug ID, not TextChunk.",
              "**Important:** no gold answers are approved by this tool. Review each question against the original openFDA snapshot, including possible additional relevant labels.",
              "**Do not treat an absent contraindication/interaction as evidence of medical safety.**", "",
              "## Interpretation cautions", "",
              "- Q01–Q08: query paraphrases are associated with known supporting excerpts. They need a corpus-wide review for additional relevant records.",
              "- Q09–Q15: source candidates can be checked directly against the original openFDA substance_name field, but source metadata is shared with graph construction.",
              "- Q16–Q23: the wording 'verified contraindication' closely matches the annotation labels used to create the graph. These are positive-claim tests, not negation/exclusion tests.",
              "- Q24–Q25: classifications must be checked against the underlying source excerpt. A missing prohibition among reviewed records does not mean a drug combination is safe.",
              "- Q26–Q30: all are conjunctive filters, but most name the primary medicine; they test traversal/AND logic rather than difficult entity resolution.",
              "- Some queries reuse the same exact source chunks, so the test cases are correlated.",
              "- All three retrieval modes must return ranked distinct Drug IDs, with the same test corpus and the same k; disclose that graph filters are supplied to the structured modes rather than inferred from free text.", ""]
    issues_by_question = {}
    failed = 0
    for r in query_rows:
        qid = r["query_id"]
        proposed = split_ids(r["proposed_drug_ids"])
        evidence_ids = split_ids(r["proposed_evidence_ids"])
        issues = []
        f = json.loads(r["graph_filter_json"])
        kind = f["kind"]
        if r["gold_drug_ids"].strip() or r["review_status"].strip() != "pending":
            issues.append("Already edited/approved; this file is meant to be the original draft.")
        if not proposed:
            issues.append("No proposed candidate.")
        for d in proposed:
            if d not in drug_nodes:
                issues.append("Unknown candidate Drug ID: " + d)
        for ev in evidence_ids:
            if ev.startswith("CHUNK:"):
                ck = chunks_by_id.get(ev)
                if not ck:
                    issues.append("Evidence chunk missing: " + ev)
                elif ck["drug_id"] not in proposed:
                    issues.append("Chunk drug does not match any proposed candidate: " + ev)
            elif ev.startswith("LABEL:"):
                label_id = ev.split("#", 1)[0]
                if label_id not in label_owner:
                    issues.append("Source label missing: " + label_id)
                elif label_owner[label_id] not in proposed:
                    issues.append("Source label owner does not match proposals: " + label_id)
            else:
                issues.append("Unknown evidence pointer format: " + ev)

        source = None
        lexical = []
        if kind == "semantic_unconstrained":
            lexical = lexical_shortlist(r["query_en"])
            issues.append("Semantic: full-corpus manual relevance judgment required; lexical shortlist is NOT exhaustive.")
        elif kind == "ingredient":
            if f["ingredient_id"] not in ingredient_nodes:
                issues.append("Ingredient ID not in prepared nodes.")
                source = set()
            else:
                source = ingredient_sources[f["ingredient_id"]]
        elif kind == "contraindication":
            source = con_by_id[f["contraindication_id"]]
        elif kind == "interaction":
            source = {s["drug_id"] for s in inter_by_target[f["target_id"]] if s["interaction_type"] == f["interaction_type"]}
        elif kind == "interaction_monitor_not_prohibited":
            source = {s["drug_id"] for s in inter_by_target[f["target_id"]]
                      if s["interaction_type"] != "CONTRAINDICATED_COADMINISTRATION"
                      and s["action_type"] in {"MONITOR_INR", "MONITOR_BLEEDING"}}
            issues.append("Closed-world negative condition applies ONLY to reviewed interactions; not a clinical absence claim.")
        elif kind == "ingredient_and_contraindication":
            source = ingredient_sources[f["ingredient_id"]] & con_by_id[f["contraindication_id"]]
        elif kind == "ingredient_and_interaction":
            source = ingredient_sources[f["ingredient_id"]] & {s["drug_id"] for s in inter_by_target[f["target_id"]]}
        else:
            issues.append("Unsupported query kind: " + kind)
        source_set = set(source) if source is not None else set()
        if source is not None and source_set != proposed:
            issues.append("MISMATCH: draft candidates differ from evidence-backed source-derived candidates.")
        if kind in {"contraindication", "interaction", "ingredient_and_contraindication", "ingredient_and_interaction"}:
            issues.append("Only currently reviewed facts are covered; benchmark wording must stay within this scope.")
        if qid in {"Q01", "Q04", "Q16", "Q21", "Q17", "Q20", "Q03", "Q06"}:
            issues.append("Shares a core fact/source with another query; avoid claiming all tests are independent.")
        if qid in {"Q26", "Q27", "Q28", "Q29", "Q30"}:
            issues.append("Primary ingredient is explicitly named, so this is a controlled conjunctive traversal test.")
        if qid == "Q25":
            issues.append("Requires caution: NOT a verified contraindication in the 9 reviewed interaction records only.")
        fatal = [i for i in issues if i.startswith(("MISMATCH", "Unknown", "Evidence", "Chunk drug", "Source label", "Ingredient ID", "Unsupported"))]
        if fatal:
            failed += 1
        def drug_names(ids):
            return "; ".join(drug_nodes[d]["properties"].get("generic_name", d) for d in sorted(ids) if d in drug_nodes)
        audit_rows.append({
            "query_id": qid, "category": r["category"], "kind": kind,
            "proposed_drug_ids": "|".join(sorted(proposed)),
            "proposed_drug_names": drug_names(proposed),
            "source_candidate_ids_NOT_GOLD": "|".join(sorted(source_set)) if source is not None else "REQUIRES_MANUAL_CORPUS_REVIEW",
            "draft_matches_sources": "PENDING_MANUAL_REVIEW" if source is None else str(source_set == proposed),
            "blocking_source_issues": " | ".join(fatal),
            "review_notes": " | ".join(issues),
            "gold_drug_ids": "", "review_status": "pending",
        })
        packet += [f"## {qid} — {r['category']}", "", r["query_en"], "",
                   "- Proposed source candidate(s): " + (drug_names(proposed) or "(none)"),
                   "- Source-based candidates (NOT approved gold): " +
                   (drug_names(source_set) or "(none)") if source is not None else "- Source-based candidates: manual corpus review required.",
                   "- Notes: " + ("; ".join(issues) if issues else "Source consistency check passed. Independent gold review still required."), ""]
        for ev in sorted(evidence_ids)[:3]:
            ck = chunks_by_id.get(ev)
            if ck:
                packet.append(f"  - Evidence `{ev}`: {short(ck.get('text', ''), 330)}")
            else:
                packet.append(f"  - Evidence `{ev}`: metadata pointer, not a text chunk")
        if lexical:
            packet += ["", "  **Lexical shortlist for further review — NOT gold:**"]
            for d, sc, ck in lexical[:5]:
                packet.append(f"  - {drug_nodes[d]['properties'].get('generic_name', d)} (token overlap {sc}), `{ck['chunk_id']}`: {short(ck.get('text', ''), 130)}")
        packet += [""]
        issues_by_question[qid] = issues

    output_dir = ROOT / "benchmark"
    with (output_dir / "audit_questions.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(audit_rows[0]))
        writer.writeheader()
        writer.writerows(audit_rows)
    (output_dir / "review_packet.md").write_text("\n".join(packet), encoding="utf-8")
    summary = {
        "queries": len(query_rows),
        "categories": dict(Counter(r["category"] for r in query_rows)),
        "raw_label_count": len(raw_by_drug),
        "source_evidence_integrity_failures": invalid_sources,
        "question_blocking_mismatches": failed,
        "gold_approved_by_script": 0,
        "important": "Draft consistency checks are NOT independent human gold adjudication. No Precision@k/Recall@k calculated.",
        "written_files": ["benchmark/audit_questions.csv", "benchmark/review_packet.md"],
    }
    (output_dir / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Draft queries:", summary["queries"], summary["categories"])
    print("Raw openFDA label records:", len(raw_by_drug))
    print("Broken quote/source links:", len(invalid_sources))
    print("Question/source mismatches:", failed)
    print("Approved gold answers: 0 (deliberately)")
    print("Created benchmark/audit_summary.json, benchmark/audit_questions.csv, benchmark/review_packet.md")
    if invalid_sources or failed:
        print("WARNING: inspect the reported mismatches before gold approval")
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError) as err:
        print("ERROR:", err, file=sys.stderr)
        raise SystemExit(1)
