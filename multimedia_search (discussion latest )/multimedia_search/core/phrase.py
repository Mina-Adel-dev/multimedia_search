"""Phrase search using positional index."""

from typing import List, Set

from multimedia_search.core.index import IndexReader
from multimedia_search.core.preprocessor import Preprocessor


class PhraseSearcher:
    """Find documents containing an exact phrase."""

    def __init__(self, index_reader: IndexReader, preprocessor: Preprocessor):
        self.index = index_reader
        self.preprocessor = preprocessor

    def search(self, phrase: str) -> Set[int]:
        """
        Return set of doc_ids where all phrase terms appear consecutively.
        """
        if not isinstance(phrase, str) or not phrase.strip():
            return set()

        terms = self.preprocessor.process(phrase)
        if not terms:
            return set()

        if len(terms) == 1:
            return self.index.get_term_docids(terms[0])

        postings_list = [self.index.get_postings(term) for term in terms]
        if not all(postings_list):
            return set()

        pos_dicts = []
        for postings in postings_list:
            position_dict = {}
            for doc_id, positions in postings:
                position_dict[doc_id] = positions
            pos_dicts.append(position_dict)

        common_docs = set(pos_dicts[0].keys())
        for position_dict in pos_dicts[1:]:
            common_docs &= set(position_dict.keys())

        result = set()
        for doc_id in common_docs:
            pos_lists: List[List[int]] = [position_dict[doc_id] for position_dict in pos_dicts]

            for start_pos in pos_lists[0]:
                match = True
                for offset, positions in enumerate(pos_lists[1:], start=1):
                    if start_pos + offset not in positions:
                        match = False
                        break

                if match:
                    result.add(doc_id)
                    break

        return result
