from __future__ import annotations
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'benchmark'
WORK = BENCH / 'gold_review_working.csv'
BACKUP = BENCH / 'gold_review_working_before_semantic.csv'
DECISIONS = BENCH / 'semantic_review_decisions.csv'
PROGRESS = BENCH / 'gold_review_progress.json'
RAW = ROOT / 'data' / 'raw' / 'openfda_pilot.json'
NODES = ROOT / 'data' / 'processed' / 'nodes.jsonl'
FULL_VIEW = BENCH / 'semantic_full_label_review.txt'

FIELDS = ['query_id', 'category', 'query_en', 'graph_filter_json',
          'proposed_drug_ids', 'proposed_evidence_ids', 'gold_drug_ids',
          'review_status', 'reviewer_note', 'reviewed_at_utc']
DECISION_FIELDS = ['query_id', 'drug_id', 'decision', 'reviewed_at_utc']
TEXT_FIELDS = ['description', 'indications_and_usage', 'contraindications',
               'drug_interactions', 'adverse_reactions', 'warnings_and_cautions',
               'boxed_warning']
# Hints are intentionally broad; unmatched passages can still be relevant.
HINTS = {
    'Q01': [r'malignant\s+hypertension', r'severe\s+hypertension'],
    'Q02': [r'coronary.{0,35}bypass', r'\bCABG\b', r'bypass\s+graft'],
    'Q03': [r'\bpimozide\b'],
    'Q04': [r'bacterial\s+endocarditis', r'\bendocarditis\b'],
    'Q05': [r'\burticaria\b', r'\bNSAIDs?\b', r'\baspirin\b', r'allergic.type', r'\basthma\b'],
    'Q06': [r'monoamine\s+oxidase', r'\bMAOI\b', r'\b14\s+days?\b', r'\blinezolid\b', r'methylene\s+blue'],
    'Q07': [r'antiplatelet', r'low.dose\s+aspirin', r'\baspirin\b'],
    'Q08': [r'\bINR\b', r'enzyme\s+inhibit', r'\bCYP(?:2C9|1A2|3A4)\b', r'inhibitors?'],
}

class Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'li', 'br', 'tr'):
            self.parts.append(' ')
    def value(self):
        return ' '.join(unescape(' '.join(self.parts)).split())


def clean(value):
    h = Cleaner()
    h.feed(str(value or ''))
    return h.value()


def csv_read(path):
    if not path.is_file():
        raise FileNotFoundError(f'Missing {path}')
    with path.open(encoding='utf-8-sig', newline='') as fp:
        return list(csv.DictReader(fp))


def atomic_csv(path, rows, fields):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as fp:
        writer = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def load_state():
    rows = csv_read(WORK)
    if len(rows) != 30 or len({r['query_id'] for r in rows}) != 30:
        raise ValueError('Expected 30 unique questions in benchmark/gold_review_working.csv')
    by_q = {r['query_id']: r for r in rows}
    for i in range(1, 9):
        r = by_q.get(f'Q{i:02d}')
        if not r or r['category'] != 'semantic':
            raise ValueError('Missing semantic Q01–Q08')
    for i in range(9, 31):
        r = by_q[f'Q{i:02d}']
        if r['review_status'] != 'approved' or not r['gold_drug_ids'].strip():
            raise ValueError(f'Existing {r["query_id"]} is not approved. Run 10_review_gold.py first.')

    raw = json.loads(RAW.read_text(encoding='utf-8-sig'))
    records = raw.get('results')
    if not isinstance(records, list):
        raise ValueError('Malformed raw openFDA results list')
    node_names = {}
    with NODES.open(encoding='utf-8-sig') as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get('kind') == 'Drug':
                node_names[obj['id']] = obj.get('properties', {}).get('generic_name', obj['id'])
    labels = {}
    for rec in records:
        drug_id = 'DRUG:' + str(rec.get('set_id', '')).strip()
        if drug_id == 'DRUG:' or drug_id in labels:
            raise ValueError('Missing/duplicate source set_id')
        if drug_id not in node_names:
            raise ValueError(f'Label not represented in Drug graph: {drug_id}')
        labels[drug_id] = {
            'name': node_names[drug_id], 'set_id': rec['set_id'],
            'revision_id': rec.get('id', ''),
            'sections': {
                f: clean(' '.join(map(str, rec.get(f, []))))
                for f in TEXT_FIELDS if rec.get(f)
            },
        }
    if len(labels) != 25 or len(node_names) != 25:
        raise ValueError(f'Expected exactly 25 records and 25 Drug nodes, got {len(labels)}, {len(node_names)}. Do not approve incomplete corpus.')
    previous = csv_read(DECISIONS) if DECISIONS.exists() else []
    decisions = {}
    for d in previous:
        key = (d['query_id'], d['drug_id'])
        if key in decisions or d['query_id'] not in HINTS or d['drug_id'] not in labels or d['decision'] not in {'yes', 'no'}:
            raise ValueError(f'Malformed/duplicate judgment: {d}')
        decisions[key] = {k: d[k] for k in DECISION_FIELDS}
    return rows, by_q, labels, decisions


