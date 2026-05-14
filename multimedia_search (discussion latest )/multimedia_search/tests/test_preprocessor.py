import unittest
from multimedia_search.core.preprocessor import Preprocessor
from multimedia_search.config import STOPWORDS

class TestPreprocessor(unittest.TestCase):
    def setUp(self):
        self.preproc = Preprocessor(stopwords=STOPWORDS, use_stemming=False)

    def test_tokenization_and_lowercase(self):
        text = "Hello World! This is a test."
        tokens = self.preproc.tokenize(text)
        self.assertEqual(tokens, ["hello", "world", "this", "is", "a", "test"])

    def test_stopword_removal(self):
        text = "the cat and the dog are playing"
        tokens = self.preproc.process(text)
        self.assertNotIn("the", tokens)
        self.assertNotIn("and", tokens)
        self.assertIn("cat", tokens)
        self.assertIn("dog", tokens)
        self.assertIn("playing", tokens)

    def test_stemming_enabled(self):
        preproc_stem = Preprocessor(use_stemming=True)
        text = "running runner runs"
        tokens = preproc_stem.process(text)
        for t in tokens:
            self.assertTrue(t.startswith("run"))