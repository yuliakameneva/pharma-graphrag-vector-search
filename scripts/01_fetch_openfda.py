import argparse
import datetime as dt
import json
import os
import pathlib
import re
import time
from urllib.parse import urlencode

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = "https://api.fda.gov/drug/label.json"
REQUIRED = ("indications_and_usage", "contraindications", "drug_interactions")
TEXT_FIELDS = REQUIRED + ("description", "adverse_reactions", "warnings_and_cautions", "boxed_warning")


def qualified(label):
    meta = label.get("openfda") or {}
    if not isinstance(meta, dict):
        return False
    ptype = " ".join(meta.get("product_type") or []).upper()
    if "HUMAN" not in ptype or not label.get("set_id") or not label.get("id"):
        return False
    if not meta.get("substance_name") or not meta.get("generic_name"):
        return False
    return all(any(str(v).strip() for v in (label.get(f) or [])) for f in REQUIRED)


def quality_score(record, target):
    m = record.get("openfda") or {}
    gen = " ".join(m.get("generic_name") or []).casefold()
    coverage = sum(bool(record.get(k)) for k in TEXT_FIELDS)
    # Prefer a one-ingredient exact-ish name when possible; do not assume all are single ingredient.
    exact = int(target.casefold() in re.findall(r"[a-z]+", gen))
    cap = min(30000, sum(len(str(x)) for f in TEXT_FIELDS for x in (record.get(f) or [])))
    return (exact * 25 + coverage * 6 + cap / 1000.0,
            str(record.get("effective_time") or ""),
            str(record.get("id") or ""))


def fetch(session, query, limit, api_key="", retries=4):
    params = {"search": query, "limit": limit}
    if api_key:
        params["api_key"] = api_key
    safe_params = {k: v for k, v in params.items() if k != "api_key"}
    request_url = API + "?" + urlencode(safe_params)
    for attempt in range(retries):
        try:
            response = session.get(API, params=params, timeout=(10, 50))
            if response.status_code == 404:
                return [], request_url  # No matching documents
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < retries - 1:
                    time.sleep(min(16, 2 ** attempt))
                    continue
            response.raise_for_status()
            return response.json().get("results", []), request_url
        except (requests.RequestException, ValueError) as ex:
            if attempt == retries - 1:
                print(f"  Network/API failure: {type(ex).__name__}: {ex}")
                return [], request_url
            time.sleep(min(16, 2 ** attempt))
    return [], request_url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-labels", type=int, default=20)
    ap.add_argument("--per-drug", type=int, default=15)
    ap.add_argument("--seeds", type=pathlib.Path, default=ROOT / "seeds.txt")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "data" / "raw" / "openfda_pilot.json")
    args = ap.parse_args()
    if not 1 <= args.max_labels <= 250:
        ap.error("max-labels must be 1..250")
    if not 1 <= args.per_drug <= 100:
        ap.error("per-drug must be 1..100")
    seeds = [s.strip() for s in args.seeds.read_text(encoding="utf-8").splitlines()
             if s.strip() and not s.lstrip().startswith("#")]
    session = requests.Session()
    session.headers.update({"User-Agent": "student-graphrag-pilot/0.1 (research; openFDA public API)",
                            "Accept": "application/json"})
    api_key = os.getenv("OPENFDA_API_KEY", "").strip()
    chosen, checked, used_ids = [], [], set()
    for target in seeds:
        if len(chosen) >= args.max_labels:
            break
        # This expression is constructed using the documented openFDA query language.
        expression = (f'openfda.generic_name:"{target}" AND '
                      '_exists_:indications_and_usage AND '
                      '_exists_:contraindications AND '
                      '_exists_:drug_interactions')
        results, url = fetch(session, expression, args.per_drug, api_key=api_key)
        valid = [r for r in results if qualified(r) and r["set_id"] not in used_ids]
        # Some historical records are not indexed consistently. Fall back to
        # a broad search, BUT keep the exact same strict local validation.
        if not valid:
            broad_results, broad_url = fetch(
                session, f'openfda.generic_name:"{target}"', args.per_drug, api_key=api_key)
            results = broad_results
            url = broad_url
            valid = [r for r in results if qualified(r) and r["set_id"] not in used_ids]
        valid.sort(key=lambda r: quality_score(r, target), reverse=True)
        if valid:
            record = valid[0]
            used_ids.add(record["set_id"])
            chosen.append(record)
            print(f"[{len(chosen):02d}/{args.max_labels}] {target}: OK / "
                  f"{record['set_id']} / version {record.get('version', '?')}")
        else:
            print(f"[--/{args.max_labels}] {target}: no sufficiently complete record")
        checked.append({"target": target, "results_examined": len(results),
                        "valid_candidates": len(valid), "query_url": url,
                        "selected_set_id": valid[0]["set_id"] if valid else None})
        time.sleep(.20)
    payload = {
        "provenance": {"source": "openFDA Drug Labeling (SPL)", "endpoint": API,
                       "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                       "selection": "1 information-rich label per seed; deterministic best score",
                       "selection_queries": checked, "actual_label_count": len(chosen),
                       "requested_label_count": args.max_labels},
        "results": chosen
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(chosen)} authentic records to {args.out}")
    if len(chosen) < args.max_labels:
        print("Some searches had no suitable records. Expand seeds.txt or per-drug and retry.")
    if not chosen:
        raise SystemExit("No real data was fetched; check Internet/API connectivity. No fabricated data written.")


if __name__ == "__main__":
    main()
