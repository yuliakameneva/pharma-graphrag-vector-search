from __future__ import annotations

import argparse
from collections import Counter
import csv
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
QID = 'Q05'

# Exact known source supports. Must ALSO be checked against raw section text.
EXPECTED = {
    'DRUG:2794b60d-d09b-4115-9ff2-07ff15524e78',  # Naproxen Sodium
    'DRUG:1eaa7790-f1a1-4f51-b10a-cbbaf033f684',  # Ibuprofen
    'DRUG:95a33c9b-79a6-47c7-8433-fc217950b88f',  # Butalbital/Aspirin/Caffeine/Codeine
}
ASPIRIN_NSAID = re.compile(r'\b(?:aspirin|NSAIDs?|nonsteroidal anti-inflammatory drugs?)\b', re.I)
EVIDENCE = {
    'DRUG:2794b60d-d09b-4115-9ff2-07ff15524e78': re.compile(
        r'History of asthma, urticaria, or other allergic-type reactions after taking aspirin or other NSAIDs', re.I),
    'DRUG:1eaa7790-f1a1-4f51-b10a-cbbaf033f684': re.compile(
        r'History of asthma, urticaria, or other allergic-type reactions after taking aspirin or other NSAIDs', re.I),
    'DRUG:95a33c9b-79a6-47c7-8433-fc217950b88f': re.compile(
        r'Known allergy to (?:nonsteroidal anti-inflammatory drugs \(NSAIDs\)|NSAIDs)', re.I),
}


