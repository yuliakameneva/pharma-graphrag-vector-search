import argparse
import csv
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
import pathlib
import re
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECTIONS = ["description", "indications_and_usage", "contraindications",
            "drug_interactions", "adverse_reactions", "warnings_and_cautions", "boxed_warning"]
ANNOTATION_TYPES = {"Contraindication", "InteractionTarget", "Condition", "SideEffect"}
ANNOTATION_EDGES = {"HAS_CONTRAINDICATION": "Contraindication",
                    "INTERACTS_WITH": "InteractionTarget",
                    "INDICATED_FOR": "Condition", "HAS_SIDE_EFFECT": "SideEffect"}


def hash_id(prefix, *parts):
    return prefix + ":" + hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:20]


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "tr", "li"}:
            self.parts.append(" ")
    def text(self):
        return " ".join(self.parts)


def clean(value):
    parser = TextExtractor()
    parser.feed(str(value or ""))
    result = unescape(parser.text())
    return re.sub(r"\s+", " ", result).strip()


def chunk_words(text, size=150, overlap=30):
    if not (0 <= overlap < size):
        raise ValueError("overlap must be nonnegative and strictly smaller than size")
    words = text.split()
    pos = 0
    while pos < len(words):
        end = min(len(words), pos + size)
        yield " ".join(words[pos:end])
        if end == len(words):
            break
        pos = end - overlap


def first(xs):
    return str(xs[0]) if xs else ""


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")


def add_node(nodes, node_id, kind, **props):
    if node_id not in nodes:
        nodes[node_id] = {"id": node_id, "kind": kind,
                          "properties": {"id": node_id, "kind": kind, **props}}


def add_edge(edges, src, rel, dst, evidence="", status="source_metadata"):
    edges.append({"source_id": src, "relationship": rel,
                  "target_id": dst, "evidence_id": evidence,
                  "verification_status": status})


def load_annotations(annotations_file, nodes, edges, chunks):
    if not annotations_file.exists():
        return 0
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    added = 0
    with annotations_file.open(encoding="utf-8-sig", newline="") as f:
        for ix, row in enumerate(csv.DictReader(f), start=2):
            if not any((v or "").strip() for v in row.values()):
                continue
            relation = row.get("relation", "").strip()
            kind = row.get("concept_type", "").strip()
            drug_id = row.get("drug_id", "").strip()
            chunk_id = row.get("evidence_chunk_id", "").strip()
            quote = clean(row.get("evidence_quote"))
            label = row.get("concept_label", "").strip()
            status = row.get("status", "").strip().lower()
            reviewer = row.get("reviewed_by", "").strip()
            if status != "verified":
                continue  # only independently reviewed facts become edges
            if (relation not in ANNOTATION_EDGES or ANNOTATION_EDGES[relation] != kind
                    or drug_id not in nodes or not label or not reviewer
                    or chunk_id not in chunk_by_id or not quote):
                raise ValueError(f"Invalid verified claim at annotations line {ix}")
            chunk = chunk_by_id[chunk_id]
            if chunk["drug_id"] != drug_id or quote.casefold() not in chunk["text"].casefold():
                raise ValueError(f"Missing exact supporting quotation at line {ix}")
            concept_id = row.get("concept_id", "").strip() or hash_id(kind.upper(), label.casefold())
            add_node(nodes, concept_id, kind, name=label, review_status="verified")
            add_edge(edges, drug_id, relation, concept_id, evidence=chunk_id, status="reviewed:" + reviewer)
            added += 1
    return added


