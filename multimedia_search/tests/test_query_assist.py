import unittest

from multimedia_search.core.document import Document
from multimedia_search.core.index import IndexBuilder, IndexReader
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.utils.phonetics import soundex
from multimedia_search.utils.query_assist import build_did_you_mean, expand_ranked_query


class TestQueryAssist(unittest.TestCase):
    def _build_reader(self, docs):
        builder = IndexBuilder()
        builder.build(docs)
        return IndexReader(builder.get_data())

    def test_soundex_basic(self):
        self.assertEqual(soundex("Robert"), "R163")
        self.assertEqual(soundex("Rupert"), "R163")

    def test_ranked_query_synonym_expansion(self):
        docs = [
            Document(
                doc_id=0,
                path="/fake/auto.txt",
                file_type="txt",
                raw_text="automobile repair manual",
                tokens=Preprocessor().process("automobile repair manual"),
            )
        ]
        reader = self._build_reader(docs)
        preprocessor = Preprocessor()

        expanded = expand_ranked_query("car", reader, preprocessor)
        self.assertIn("car", expanded.split())
        self.assertIn("automobile", expanded.split())

    def test_did_you_mean_from_close_match(self):
        docs = [
            Document(
                doc_id=0,
                path="/fake/auto.txt",
                file_type="txt",
                raw_text="automobile repair manual",
                tokens=Preprocessor().process("automobile repair manual"),
            )
        ]
        reader = self._build_reader(docs)
        suggestion = build_did_you_mean(reader, "automoblie", Preprocessor())
        self.assertEqual(suggestion, "automobile")

    def test_did_you_mean_from_soundex(self):
        docs = [
            Document(
                doc_id=0,
                path="/fake/phone.txt",
                file_type="txt",
                raw_text="phone repair guide",
                tokens=Preprocessor().process("phone repair guide"),
            )
        ]
        reader = self._build_reader(docs)
        suggestion = build_did_you_mean(reader, "fone", Preprocessor())
        self.assertEqual(suggestion, "phone")