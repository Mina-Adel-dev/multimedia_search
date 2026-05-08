"""Generate snippets around matched terms."""

from typing import List

from multimedia_search.config import SNIPPET_LENGTH


class SnippetGenerator:
    """Create a short text snippet highlighting matched terms."""

    def generate(self, text: str, matched_terms: List[str]) -> str:
        """
        Return a snippet of about SNIPPET_LENGTH characters around the first
        occurrence of any matched term.
        """
        if not text:
            return ""

        if not matched_terms:
            return text[:SNIPPET_LENGTH].strip() + ("..." if len(text) > SNIPPET_LENGTH else "")

        text_lower = text.lower()
        first_pos = len(text)

        for term in matched_terms:
            pos = text_lower.find(term.lower())
            if pos != -1 and pos < first_pos:
                first_pos = pos

        if first_pos == len(text):
            return text[:SNIPPET_LENGTH].strip() + ("..." if len(text) > SNIPPET_LENGTH else "")

        half = SNIPPET_LENGTH // 2
        start = max(0, first_pos - half)
        end = min(len(text), start + SNIPPET_LENGTH)

        snippet = text[start:end].strip()

        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet
