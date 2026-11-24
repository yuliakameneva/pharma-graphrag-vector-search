"""Inspect and safely reset questionable semantic gold judgments (Q01–Q08).

Usage in PowerShell, from project root:
  py scripts/12_recheck_semantic_gold.py --inspect Q01
  py scripts/12_recheck_semantic_gold.py --reset Q01
  py scripts/11_review_semantic_gold.py --review Q01

--inspect writes a non-authoritative keyword evidence navigation worksheet.
--reset asks for confirmation, backs up both CSVs, clears only the specified
query's judgments and approved gold, and updates progress. Q09–Q30 unaffected.
"""
from __future__ import annotations
import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmark"
WORK = BENCH / "gold_review_working.csv"
DECISIONS = BENCH / "semantic_review_decisions.csv"
PROGRESS = BENCH / "gold_review_progress.json"
RAW = ROOT / "data/raw/openfda_pilot.json"
SECTIONS = ("description", "indications_and_usage", "contraindications", "drug_interactions",
            "adverse_reactions", "warnings_and_cautions", "boxed_warning")
KEYWORDS = {
    "Q01": (r"malignant\s+hypertension", r"severe\s+hypertension"),
    "Q02": (r"coronary.{0,35}bypass", r"\bCABG\b"),
    "Q03": (r"\bpimozide\b",),
    "Q04": (r"bacterial\s+endocarditis", r"\bendocarditis\b"),
    "Q05": (r"urticaria", r"aspirin", r"NSAIDs?"),
    "Q06": (r"monoamine\s+oxidase", r"\bMAOI", r"14\s+days?"),
    "Q07": (r"antiplatelet", r"low.dose\s+aspirin"),
    "Q08": (r"\bINR\b", r"enzyme\s+inhibit"),
}

class StripHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pieces = []
    def handle_data(self, data):
        self.pieces.append(data)
    def handle_starttag(self, tag, attrs):
        if tag in ("br", "li", "p", "tr"):
            self.pieces.append(" ")

def source_text(parts):
    parser = StripHtml()
    parser.feed(" ".join(str(x) for x in parts))
    return " ".join(unescape(" ".join(parser.pieces)).split())

def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        return rdr.fieldnames, list(rdr)

def write_csv(path, fields, rows):
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    tmp.replace(path)

def inspect(qid, question_rows, decisions):
    data = json.loads(RAW.read_text(encoding="utf-8-sig"))
    labels = data.get("results", [])
    if len(labels) != 25:
        raise ValueError(f"Expected 25 openFDA records, found {len(labels)}")
    decisions_by_drug = {(x["query_id"], x["drug_id"]): x["decision"] for x in decisions}
    output = []
    for item in labels:
        did = "DRUG:" + str(item["set_id"])
        name_list = item.get("openfda", {}).get("generic_name", [])
        name = "; ".join(map(str, name_list)) if name_list else "(unnamed)"
        excerpts = []
        for section in SECTIONS:
            val = item.get(section, [])
            if not val:
                continue
            txt = source_text(val if isinstance(val, list) else [val])
            for pattern in KEYWORDS[qid]:
                match = re.search(pattern, txt, re.IGNORECASE)
                if match:
                    excerpts.append(f"[{section}] {txt[max(0,match.start()-150):match.end()+230]}")
        output.append({
            "query_id":qid,
            "drug_name":name,
            "drug_id":did,
            "current_judgment":decisions_by_drug.get((qid, did), "pending"),
            "keyword_hit_count":len(excerpts),
            "source_excerpts_NAVIGATION_ONLY":" || ".join(excerpts)[:2400],
            "manual_conclusion":"",
        })
    target = BENCH / f"{qid.lower()}_source_review.csv"
    write_csv(target, list(output[0].keys()), output)
    print(f"Saved source-navigation worksheet: {target.relative_to(ROOT)}")
    print("Current judgments:", dict(Counter(x["current_judgment"] for x in output)))
    print("Labels with keyword hints:", sum(int(x["keyword_hit_count"] > 0) for x in output), "/ 25")
    print("IMPORTANT: keyword matches DO NOT prove relevance; no matches DO NOT prove irrelevance.")
    print("A label is relevant only if its indexed text supports the FULL meaning of the question.")

def reset(qid, question_rows, qfields, decision_rows, dfields):
    matches = [x for x in question_rows if x["query_id"] == qid]
    if len(matches) != 1 or matches[0]["category"] != "semantic":
        raise ValueError(f"Expected exactly one semantic question {qid}")
    question = matches[0]
    affected = [d for d in decision_rows if d["query_id"] == qid]
    print(f"{qid}: status={question['review_status']}, gold IDs={len([x for x in question['gold_drug_ids'].split('|') if x])}, judgments={len(affected)}")
    if not affected and question["review_status"] == "pending" and not question["gold_drug_ids"]:
        print("Already reset; nothing to change.")
        return
    if input(f"To reset ONLY {qid}, type RESET {qid}: ").strip() != f"RESET {qid}":
        print("Cancelled; nothing changed.")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BENCH / "backups" / f"semantic_reset_{qid}_{stamp}"
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(WORK, destination / WORK.name)
    if DECISIONS.is_file():
        shutil.copy2(DECISIONS, destination / DECISIONS.name)
    if PROGRESS.is_file():
        shutil.copy2(PROGRESS, destination / PROGRESS.name)
    question["gold_drug_ids"] = ""
    question["review_status"] = "pending"
    question["reviewer_note"] = "Requires full-corpus source re-review; earlier approval reset."
    question["reviewed_at_utc"] = ""
    write_csv(WORK, qfields, question_rows)
    write_csv(DECISIONS, dfields, [d for d in decision_rows if d["query_id"] != qid])
    counts = Counter((x["category"], x["review_status"]) for x in question_rows)
    summary = {
      "total_questions": len(question_rows),
      "approved": sum(x["review_status"] == "approved" for x in question_rows),
      "rejected": sum(x["review_status"] == "rejected" for x in question_rows),
      "pending": sum(x["review_status"] == "pending" for x in question_rows),
      "semantic_questions_still_require_full_corpus_review": [x["query_id"] for x in question_rows if x["category"] == "semantic" and x["review_status"] == "pending"],
      "counts_by_category_and_status": [dict(category=category, status=status, count=n) for (category, status), n in sorted(counts.items())],
      "warning":"Source-snapshot manual relevance judgments only; not external medical adjudication. No clinical conclusions follow from negative judgments.",
    }
    PROGRESS.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Backup:", destination.relative_to(ROOT))
    print(f"Reset {qid}; removed {len(affected)} judgments. Other questions were preserved.")
    print(f"Status: approved={summary['approved']}, pending={summary['pending']}")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--inspect", choices=sorted(KEYWORDS), metavar="Q01", help="Create a 25-label source navigation CSV")
    group.add_argument("--reset", choices=sorted(KEYWORDS), metavar="Q01", help="Back up state and reset one semantic question")
    args = p.parse_args()
    if not WORK.is_file():
        raise FileNotFoundError(WORK)
    qfields, questions = read_csv(WORK)
    dfields, decisions = read_csv(DECISIONS) if DECISIONS.exists() else (["query_id", "drug_id", "decision", "reviewed_at_utc"], [])
    if getattr(args, "inspect", None):
        inspect(args.inspect, questions, decisions)
    else:
        reset(args.reset, questions, qfields, decisions, dfields)

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, csv.Error, json.JSONDecodeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
