"""Audit and, after explicit confirmation, correct Q07/Q08 semantic relevance judgments.

Run in Windows PowerShell from pharma_graphrag_pilot:
    py scripts/16_audit_correct_q07_q08.py --check
    py scripts/16_audit_correct_q07_q08.py --apply

This tool uses the FROZEN 25-label openFDA snapshot in data/raw/openfda_pilot.json
and checks exact source evidence in the indexed drug_interactions section.
It corrects only Q07 and Q08 in benchmark/semantic_review_decisions.csv and
benchmark/gold_review_working.csv; leaves Q01-Q06 and Q09-Q30 untouched;
backups before writing. Does not modify Neo4j, Qdrant or original data.
This is source-relevance annotation, not clinical safety evaluation.
"""
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
RAW = ROOT / 'data' / 'raw' / 'openfda_pilot.json'
WORK = BENCH / 'gold_review_working.csv'
DECISIONS = BENCH / 'semantic_review_decisions.csv'
PROGRESS = BENCH / 'gold_review_progress.json'
AUDIT = BENCH / 'q07_q08_evidence_audit.csv'
EXPECTED = {
    'Q07': {
        'DRUG:2794b60d-d09b-4115-9ff2-07ff15524e78': r'interfered with the antiplatelet effect of low-dose immediate-release aspirin',
        'DRUG:1eaa7790-f1a1-4f51-b10a-cbbaf033f684': r'interference with the antiplatelet activity of aspirin',
    },
    'Q08': {
        'DRUG:724b0061-f42a-4008-a078-09c800ee9785': r'Inhibitors of CYP2C9, 1A2, and/or 3A4 have the potential to increase the effect \(increase INR\) of warfarin',
    },
}
QUESTIONS = {
    'Q07': ['antiplatelet effect', 'aspirin'],
    'Q08': ['inr', 'enzyme inhibition'],
}


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def atomic_csv(path, headers, rows):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def load_and_validate():
    corpus = json.loads(RAW.read_text(encoding='utf-8-sig'))
    results = corpus['results']
    if len(results) != 25:
        raise ValueError('Expected frozen corpus of exactly 25 openFDA labels')
    labels = {}
    for item in results:
        did = 'DRUG:' + str(item['set_id'])
        if did in labels:
            raise ValueError('Duplicate drug id in raw snapshot')
        labels[did] = {'name': ', '.join(item.get('openfda', {}).get('generic_name', [])),
                       'text': ' '.join(map(str,item.get('drug_interactions',[])))}
    for q, supports in EXPECTED.items():
        for did, pattern in supports.items():
            if did not in labels or not re.search(pattern, labels[did]['text'], re.I):
                raise ValueError(f'Expected source evidence not found for {q}/{did}; inspect raw label')
    # Require standard snapshot drug IDs, protecting against accidental use on another dataset
    snapshot_ids = {
        '2794b60d-d09b-4115-9ff2-07ff15524e78','1eaa7790-f1a1-4f51-b10a-cbbaf033f684',
        '724b0061-f42a-4008-a078-09c800ee9785','23899405-007b-48d9-82a9-a530b8e90784',
        '4da914d0-629e-4766-b57f-6119fa8283cf'
    }
    if not {'DRUG:'+id for id in snapshot_ids}.issubset(labels):
        raise ValueError('Unexpected snapshot label IDs')
    q_headers, qs = read_csv(WORK)
    d_headers, ds = read_csv(DECISIONS)
    if len(qs)!=30 or len({r['query_id'] for r in qs})!=30:
        raise ValueError('Expected 30 unique benchmark questions')
    if any(r.get('review_status') != 'approved' for r in qs):
        raise ValueError('All 30 questions must be approved first')
    byq = {r['query_id']:r for r in qs}
    for q in EXPECTED:
        row = byq[q]
        if row['category']!='semantic' or not all(token in row['query_en'].lower() for token in QUESTIONS[q]):
            raise ValueError(f'Question {q} changed from expected meaning. Manual review required.')
    for q in EXPECTED:
        sub=[d for d in ds if d.get('query_id')==q]
        if len(sub)!=25 or {d['drug_id'] for d in sub} != set(labels):
            raise ValueError(f'{q} needs 25 unique corpus judgments')
        if any(d['decision'] not in ('yes','no') for d in sub):
            raise ValueError(f'Invalid {q} judgment')
        current_yes = {d['drug_id'] for d in sub if d['decision']=='yes'}
        stored = set(filter(None,byq[q]['gold_drug_ids'].split('|')))
        if current_yes != stored:
            raise ValueError(f'{q} judgments differ from approved gold. Investigate manually.')
    # If any other question has insufficient judgments or weird duplicate decisions, stop.
    if len({(d['query_id'], d['drug_id']) for d in ds}) != len(ds):
        raise ValueError('Duplicate relevance decisions')
    return q_headers,qs,d_headers,ds,labels,byq


