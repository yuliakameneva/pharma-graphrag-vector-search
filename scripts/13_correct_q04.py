from __future__ import annotations
import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'benchmark'
WORK = BENCH / 'gold_review_working.csv'
DECISIONS = BENCH / 'semantic_review_decisions.csv'
PROGRESS = BENCH / 'gold_review_progress.json'
RAW = ROOT / 'data/raw/openfda_pilot.json'
QID = 'Q04'
PHRASE = re.compile(r'\bbacterial\s+endocarditis\b', re.IGNORECASE)


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding='utf-8-sig', newline='') as f:
        rdr = csv.DictReader(f)
        return rdr.fieldnames, list(rdr)


def write_atomic(path, columns, records):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    tmp.replace(path)


def read_and_validate():
    obj = json.loads(RAW.read_text(encoding='utf-8-sig'))
    original = obj.get('results', [])
    if len(original) != 25:
        raise ValueError('Expected exactly 25 original openFDA labels')
    label_by_id = {}
    for rec in original:
        did = 'DRUG:' + str(rec['set_id'])
        if did in label_by_id:
            raise ValueError('Duplicate drug in openFDA source')
        name = ', '.join(rec.get('openfda', {}).get('generic_name', [])) or did
        contraindications = ' '.join(str(x) for x in rec.get('contraindications', []))
        match = PHRASE.search(contraindications)
        snippet = (contraindications[max(match.start()-95,0):match.end()+150] if match else '')
        label_by_id[did] = (name, bool(match), ' '.join(snippet.split()))
    q_fields, questions = read_csv(WORK)
    if len(questions) != 30 or len(set(r['query_id'] for r in questions)) != 30:
        raise ValueError('Expected 30 unique benchmark questions')
    matching = [r for r in questions if r['query_id'] == QID]
    if len(matching) != 1 or matching[0]['category'] != 'semantic':
        raise ValueError('Missing or invalid Q04 benchmark question')
    q = matching[0]
    if q['review_status'] != 'approved':
        raise ValueError('Q04 must already be approved; use existing 11_review_semantic_gold.py first')
    d_fields, decisions = read_csv(DECISIONS)
    found = [r for r in decisions if r['query_id'] == QID]
    if len(found) != 25 or len(set(r['drug_id'] for r in found)) != 25:
        raise ValueError('Q04 must have 25 unique source judgments before correction')
    if any(r['drug_id'] not in label_by_id or r['decision'] not in ('yes','no') for r in found):
        raise ValueError('Q04 contains malformed judgments')
    gold_now = set(filter(None, q['gold_drug_ids'].split('|')))
    yes_now = {r['drug_id'] for r in found if r['decision'] == 'yes'}
    if gold_now != yes_now:
        raise ValueError('Q04 gold_drug_ids does not match saved yes decisions; manual audit required')
    gold_source = {did for did, (_, rel, _) in label_by_id.items() if rel}
    # This is the locked, source-reviewed evidence for this EXACT question.
    if gold_source != {'DRUG:724b0061-f42a-4008-a078-09c800ee9785'}:
        raise ValueError('Unexpected source matches. The source may have changed; do not auto-edit Q04.')
    return q_fields, questions, d_fields, decisions, label_by_id, yes_now, gold_source


def show(label_by_id, yes_now, gold_source):
    print('Q04: Which labels explicitly list bacterial endocarditis as a contraindication?')
    print(f'Original source: {len(label_by_id)} openFDA labels; current YES={len(yes_now)}; supported YES={len(gold_source)}')
    print('\nExisting YES decisions:')
    for did in sorted(yes_now):
        name, relevant, passage = label_by_id[did]
        print(f'  {"KEEP y" if relevant else "CHANGE TO n"}: {name} | {did}')
        print('    Contraindication source:', passage if passage else 'No exact bacterial endocarditis entry in contraindications')
    print('\nSource-supported YES labels:')
    for did in sorted(gold_source):
        name, _, passage = label_by_id[did]
        print(f'  {name} | {did}')
        print('   ', passage)
    if yes_now == gold_source:
        print('\nQ04 already matches the source; nothing needs changing.')
    else:
        print(f'\nProposed corrections: {len(yes_now - gold_source)} yes -> no, {len(gold_source - yes_now)} no -> yes')
    print('This is a fixed-snapshot document relevance judgment; it does NOT establish clinical safety.')


def apply_changes(qfields, qs, dfields, ds, labels, old_yes, source_yes):
    if old_yes == source_yes:
        print('No changes needed.')
        return
    print('\nTo apply only the Q04 correction and create backups, type: CORRECT Q04')
    if input('Confirmation: ').strip() != 'CORRECT Q04':
        print('Cancelled; no changes applied.')
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest = BENCH / 'backups' / f'q04_fix_{stamp}'
    dest.mkdir(parents=True, exist_ok=False)
    for path in (WORK, DECISIONS, PROGRESS):
        if path.exists():
            shutil.copy2(path, dest / path.name)
    for record in ds:
        if record['query_id'] == QID:
            record['decision'] = 'yes' if record['drug_id'] in source_yes else 'no'
            if record['drug_id'] in old_yes.symmetric_difference(source_yes):
                record['reviewed_at_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    q = next(r for r in qs if r['query_id'] == QID)
    q['gold_drug_ids'] = '|'.join(sorted(source_yes))
    q['review_status'] = 'approved'
    q['reviewer_note'] = ('Q04 corrected against all 25 locked openFDA labels: explicit bacterial endocarditis '
                          'entry in contraindications section only. Other semantic and Q09-Q30 labels unchanged. '
                          'Negative source judgments do not establish clinical safety.')
    q['reviewed_at_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    write_atomic(DECISIONS, dfields, ds)
    write_atomic(WORK, qfields, qs)
    counts = Counter((r['category'],r['review_status']) for r in qs)
    progress = {
      'total_questions':len(qs),
      'approved':sum(r['review_status']=='approved' for r in qs),
      'rejected':sum(r['review_status']=='rejected' for r in qs),
      'pending':sum(r['review_status']=='pending' for r in qs),
      'semantic_questions_still_require_full_corpus_review':[r['query_id'] for r in qs if r['category']=='semantic' and r['review_status']=='pending'],
      'counts_by_category_and_status':[{'category':c,'status':s,'count':n} for (c,s),n in sorted(counts.items())],
      'warning':'Source-snapshot relevance decisions only, not external medical adjudication or medical-safety evidence.',
    }
    PROGRESS.write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\nSuccess; backup:',dest.relative_to(ROOT))
    print('Q04 updated: judged 25/25, relevant=1, irrelevant=24')
    print(f"Benchmark approved={progress['approved']}, pending={progress['pending']}, rejected={progress['rejected']}")
    print('Next: py scripts/11_review_semantic_gold.py --status')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check', action='store_true')
    g.add_argument('--apply', action='store_true')
    args = p.parse_args()
    data = read_and_validate()
    show(data[4], data[5], data[6])
    if args.apply:
        apply_changes(*data)

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, csv.Error, json.JSONDecodeError) as e:
        print('ERROR:',e,file=sys.stderr)
        sys.exit(1)