def emit_progress(rows):
    counts = Counter((r['category'], r['review_status']) for r in rows)
    doc = {
        'total_questions': len(rows),
        'approved': sum(r['review_status'] == 'approved' for r in rows),
        'rejected': sum(r['review_status'] == 'rejected' for r in rows),
        'pending': sum(r['review_status'] == 'pending' for r in rows),
        'semantic_questions_still_require_full_corpus_review': [r['query_id'] for r in rows if r['category'] == 'semantic' and r['review_status'] == 'pending'],
        'counts_by_category_and_status': [{'category': c, 'status': s, 'count': n}
                                          for (c, s), n in sorted(counts.items())],
        'warning': 'Source-snapshot manual relevance judgments only; not external medical adjudication. No medical safety conclusions follow from negative judgments.',
    }
    PROGRESS.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')


def store_decisions(decisions):
    atomic_csv(DECISIONS, [decisions[key] for key in sorted(decisions)], DECISION_FIELDS)


def finish_question(question, rows, labels, decisions):
    qid = question['query_id']
    judged = {drug_id: decisions.get((qid, drug_id), {}).get('decision') for drug_id in labels}
    if any(v not in {'yes', 'no'} for v in judged.values()):
        return False
    yes = sorted(d for d, judgment in judged.items() if judgment == 'yes')
    if not yes:
        print(f'{qid}: no relevant labels selected. Keep pending; revise question or review judgments.')
        return False
    if question['review_status'] == 'approved':
        if question['gold_drug_ids'] != '|'.join(yes):
            raise ValueError(f'{qid} already approved with a different gold set; do not overwrite')
        return True
    if question['review_status'] != 'pending':
        raise ValueError(f'Unexpected review_status for {qid}')
    question['gold_drug_ids'] = '|'.join(yes)
    question['review_status'] = 'approved'
    question['reviewer_note'] = ('Manually judged seven indexed sections across all 25 openFDA label snapshots for text relevance. '
                               'No judgment implies clinical safety or full-label completeness; keyword hints were only navigation aids.')
    question['reviewed_at_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    atomic_csv(WORK, rows, FIELDS)
    emit_progress(rows)
    print(f'APPROVED {qid}: {len(yes)} distinct Drug IDs from 25 reviewed labels')
    return True


def sources_for(qid, label):
    patterns = [re.compile(x, re.IGNORECASE) for x in HINTS[qid]]
    matches = []
    for section, text in label['sections'].items():
        for pattern in patterns:
            for match in list(pattern.finditer(text))[:3]:
                start = max(0, match.start() - 175)
                end = min(len(text), match.end() + 220)
                snippet = ('...' if start else '') + text[start:end] + ('...' if end < len(text) else '')
                matches.append((section, snippet))
    # Each occurrence is just a navigation hint (NOT a relevance judgment).
    return matches


def full_label_file(qid, query, drug_id, label):
    lines = [f'QUESTION {qid}: {query}', '',
             f'DRUG {label["name"]}', f'DRUG_ID {drug_id}',
             f'SET_ID {label["set_id"]}', f'OPENFDA_REVISION {label["revision_id"]}',
             '', 'INDEXED SECTIONS FROM SOURCE SNAPSHOT ONLY — not the entire official label.']
    for section, content in label['sections'].items():
        lines += ['', '=' * 78, section.upper(), '=' * 78, content]
    FULL_VIEW.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Indexed source sections written to: {FULL_VIEW.relative_to(ROOT)}')
    print('Open it in VS Code and inspect all indexed sections. Then return here to judge.')


def review(qids, rows, by_q, labels, decisions):
    if not BACKUP.exists():
        shutil.copy2(WORK, BACKUP)
        print('Preserved backup:', BACKUP.relative_to(ROOT))
    all_ids = sorted(labels)
    for qid in qids:
        question = by_q[qid]
        if question['review_status'] == 'approved':
            print(f'{qid} already approved; not editing it.')
            continue
        # Rank only for reading convenience; every label MUST be reviewed.
        suggested = set(question['proposed_drug_ids'].split('|'))
        order = sorted(all_ids, key=lambda d: (
            -int(d in suggested), -len(sources_for(qid, labels[d])), labels[d]['name'], d))
        print('\n' + '=' * 75)
        print(qid, 'QUESTION:', question['query_en'])
        print('Assess the seven indexed sections of ALL 25 SOURCE LABELS; do not infer clinical safety.')
        print('Keyword matches are navigation hints; the proposed candidate is NOT assumed correct.')
        for ordinal, drug_id in enumerate(order, 1):
            if (qid, drug_id) in decisions:
                continue
            label = labels[drug_id]
            snippets = sources_for(qid, label)
            print('\n' + '-' * 75)
            print(f'{qid} | {ordinal}/25 | {label["name"]} | {drug_id}')
            if drug_id in suggested:
                print('SOURCE-DERIVED CANDIDATE — manually check')
            print('Keyword hits:', len(snippets), '(not a relevance score)')
            for sec, snip in snippets[:2]:
                print(f'[{sec}]: {snip[:450]}')
            if not snippets:
                print('No matching keyword hint. This DOES NOT prove irrelevance; inspect indexed sections.')
            while True:
                answer = input('Relevant to question in THIS label? [y]es/[n]o/[f]ull source/[s]kip/[q]uit: ').strip().lower()
                if answer in {'y', 'n'}:
                    decisions[(qid, drug_id)] = {
                        'query_id': qid, 'drug_id': drug_id,
                        'decision': 'yes' if answer == 'y' else 'no',
                        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    }
                    store_decisions(decisions)
                    print('Saved judgment:', answer)
                    break
                if answer == 'f':
                    full_label_file(qid, question['query_en'], drug_id, label)
                elif answer == 's':
                    print('Skipped; will ask next time.')
                    break
                elif answer == 'q':
                    print('Stopped. All previous judgments saved.')
                    return
                else:
                    print('Type y, n, f, s or q.')
        finish_question(question, rows, labels, decisions)
    print('\nSession finished. Run --status to see progress.')


def status(rows, labels, decisions):
    status_counts = Counter(r['review_status'] for r in rows)
    print(f'Benchmark questions: approved={status_counts["approved"]}, pending={status_counts["pending"]}, rejected={status_counts["rejected"]}')
    for i in range(1, 9):
        qid = f'Q{i:02d}'
        ds = [d['decision'] for (q, _), d in decisions.items() if q == qid]
        print(f'{qid}: judged {len(ds)}/{len(labels)}; relevant={ds.count("yes")}; irrelevant={ds.count("no")}')
    print('Existing Q09–Q30 gold answers are not modified by this tool.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    ops = parser.add_mutually_exclusive_group(required=True)
    ops.add_argument('--status', action='store_true', help='Show progress only')
    ops.add_argument('--review', metavar='Q01|ALL', help='Review semantic question by ID or all remaining')
    args = parser.parse_args()
    rows, by_q, labels, decisions = load_state()
    if args.status:
        status(rows, labels, decisions)
        return
    value = args.review.upper()
    if value != 'ALL' and value not in HINTS:
        parser.error('Use --review Q01 ... --review Q08, or --review ALL')
    qids = sorted(HINTS) if value == 'ALL' else [value]
    review(qids, rows, by_q, labels, decisions)
    status(rows, labels, decisions)

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError, csv.Error) as e:
        print('ERROR:', e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nInterrupted. Previously saved decisions are preserved.')