def audit(ds,labels):
    rows=[]
    for q in EXPECTED:
        print('\n'+q+': '+('interference with low-dose aspirin antiplatelet effect' if q=='Q07' else 'INR increase specifically due to CYP enzyme inhibition'))
        byid={d['drug_id']:d for d in ds if d['query_id']==q}
        correct=set(EXPECTED[q]); selected={did for did,d in byid.items() if d['decision']=='yes'}
        print('  Current YES:',len(selected),'| Supported YES:',len(correct))
        print('  Changes:',len(selected-correct),'yes->no,',len(correct-selected),'no->yes')
        for did in sorted(labels):
            old=byid[did]['decision']; expected='yes' if did in correct else 'no'
            if did in correct:
                excerpt=re.search(EXPECTED[q][did],labels[did]['text'],re.I).group(0)
            else:
                excerpt='No direct evidence of THIS exact proposition in indexed label sections; related mentions do not qualify.'
            rows.append({'query_id':q,'drug_id':did,'drug_name':labels[did]['name'],
                         'old_decision':old,'evidence_supported_decision':expected,
                         'action':'KEEP' if old==expected else 'CORRECT',
                         'source_evidence_or_rationale':excerpt})
            if old!=expected:
                print('    CHANGE',old,'->',expected,labels[did]['name'],'|',did)
        print('  Expected positive labels:',', '.join(labels[did]['name'] for did in sorted(correct)))
    atomic_csv(AUDIT, list(rows[0]), rows)
    print('\nEvidence audit saved:',AUDIT.relative_to(ROOT))
    print('CAUTION: A negative judgment is NOT evidence that a medicine is safe.')
    return rows


def apply(q_headers,qs,d_headers,ds,labels,byq,audit_rows):
    changes=[r for r in audit_rows if r['action']=='CORRECT']
    if not changes:
        print('All Q07/Q08 judgments already match the audited corpus. No changes.')
        return
    if input('Type CORRECT Q07 Q08 to confirm (anything else cancels): ').strip() != 'CORRECT Q07 Q08':
        print('Cancelled; no benchmark gold files edited.')
        return
    backup=BENCH/'backups'/('q07_q08_fix_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True,exist_ok=False)
    for source in [WORK,DECISIONS,PROGRESS]:
        if source.exists(): shutil.copy2(source,backup/source.name)
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    before={q:dict(row) for q,row in byq.items() if q not in EXPECTED}
    for d in ds:
        q=d['query_id']
        if q in EXPECTED:
            decision='yes' if d['drug_id'] in EXPECTED[q] else 'no'
            if d['decision']!=decision:
                d['decision']=decision; d['reviewed_at_utc']=now
    for q,expected in EXPECTED.items():
        row=byq[q]
        row['gold_drug_ids']='|'.join(sorted(expected))
        row['review_status']='approved'
        row['reviewed_at_utc']=now
        row['reviewer_note']=('Q07/Q08 corrected against 25 frozen openFDA labels and direct drug_interactions evidence. '
                              'Related words (aspirin, antiplatelet, INR, CYP) alone do not satisfy query. '
                              'Document relevance only; not medical safety analysis.')
    if any(byq[q] != before[q] for q in before):
        raise ValueError('Safety violation: changes outside Q07/Q08')
    atomic_csv(DECISIONS,d_headers,ds)
    atomic_csv(WORK,q_headers,qs)
    counts=Counter((r['category'],r['review_status']) for r in qs)
    progress={'total_questions':len(qs),'approved':sum(r['review_status']=='approved' for r in qs),
              'rejected':sum(r['review_status']=='rejected' for r in qs),
              'pending':sum(r['review_status']=='pending' for r in qs),
              'semantic_questions_still_require_full_corpus_review':[],
              'counts_by_category_and_status':[
                  {'category':cat,'status':st,'count':n} for (cat,st),n in sorted(counts.items())],
              'warning':'Manual source-snapshot text relevance only, not medical or external gold adjudication.'}
    PROGRESS.write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Corrected {len(changes)} judgments across Q07/Q08.')
    print('Q07: 2 relevant, 23 irrelevant | Q08: 1 relevant, 24 irrelevant')
    print('Backups:',backup.relative_to(ROOT))
    print('Questions approved:',progress['approved'],'pending:',progress['pending'])
    print('Check: py scripts/11_review_semantic_gold.py --status')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--check',action='store_true')
    group.add_argument('--apply',action='store_true')
    args=p.parse_args()
    qh,qs,dh,ds,labels,byq=load_and_validate()
    audit_rows=audit(ds,labels)
    if args.apply: apply(qh,qs,dh,ds,labels,byq,audit_rows)

if __name__=='__main__':main()
