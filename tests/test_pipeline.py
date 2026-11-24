"""Offline synthetic fixtures for unit tests ONLY, never part of the research corpus."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load_script(name, short):
    spec = importlib.util.spec_from_file_location(short, ROOT / "scripts" / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

fetcher = load_script("01_fetch_openfda.py", "fetcher")
prep = load_script("02_prepare_dataset.py", "prep")

SYNTHETIC_FIXTURE = {
    "provenance": {"retrieved_at_utc": "2020-01-01T00:00:00+00:00"},
    "results": [{
        "set_id": "TEST-SET-000", "id": "TEST-DOC-000", "version": "1",
        "effective_time": "20200101",
        "openfda": {"generic_name": ["Testonly"], "brand_name": ["Testonly"],
                    "product_type": ["HUMAN PRESCRIPTION DRUG"],
                    "substance_name": ["TESTOONLY SUBSTANCE"],
                    "route": ["ORAL"],
                    "pharm_class_epc": ["TEST CLASS [EPC]"]},
        "description": ["This is an invented unit test fixture only."],
        "contraindications": ["Some made-up contraindication X for testing."],
        "indications_and_usage": ["Some made-up indication Y for testing."],
        "drug_interactions": ["Some made-up interaction Z for testing."]
    }]
}


class PrepareTest(unittest.TestCase):
    def test_required_sections(self):
        self.assertTrue(fetcher.qualified(SYNTHETIC_FIXTURE["results"][0]))
        bad = json.loads(json.dumps(SYNTHETIC_FIXTURE["results"][0]))
        del bad["contraindications"]
        self.assertFalse(fetcher.qualified(bad))

    def test_clean_and_chunking(self):
        self.assertEqual(prep.clean("alpha <b>beta</b> &amp; gamma"), "alpha beta & gamma")
        parts = list(prep.chunk_words(" ".join(str(i) for i in range(350)), 100, 25))
        self.assertEqual(len(parts), 5)
        self.assertEqual(parts[0].split()[-25:], parts[1].split()[:25])
        with self.assertRaises(ValueError):
            list(prep.chunk_words("abc", 100, 100))

    def test_graph_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = pathlib.Path(tmp) / "processed"
            anns = pathlib.Path(tmp) / "verified_constraints.csv"
            anns.write_text("drug_id,relation,concept_type,concept_id,concept_label,evidence_chunk_id,evidence_quote,status,reviewed_by\n", encoding="utf-8")
            stats = prep.prepare(SYNTHETIC_FIXTURE, dest, anns, 100, 20)
            self.assertEqual(stats["actual_label_count"], 1)
            self.assertEqual(stats["verified_constraint_claims"], 0)
            self.assertGreaterEqual(len(stats["node_types"]), 7)
            self.assertGreaterEqual(len(stats["edge_types"]), 6)
            self.assertTrue((dest / "chunks.jsonl").exists())
            self.assertFalse("HAS_CONTRAINDICATION" in stats["edge_types"])

    def test_verified_claim_requires_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = pathlib.Path(tmp) / "processed"
            anns = pathlib.Path(tmp) / "verified_constraints.csv"
            anns.write_text("drug_id,relation,concept_type,concept_id,concept_label,evidence_chunk_id,evidence_quote,status,reviewed_by\n", encoding="utf-8")
            prep.prepare(SYNTHETIC_FIXTURE, dest, anns)
            chunks = [json.loads(line) for line in (dest / "chunks.jsonl").read_text().splitlines()]
            target = next(x for x in chunks if x["section_type"] == "contraindications")
            anns.write_text("drug_id,relation,concept_type,concept_id,concept_label,evidence_chunk_id,evidence_quote,status,reviewed_by\n" +
                            f"{target['drug_id']},HAS_CONTRAINDICATION,Contraindication,,Test condition,{target['chunk_id']},invented unit test fixture,verified,unit-test\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                prep.prepare(SYNTHETIC_FIXTURE, dest, anns)


if __name__ == "__main__":
    unittest.main()
