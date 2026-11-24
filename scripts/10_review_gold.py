from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "benchmark" / "queries_to_review.csv"
AUDIT = ROOT / "benchmark" / "audit_questions.csv"
WORK = ROOT / "benchmark" / "gold_review_working.csv"
SUMMARY = ROOT / "benchmark" / "gold_review_progress.json"
NODES = ROOT / "data" / "processed" / "nodes.jsonl"
CHUNKS = ROOT / "data" / "processed" / "chunks.jsonl"
FIELDS = [
    "query_id", "category", "query_en", "graph_filter_json",
    "proposed_drug_ids", "proposed_evidence_ids", "gold_drug_ids",
    "review_status", "reviewer_note", "reviewed_at_utc"
]

def read_csv(p):
    if not p.is_file():
        raise FileNotFoundError(f"Missing file: {p}")
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def read_jsonl(p):
    if not p.is_file():
        raise FileNotFoundError(f"Missing file: {p}")
    with p.open(encoding="utf-8-sig") as f:
        return [json.loads(l) for l in f if l.strip()]

def save(rows):
    WORK.parent.mkdir(parents=True, exist_ok=True)
    # Use temp + replace to avoid truncated output after interrupts.
    temp = WORK.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in FIELDS})
    temp.replace(WORK)
    counts = Counter((r["category"], r["review_status"]) for r in rows)
    doc = {
        "total_questions": len(rows),
        "approved": sum(r["review_status"] == "approved" for r in rows),
        "rejected": sum(r["review_status"] == "rejected" for r in rows),
        "pending": sum(r["review_status"] == "pending" for r in rows),
        "semantic_questions_still_require_full_corpus_review":
           [r["query_id"] for r in rows if r["category"] == "semantic" and r["review_status"] == "pending"],
        "counts_by_category_and_status": [
            {"category": cat, "status": st, "count": n}
            for (cat, st), n in sorted(counts.items())],
        "warning": "Manual acknowledgement of source-derived candidates is not independent external verification. Semantic questions are deliberately left pending. Do not benchmark 30 questions until all valid gold sets are approved.",
    }
    SUMMARY.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

def initialize():
    drafts = read_csv(DRAFT)
    audits = {r["query_id"]: r for r in read_csv(AUDIT)}
    if len(drafts) != 30 or len({r["query_id"] for r in drafts}) != 30:
        raise ValueError("Expected 30 unique questions in queries_to_review.csv")
    if set(r["query_id"] for r in drafts) != set(audits):
        raise ValueError("Draft questions and audit IDs disagree. Re-run 09_audit_benchmark.py.")
    if WORK.exists():
        rows = read_csv(WORK)
        if [r["query_id"] for r in rows] != [r["query_id"] for r in drafts]:
            raise ValueError("Existing review file has different question IDs/order. Back it up before rerunning.")
        return rows, audits
    rows = []
    for d in drafts:
        if d.get("gold_drug_ids", "").strip() or d.get("review_status", "pending") != "pending":
            raise ValueError("Original draft already contains approvals; refusing to overwrite them")
        row = {k: d.get(k, "") for k in FIELDS}
        row["review_status"] = "pending"
        row["reviewed_at_utc"] = ""
        rows.append(row)
    save(rows)
    return rows, audits

def pretty_excerpt(text, limit=1100):
    s = " ".join((text or "").split())
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + " ... [open original label for full context]"
    return s

def print_status(rows):
    counts = Counter(r["review_status"] for r in rows)
    print(f"Questions: {len(rows)} | approved: {counts['approved']} | rejected: {counts['rejected']} | pending: {counts['pending']}")
    print("Structural/strict/multi-hop can be reviewed here; semantic Q01–Q08 need full 25-label manual review later.")
    print("Files:", WORK.relative_to(ROOT), ",", SUMMARY.relative_to(ROOT))

def review_structured(rows, audits):
    nodes = {n["id"]: n for n in read_jsonl(NODES) if n.get("kind") == "Drug"}
    chunks = {c["chunk_id"]: c for c in read_jsonl(CHUNKS)}
    reviewable = [r for r in rows if r["category"] != "semantic" and r["review_status"] == "pending"]
    if not reviewable:
        print("No remaining nonsemantic pending questions.")
        print_status(rows)
        return
    print("\nCAUTION: Confirm both the evidence and completeness of the proposed answer set in the stated closed corpus / verified facts scope.")
    print("The candidate list comes from the same source dataset used to build the graph: it is NOT independent evidence.")
    print("For Q25, NOT marked contraindicated among the 9 reviewed records does NOT mean clinically safe.\n")
    for r in reviewable:
        aid = audits[r["query_id"]]
        print("\n" + "=" * 76)
        print(r["query_id"], "[", r["category"], "]")
        print("QUESTION:", r["query_en"])
        print("Candidates (source-derived, NOT gold):")
        for d in filter(None, r["proposed_drug_ids"].split("|")):
            print(" -", nodes.get(d, {}).get("properties", {}).get("generic_name", "unknown name"), f"({d})")
        for ev in filter(None, r["proposed_evidence_ids"].split("|")):
            if ev.startswith("CHUNK:"):
                ch = chunks.get(ev)
                print("Evidence", ev, ":", pretty_excerpt(ch.get("text", "") if ch else "MISSING"))
            else:
                print("Metadata evidence pointer:", ev, "(verify original openFDA substance_name)")
        print("Audit source consistency:", aid.get("draft_matches_sources"))
        if aid.get("blocking_source_issues", "").strip() or aid.get("draft_matches_sources", "") != "True":
            print("BLOCKED: cannot approve automatically because audit is not clean:", aid.get("blocking_source_issues"))
            continue
        if aid.get("review_notes", "").strip():
            print("CAUTION:", aid["review_notes"][:380])
        while True:
            answer = input("After checking ORIGINAL sources: approve complete answer set? [y]es/[n]o/[s]kip/[q]uit: ").strip().lower()
            if answer in {"y", "n", "s", "q"}:
                break
            print("Please enter y, n, s or q.")
        if answer == "q":
            print("Stopped; previous answers are saved.")
            break
        if answer == "s":
            continue
        r["review_status"] = "approved" if answer == "y" else "rejected"
        r["gold_drug_ids"] = r["proposed_drug_ids"] if answer == "y" else ""
        r["reviewed_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        r["reviewer_note"] = "Manual source review (closed-corpus, reviewed claims only); original proposed candidates checked." if answer == "y" else "Rejected by manual reviewer; requires correction of proposed candidates."
        save(rows)
        print("Saved", r["query_id"], "->", r["review_status"])
    print("\nReview session finished.")
    print_status(rows)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="Create/show review file and progress; no approvals")
    group.add_argument("--review-structured", action="store_true", help="Review Q09–Q30 interactively and save after each answer")
    args = parser.parse_args()
    rows, audit = initialize()
    if args.status:
        print_status(rows)
    else:
        review_structured(rows, audit)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError, csv.Error) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped. Previously saved answers preserved.")