def prepare(raw, output_dir, annotations_file, size=150, overlap=30):
    assert isinstance(raw.get("results"), list)
    nodes, edges, chunks, coverage = {}, [], [], []
    retrieved_at = raw.get("provenance", {}).get("retrieved_at_utc", "")
    for record in sorted(raw["results"], key=lambda r: r.get("set_id", "")):
        ofda = record.get("openfda") or {}
        set_id = record.get("set_id", "")
        rev_id = record.get("id", "")
        if not set_id or not rev_id:
            continue
        drug_id, label_id = "DRUG:" + set_id, "LABEL:" + rev_id
        if drug_id in nodes:
            raise ValueError("Repeated set_id; choose one label revision per set_id")
        add_node(nodes, drug_id, "Drug", set_id=set_id,
                 brand_name=first(ofda.get("brand_name")),
                 generic_name=first(ofda.get("generic_name")),
                 product_type=first(ofda.get("product_type")),
                 manufacturer=first(ofda.get("manufacturer_name")))
        add_node(nodes, label_id, "DrugLabel", set_id=set_id, document_id=rev_id,
                 version=str(record.get("version") or ""),
                 effective_time=str(record.get("effective_time") or ""),
                 retrieved_at_utc=retrieved_at,
                 source_api_url="https://api.fda.gov/drug/label.json",
                 source_set_id=set_id)
        add_edge(edges, drug_id, "HAS_LABEL", label_id, evidence=label_id)

        for name in sorted(set(ofda.get("substance_name") or [])):
            name = clean(name)
            if name:
                ingredient_id = hash_id("ING", name.casefold())
                add_node(nodes, ingredient_id, "ActiveIngredient", name=name)
                add_edge(edges, drug_id, "HAS_ACTIVE_INGREDIENT", ingredient_id,
                         evidence=label_id + "#openfda.substance_name")
        for field in ("pharm_class_epc", "pharm_class_cs", "pharm_class_moa"):
            for name in sorted(set(ofda.get(field) or [])):
                name = clean(name)
                if name:
                    cls_id = hash_id("CLASS", field, name.casefold())
                    add_node(nodes, cls_id, "DrugClass", name=name, class_kind=field)
                    add_edge(edges, drug_id, "BELONGS_TO_CLASS", cls_id,
                             evidence=label_id + "#openfda." + field)
        for name in sorted(set(ofda.get("route") or [])):
            name = clean(name)
            if name:
                route_id = hash_id("ROUTE", name.casefold())
                add_node(nodes, route_id, "AdministrationRoute", name=name)
                add_edge(edges, drug_id, "ADMINISTERED_VIA", route_id,
                         evidence=label_id + "#openfda.route")

        section_count = 0
        chunk_count = 0
        present_fields = []
        for field in SECTIONS:
            passages = [clean(v) for v in record.get(field, [])]
            combined = "\n".join(s for s in passages if s)
            if not combined:
                continue
            present_fields.append(field)
            section_count += 1
            section_id = hash_id("SECTION", rev_id, field)
            add_node(nodes, section_id, "TextSection", section_type=field,
                     label_id=label_id, drug_id=drug_id, length_chars=len(combined))
            add_edge(edges, label_id, "HAS_SECTION", section_id, evidence=section_id)
            for i, piece in enumerate(chunk_words(combined, size, overlap)):
                ch_id = hash_id("CHUNK", rev_id, field, i)
                c = {"chunk_id": ch_id, "drug_id": drug_id, "label_id": label_id,
                     "section_id": section_id, "section_type": field,
                     "chunk_index": i, "text": piece,
                     "set_id": set_id, "document_id": rev_id}
                chunks.append(c)
                add_node(nodes, ch_id, "TextChunk", drug_id=drug_id,
                         section_id=section_id, section_type=field, chunk_index=i,
                         text=piece)
                add_edge(edges, section_id, "HAS_CHUNK", ch_id, evidence=ch_id)
                chunk_count += 1
        coverage.append({"drug_id": drug_id,
                         "generic_name": first(ofda.get("generic_name")),
                         "set_id": set_id, "sections": section_count,
                         "chunks": chunk_count,
                         **{field: int(field in present_fields) for field in SECTIONS}})

    checked_claims = load_annotations(annotations_file, nodes, edges, chunks)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "nodes.jsonl", sorted(nodes.values(), key=lambda x: x["id"]))
    write_jsonl(output_dir / "edges.jsonl", sorted(edges, key=lambda x: (x["source_id"], x["relationship"], x["target_id"])))
    write_jsonl(output_dir / "chunks.jsonl", chunks)
    columns = ["drug_id", "generic_name", "set_id", "sections", "chunks", *SECTIONS]
    with (output_dir / "quality_by_drug.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(coverage)
    node_counts = dict(sorted(Counter(n["kind"] for n in nodes.values()).items()))
    rel_counts = dict(sorted(Counter(e["relationship"] for e in edges).items()))
    stats = {
        "actual_label_count": len(coverage), "total_chunks": len(chunks),
        "nodes_total": len(nodes), "edges_total": len(edges),
        "node_types": node_counts, "edge_types": rel_counts,
        "verified_constraint_claims": checked_claims,
        "source_retrieved_at": retrieved_at,
        "chunking": {"unit": "words", "size": size, "overlap": overlap},
        "reproducibility_note": "Every edge is supported by metadata or explicitly reviewed chunk quotation."
    }
    (output_dir / "dataset_stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=pathlib.Path, default=ROOT / "data" / "raw" / "openfda_pilot.json")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "data" / "processed")
    ap.add_argument("--annotations", type=pathlib.Path, default=ROOT / "annotations" / "verified_constraints.csv")
    ap.add_argument("--chunk-size", type=int, default=150)
    ap.add_argument("--overlap", type=int, default=30)
    args = ap.parse_args()
    if not args.input.exists():
        ap.error(f"Missing real data: {args.input}. Run 01_fetch_openfda.py first.")
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    prepare(raw, args.out, args.annotations, args.chunk_size, args.overlap)


if __name__ == "__main__":
    main()
