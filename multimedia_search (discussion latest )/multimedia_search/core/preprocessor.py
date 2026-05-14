"""Text preprocessing: tokenization, stopwords, optional stemming."""

import re
from typing import List, Optional, Set

from multimedia_search.config import STOPWORDS, USE_STEMMING

_STEMMER = None
if USE_STEMMING:
    try:
        from nltk.stem import PorterStemmer
        _STEMMER = PorterStemmer()
    except ImportError:
        _STEMMER = None
        print("Warning: nltk not installed, stemming disabled.")


class Preprocessor:
    """Configurable text preprocessor."""

    def __init__(self, stopwords: Optional[Set[str]] = None, use_stemming: bool = USE_STEMMING):
        self.stopwords = stopwords or STOPWORDS
        self.use_stemming = use_stemming and _STEMMER is not None

    def tokenize(self, text: str) -> List[str]:
        """Split text into alphanumeric tokens (lowercased)."""
        return re.findall(r"\w+", text.lower())

    def process(self, text: str) -> List[str]:
        """
        Full preprocessing pipeline: tokenize, remove stopwords, optional stemming.
        """
        tokens = self.tokenize(text)
        tokens = [t for t in tokens if t not in self.stopwords]

        if self.use_stemming and _STEMMER is not None:
            tokens = [_STEMMER.stem(t) for t in tokens]

        return tokens
