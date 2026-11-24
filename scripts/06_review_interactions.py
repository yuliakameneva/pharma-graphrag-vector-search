import csv
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS = ROOT / 'annotations'
SOURCE = ANNOTATIONS / 'interaction_candidates_9_PENDING.csv'
DEST = ANNOTATIONS / 'verified_constraints.csv'
CHUNKS = ROOT / 'data' / 'processed' / 'chunks.jsonl'
FIELDS = ['drug_id','relation','concept_type','concept_id','concept_label',
          'evidence_chunk_id','evidence_quote','status','reviewed_by']


def load_csv(path):
    with path.open('r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(FIELDS).issubset(set(reader.fieldnames)):
            raise ValueError('Invalid CSV header in ' + str(path))
        return list(reader)


def key(row):
    return (row['drug_id'].strip(), row['relation'].strip(),
            row['concept_label'].strip().casefold(), row['evidence_chunk_id'].strip())


def main():
    if not SOURCE.exists() or not DEST.exists() or not CHUNKS.exists():
        print('Missing file. Ensure you have:', SOURCE, DEST, CHUNKS, sep='\n  - ')
        return 1
    import json
    corpus = {}
    with CHUNKS.open(encoding='utf-8') as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                corpus[obj['chunk_id']] = obj
    old = load_csv(DEST)
    new = load_csv(SOURCE)
    keys = {key(r) for r in old}
    to_add = []
    print('Read',len(new),'interaction candidates. Current annotations:',len(old))
    print('Each accepted candidate will become reviewed:student_manual in the graph.')
    print('This is research annotation, not medical advice. Type y only after reviewing evidence.\n')
    for i,row in enumerate(new, start=1):
        if key(row) in keys:
            print(f'{i}. Already present: {row["concept_label"]}. Skipped.')
            continue
        if row['relation'] != 'INTERACTS_WITH' or row['concept_type'] != 'InteractionTarget':
            raise ValueError(f'Unexpected relation/type at row {i}')
        chunk = corpus.get(row['evidence_chunk_id'])
        if not chunk or chunk['drug_id'] != row['drug_id']:
            raise ValueError(f'Chunk or drug_id mismatch at row {i}: {row["evidence_chunk_id"]}')
        text = chunk['text']
        quote = row['evidence_quote'].strip()
        pos = text.casefold().find(quote.casefold())
        if pos < 0:
            raise ValueError(f'Quote not found EXACTLY in source text at row {i}')
        excerpt = text[max(0, pos-140):min(len(text),pos+len(quote)+140)]
        print(f'\n--- {i}/{len(new)} ---')
        print('Drug:', row['drug_id'])
        print('Interaction target:', row['concept_label'])
        print('Category:', row.get('interaction_class', ''))
        print('Note:', row.get('review_note_uk',''))
        print('Source:', row['evidence_chunk_id'])
        print('SOURCE CONTEXT:',excerpt)
        print('EXACT QUOTE:',quote)
        while True:
            choice=input('Have you manually confirmed the claim and correct interpretation? [y/n/q]: ').lower().strip()
            if choice in ('y','n','q'):
                break
        if choice == 'q':
            print('Review interrupted. Nothing has been written.')
            return 0
        if choice == 'y':
            clean_row={col:row.get(col,'') for col in FIELDS}
            clean_row['status']='verified'
            clean_row['reviewed_by']='student_manual'
            to_add.append(clean_row)
            keys.add(key(row))
    if not to_add:
        print('\nNo newly approved interactions. Main CSV unchanged.')
        return 0
    ANNOTATIONS.mkdir(exist_ok=True,parents=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    backup=ANNOTATIONS / f'verified_constraints_backup_{stamp}.csv'
    shutil.copy2(DEST,backup)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8-sig',newline='',dir=ANNOTATIONS,prefix='.constraints_',suffix='.csv',delete=False) as f:
            tmp=Path(f.name)
            w=csv.DictWriter(f,fieldnames=FIELDS)
            w.writeheader()
            w.writerows({c:r.get(c,'') for c in FIELDS} for r in old)
            w.writerows(to_add)
        os.replace(tmp,DEST)
    finally:
        if tmp and tmp.exists(): tmp.unlink()
    print('\nAdded',len(to_add),'verified interaction rows.')
    print('Main annotation file:',DEST)
    print('Backup:',backup)
    print('Now run: py scripts/02_prepare_dataset.py --chunk-size 150 --overlap 30')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, csv.Error) as ex:
        print('ERROR:',ex)
        raise SystemExit(1)