def read_csv(path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        return reader.fieldnames, list(reader)


def atomic_csv(path: Path, fields, records):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    tmp.replace(path)


def load_validate():
    obj = json.loads(RAW.read_text(encoding='utf-8-sig'))
    entries = obj.get('results')
    if not isinstance(entries, list) or len(entries) != 25:
        raise ValueError('Expected exactly 25 locked openFDA source labels')
    labels = {}
    for rec in entries:
        did = 'DRUG:' + str(rec['set_id'])
        if did in labels:
            raise ValueError('Duplicate source drug id')
        txt = ' '.join(str(s) for s in rec.get('contraindications', []))
        name = ', '.join(rec.get('openfda', {}).get('generic_name', [])) or did
        labels[did] = {'name': name, 'contraindications': txt}

    if set(EVIDENCE) != EXPECTED:
        raise ValueError('Internal expected IDs mismatch')
    # Gate source revision; no silent acceptance of changed source sets.
    all_named = {did for did, x in labels.items() if ASPIRIN_NSAID.search(x['contraindications'])}
    if all_named != EXPECTED:
        raise ValueError('Source contraindication sections contain unexpected aspirin/NSAID mentions. Manual review required. IDs: ' + repr(sorted(all_named)))
    for did, pattern in EVIDENCE.items():
        if did not in labels or not pattern.search(labels[did]['contraindications']):
            raise ValueError('Missing expected explicit source evidence: ' + did)

    q_fields, questions = read_csv(WORK)
    if len(questions) != 30 or len({q['query_id'] for q in questions}) != 30:
        raise ValueError('Expected exactly 30 unique benchmark questions')
    qrow = next((q for q in questions if q['query_id'] == QID), None)
    if qrow is None or qrow['category'] != 'semantic' or qrow['review_status'] != 'approved':
        raise ValueError('Q05 must be a currently approved semantic question')
    if 'aspirin or other nsaids' not in qrow['query_en'].lower():
        raise ValueError('Q05 question text changed; cannot automatically correct')

    d_fields, decisions = read_csv(DECISIONS)
    judged = [d for d in decisions if d.get('query_id') == QID]
    if len(judged) != 25 or {d['drug_id'] for d in judged} != set(labels):
        raise ValueError('Expected a complete set of 25 unique Q05 judgments')
    if any(d.get('decision') not in ('yes','no') for d in judged):
        raise ValueError('Malformed Q05 judgment')
    old_yes = {d['drug_id'] for d in judged if d['decision'] == 'yes'}
    stored_gold = set(filter(None, qrow['gold_drug_ids'].split('|')))
    if old_yes != stored_gold:
        raise ValueError('Current gold differs from decisions; manual investigation required')
    return q_fields, questions, d_fields, decisions, labels, old_yes


def show_audit(labels, old_yes):
    print('Q05: explicit previous allergy to aspirin or other NSAIDs is a CONTRAINDICATION')
    print('Corpus: 25 frozen openFDA drug labels; only Contraindications section counts for this wording.')
    print(f'Current YES: {len(old_yes)}; explicitly supported YES: {len(EXPECTED)}')
    print('\nCurrently marked YES:')
    for did in sorted(old_yes):
        name = labels[did]['name']
        if did in EXPECTED:
            m = EVIDENCE[did].search(labels[did]['contraindications'])
            print('  KEEP y:', name, '|',did)
            print('    Source:',m.group(0))
        else:
            print('  CHANGE TO n:',name,'|',did)
            print('    No aspirin/NSAID ALLERGY contraindication in source; other warnings/hypersensitivity do not qualify.')
    if old_yes == EXPECTED:
        print('\nAlready correct. Nothing to change.')
    else:
        print(f'\nProposed: {len(old_yes-EXPECTED)} y -> n; {len(EXPECTED-old_yes)} n -> y')
    print('No absence-of-risk conclusions follow from this document-relevance classification.')


def apply(q_fields, questions, d_fields, decisions, old_yes):
    if old_yes == EXPECTED:
        print('No changes needed.')
        return
    if old_yes-EXPECTED != {
        'DRUG:10db92f9-2300-4a80-836b-673e1ae91610',
        'DRUG:23899405-007b-48d9-82a9-a530b8e90784',
        'DRUG:4cd07a3c-9673-4aa0-b76a-d79df2399ee1',
    } or EXPECTED-old_yes:
        raise ValueError('Unexpected Q05 decisions; use manual review rather than automatic correction.')

    print('\nWill correct ONLY 3 extra Q05 yes -> no and preserve Q01-Q04, Q06-Q30.')
    if input('Type CORRECT Q05 to confirm: ').strip() != 'CORRECT Q05':
        print('Cancelled. No edits.')
        return
    backup_dir = BENCH / 'backups' / ('q05_fix_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup_dir.mkdir(parents=True, exist_ok=False)
    for source in (WORK, DECISIONS, PROGRESS):
        if source.exists():
            shutil.copy2(source, backup_dir / source.name)
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for dec in decisions:
        if dec['query_id'] == QID and dec['drug_id'] in old_yes-EXPECTED:
            dec['decision'] = 'no'
            dec['reviewed_at_utc'] = now
    row = next(q for q in questions if q['query_id'] == QID)
    row['gold_drug_ids'] = '|'.join(sorted(EXPECTED))
    row['review_status'] = 'approved'
    row['reviewer_note'] = ('Q05 corrected after review of the 25 frozen openFDA label contraindication sections: '
        'aspirin/NSAID ALLERGY contraindication only; increased bleeding risk and hypersensitivity to '
        'other medications are not matches. Snapshot text relevance, not clinical safety evaluation.')
    row['reviewed_at_utc'] = now
    atomic_csv(DECISIONS, d_fields, decisions)
    atomic_csv(WORK, q_fields, questions)
    counts = Counter((x['category'],x['review_status']) for x in questions)
    info = {
        'total_questions': len(questions),
        'approved': sum(x['review_status']=='approved' for x in questions),
        'rejected': sum(x['review_status']=='rejected' for x in questions),
        'pending': sum(x['review_status']=='pending' for x in questions),
        'semantic_questions_still_require_full_corpus_review': [x['query_id'] for x in questions if x['category']=='semantic' and x['review_status']=='pending'],
        'counts_by_category_and_status': [{'category':c,'status':s,'count':n} for (c,s),n in sorted(counts.items())],
        'warning': 'Source snapshot relevance judgments only; negative classifications do not establish medical safety.',
    }
    PROGRESS.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Corrected Q05: 25/25 judged; relevant=3; irrelevant=22.')
    print('Backups saved to:',backup_dir.relative_to(ROOT))
    print('Benchmark approved=',info['approved'],'pending=',info['pending'],'rejected=',info['rejected'])
    print('Check: py scripts/11_review_semantic_gold.py --status')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    ops = parser.add_mutually_exclusive_group(required=True)
    ops.add_argument('--check',action='store_true')
    ops.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    qfields, qs, dfields, ds, labels, old_yes = load_validate()
    show_audit(labels,old_yes)
    if args.apply:
        apply(qfields,qs,dfields,ds,old_yes)


if __name__=='__main__':
    try:
        main()
    except (OSError,ValueError,KeyError,csv.Error,json.JSONDecodeError) as err:
        print('ERROR:',err,file=sys.stderr)
        sys.exit(1)
