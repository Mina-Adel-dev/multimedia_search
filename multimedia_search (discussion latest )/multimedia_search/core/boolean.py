"""Boolean query parser and evaluator (AND, OR, NOT, parentheses)."""

from typing import List, Set

from multimedia_search.core.index import IndexReader
from multimedia_search.core.preprocessor import Preprocessor


class BooleanQueryError(ValueError):
    """Raised when a Boolean query is invalid."""


class BooleanRetriever:
    """Parse and evaluate Boolean expressions."""

    def __init__(self, index_reader: IndexReader, preprocessor: Preprocessor):
        self.index = index_reader
        self.preprocessor = preprocessor

    def evaluate(self, query: str) -> Set[int]:
        """
        Parse and evaluate a Boolean query.
        Example: "python AND (java OR ruby) AND NOT c++"
        """
        if not isinstance(query, str) or not query.strip():
            raise BooleanQueryError("Boolean query cannot be empty.")

        tokens = self._tokenize(query)
        if not tokens:
            raise BooleanQueryError("Boolean query contains no searchable terms.")

        postfix = self._shunting_yard(tokens)
        return self._evaluate_postfix(postfix)

    def _tokenize(self, query: str) -> List[str]:
        """Convert query string into operators, parentheses, and normalized terms."""
        query = query.replace("(", " ( ").replace(")", " ) ")
        raw_tokens = query.split()

        tokens: List[str] = []
        for token in raw_tokens:
            upper = token.upper()

            if upper in {"AND", "OR", "NOT"}:
                tokens.append(upper)
            elif token in {"(", ")"}:
                tokens.append(token)
            else:
                processed = self.preprocessor.process(token)
                if processed:
                    tokens.append(processed[0])

        return tokens

    def _shunting_yard(self, tokens: List[str]) -> List[str]:
        """Convert infix Boolean expression to postfix."""
        precedence = {"NOT": 3, "AND": 2, "OR": 1}
        output: List[str] = []
        stack: List[str] = []

        prev_type = None  # TERM, OP, LPAREN, RPAREN

        for token in tokens:
            if token == "(":
                if prev_type in {"TERM", "RPAREN"}:
                    raise BooleanQueryError("Missing operator before '('.")
                stack.append(token)
                prev_type = "LPAREN"

            elif token == ")":
                if prev_type in {"OP", "LPAREN", None}:
                    raise BooleanQueryError("Invalid or empty parentheses in Boolean query.")

                while stack and stack[-1] != "(":
                    output.append(stack.pop())

                if not stack:
                    raise BooleanQueryError("Unmatched ')' in Boolean query.")

                stack.pop()
                prev_type = "RPAREN"

            elif token in precedence:
                if token == "NOT":
                    if prev_type in {"TERM", "RPAREN"}:
                        raise BooleanQueryError("Missing operator before NOT.")
                else:
                    if prev_type not in {"TERM", "RPAREN"}:
                        raise BooleanQueryError(f"Operator {token} is missing a left operand.")

                while (
                    stack
                    and stack[-1] != "("
                    and precedence.get(stack[-1], 0) >= precedence[token]
                ):
                    output.append(stack.pop())

                stack.append(token)
                prev_type = "OP"

            else:
                if prev_type in {"TERM", "RPAREN"}:
                    raise BooleanQueryError("Missing operator between terms.")
                output.append(token)
                prev_type = "TERM"

        if prev_type == "OP":
            raise BooleanQueryError("Boolean query cannot end with an operator.")

        while stack:
            top = stack.pop()
            if top == "(":
                raise BooleanQueryError("Unmatched '(' in Boolean query.")
            output.append(top)

        return output

    def _evaluate_postfix(self, postfix: List[str]) -> Set[int]:
        """Evaluate postfix Boolean expression using document ID sets."""
        stack: List[Set[int]] = []

        for token in postfix:
            if token == "AND":
                if len(stack) < 2:
                    raise BooleanQueryError("AND operator is missing operands.")
                right = stack.pop()
                left = stack.pop()
                stack.append(left & right)

            elif token == "OR":
                if len(stack) < 2:
                    raise BooleanQueryError("OR operator is missing operands.")
                right = stack.pop()
                left = stack.pop()
                stack.append(left | right)

            elif token == "NOT":
                if len(stack) < 1:
                    raise BooleanQueryError("NOT operator is missing an operand.")
                operand = stack.pop()
                all_docs = set(range(self.index.get_doc_count()))
                stack.append(all_docs - operand)

            else:
                stack.append(self.index.get_term_docids(token))

        if len(stack) != 1:
            raise BooleanQueryError("Invalid Boolean query structure.")

        return stack[0]
