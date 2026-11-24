from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'benchmark'
WORK = BENCH / 'gold_review_working.csv'
DECISIONS = BENCH / 'semantic_review_decisions.csv'
PROGRESS = BENCH / 'gold_review_progress.json'
RAW = ROOT / 'data/raw/openfda_pilot.json'
QID = 'Q06'

EXPECTED = {
    'DRUG:15a34df5-e48f-4570-9232-80e4093c4624',  # Butalbital/acetaminophen/caffeine/codeine
    'DRUG:95a33c9b-79a6-47c7-8433-fc217950b88f',  # Butalbital/aspirin/caffeine/codeine
    'DRUG:23899405-007b-48d9-82a9-a530b8e90784',  # Fluoxetine
    'DRUG:4da914d0-629e-4766-b57f-6119fa8283cf',  # Sertraline
}
EXTRA = {
    'DRUG:062800b1-790a-41c3-a8be-94143d2c7fb6':
        '14 days refers to pausing omeprazole before Chromogranin A testing, not MAOIs.',
    'DRUG:0696b10c-972b-9dcf-e063-6294a90a1034':
        '14 days refers to pausing pantoprazole before Chromogranin A testing, not MAOIs.',
    'DRUG:1806dadd-9ebb-46ee-9b86-f153e6db3b48':
        'MAO inhibitors are mentioned among interacting agents, without a 14-day restriction.',
    'DRUG:1eaa7790-f1a1-4f51-b10a-cbbaf033f684':
        '10-14 days refers to CABG surgery outcomes, not MAOI coadministration.',
}
# Explicit text that connects the 14-day window TO use of MAOIs.
EVIDENCE = {
    'DRUG:15a34df5-e48f-4570-9232-80e4093c4624': re.compile(
        r'Concurrent use of monoamine oxidase inhibitors\s*\(MAOIs\)\s*or use of MAOIs within the last 14 days', re.I),
    'DRUG:95a33c9b-79a6-47c7-8433-fc217950b88f': re.compile(
        r'Concurrent use of monoamine oxidase inhibitors\s*\(MAOIs\)\s*or use of MAOIs within the last 14 days', re.I),
    'DRUG:23899405-007b-48d9-82a9-a530b8e90784': re.compile(
        r'(?:use of fluoxetine within 14 days of stopping an MAOI)', re.I),
    'DRUG:4da914d0-629e-4766-b57f-6119fa8283cf': re.compile(
        r'Concomitant use of monoamine oxidase inhibitors\s*\(MAOIs\),\s*or use within 14 days of stopping MAOIs', re.I),
}
MAOI = re.compile(r'(?:\bMAOIs?\b|monoamine\s+oxidase)', re.I)
FOURTEEN = re.compile(r'\b14\s+days\b|\bfourteen days\b', re.I)
INDEXED_SECTIONS = ('description', 'indications_and_usage', 'contraindications',
                    'warnings_and_cautions', 'drug_interactions', 'adverse_reactions', 'boxed_warning')


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def atomic_csv(path, fields, records):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    tmp.replace(path)


def load_validate():
    raw = json.loads(RAW.read_text(encoding='utf-8-sig'))
    items = raw.get('results', [])
    if len(items) != 25:
        raise ValueError('Expected exactly 25 frozen openFDA source labels')
    labels = {}
    both_terms_in_section = set()
    for entry in items:
        did = 'DRUG:' + str(entry['set_id'])
        if did in labels:
            raise ValueError('Duplicate source ID: ' + did)
        indexed = {sec: ' '.join(map(str, entry.get(sec, []))) for sec in INDEXED_SECTIONS}
        if any(MAOI.search(t) and FOURTEEN.search(t) for t in indexed.values()):
            both_terms_in_section.add(did)
        labels[did] = {
            'name': '; '.join(entry.get('openfda', {}).get('generic_name', [])) or did,
            'contraindications': indexed['contraindications'],
            'indexed': indexed,
        }
    if set(EVIDENCE) != EXPECTED or set(EXTRA) & EXPECTED:
        raise ValueError('Internal expected/source ID mismatch')
    if both_terms_in_section != EXPECTED:
        raise ValueError('Source revisions require manual review: records with BOTH MAOI and 14-day mentions in an indexed section are: ' + repr(sorted(both_terms_in_section)))
    for did, pattern in EVIDENCE.items():
        if did not in labels or not pattern.search(labels[did]['contraindications']):
            raise ValueError('Expected direct Contraindications evidence missing: ' + did)

    qfields, questions = read_csv(WORK)
    if len(questions) != 30 or len({q['query_id'] for q in questions}) != 30:
        raise ValueError('Expected 30 unique benchmark questions')
    question = next((q for q in questions if q['query_id'] == QID), None)
    if not question or question['review_status'] != 'approved' or question['category'] != 'semantic':
        raise ValueError('Q06 must be a currently approved semantic question')
    wording = question['query_en'].lower()
    if 'monoamine oxidase inhibitors' not in wording or 'fourteen-day' not in wording:
        raise ValueError('Q06 wording changed; automatic correction refused')
    dfields, decisions = read_csv(DECISIONS)
    subset = [d for d in decisions if d.get('query_id') == QID]
    if len(subset) != 25 or {d['drug_id'] for d in subset} != set(labels):
        raise ValueError('Q06 must have exactly 25 distinct judgments corresponding to raw labels')
    if any(d.get('decision') not in ('yes','no') for d in subset):
        raise ValueError('Invalid Q06 judgment in decisions CSV')
    old_yes = {d['drug_id'] for d in subset if d['decision'] == 'yes'}
    gold = set(filter(None, question['gold_drug_ids'].split('|')))
    if gold != old_yes:
        raise ValueError('Q06 gold and judgment sets differ; investigate manually')
    if old_yes != EXPECTED and (old_yes - EXPECTED != set(EXTRA) or EXPECTED - old_yes):
        raise ValueError('Unexpected Q06 yes pattern; do not blindly overwrite annotations: ' + repr(sorted(old_yes)))
    return qfields, questions, dfields, decisions, labels, old_yes


def audit(labels, old_yes):
    print('Q06: documented drug restriction involving MAOIs AND a 14-day window')
    print('Sources: 25 frozen openFDA labels; semantic relevance in seven indexed sections.')
    print(f'Current YES: {len(old_yes)}; direct source-supported YES: {len(EXPECTED)}\n')
    for did in sorted(old_yes):
        label = labels[did]
        if did in EXPECTED:
            match = EVIDENCE[did].search(label['contraindications'])
            print('  KEEP y:', label['name'], '|', did)
            print('    Source:', match.group(0))
        else:
            print('  CHANGE TO n:', label['name'], '|', did)
            print('    Reason:', EXTRA[did])
    print(f'\nProposed: {len(old_yes-EXPECTED)} y -> n, {len(EXPECTED-old_yes)} n -> y')
    print('CAUTION: This is relevance to the selected label snapshot, not a clinical safety assessment.')


def apply(qfields, questions, dfields, decisions, old_yes):
    if old_yes == EXPECTED:
        print('Already correct; no changes required.')
        return
    if input('\nType CORRECT Q06 to confirm: ').strip() != 'CORRECT Q06':
        print('Cancelled; nothing was edited.')
        return
    backup = BENCH / 'backups' / ('q06_fix_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True, exist_ok=False)
    for file in (WORK, DECISIONS, PROGRESS):
        if file.exists():
            shutil.copy2(file, backup / file.name)
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for d in decisions:
        if d['query_id'] == QID and d['drug_id'] in EXTRA:
            d['decision'] = 'no'
            d['reviewed_at_utc'] = now
    qrow = next(q for q in questions if q['query_id'] == QID)
    qrow['gold_drug_ids'] = '|'.join(sorted(EXPECTED))
    qrow['review_status'] = 'approved'
    qrow['reviewer_note'] = (
        'Q06 audited against 25 frozen openFDA SPL snapshots. MAOI-related 14-day restriction '
        'supported by explicit Contraindications text in 4 labels. Other 14-day periods '
        '(chromogranin A / CABG) and MAOI references without 14-day interval are excluded. '
        'Source relevance only; no clinical absence-of-risk inference.')
    qrow['reviewed_at_utc'] = now
    atomic_csv(DECISIONS, dfields, decisions)
    atomic_csv(WORK, qfields, questions)
    statuses = Counter((r['category'], r['review_status']) for r in questions)
    info = {
        'total_questions': len(questions),
        'approved': sum(r['review_status'] == 'approved' for r in questions),
        'rejected': sum(r['review_status'] == 'rejected' for r in questions),
        'pending': sum(r['review_status'] == 'pending' for r in questions),
        'semantic_questions_still_require_full_corpus_review': [r['query_id'] for r in questions if r['category']=='semantic' and r['review_status']=='pending'],
        'counts_by_category_and_status': [{'category':cat,'status':status,'count':n} for (cat,status),n in sorted(statuses.items())],
        'warning': 'Source-snapshot relevance judgments only; no medical safety inferences from negatives.',
    }
    PROGRESS.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\nCorrected Q06: 25/25 judged; relevant=4; irrelevant=21')
    print('Backups:', backup.relative_to(ROOT))
    print(f'Benchmark questions: approved={info["approved"]}, pending={info["pending"]}, rejected={info["rejected"]}')
    print('Verify: py scripts/11_review_semantic_gold.py --status')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    qfields, questions, dfields, decisions, labels, old_yes = load_validate()
    audit(labels, old_yes)
    if args.apply:
        apply(qfields, questions, dfields, decisions, old_yes)


if __name__ == '__main__':
    main()
