"""Parser for CSV files."""

import csv
from pathlib import Path
from multimedia_search.parsers.base import BaseParser


class CSVParser(BaseParser):
    """Read CSV and return space-separated values from all cells."""

    def parse(self, file_path: Path) -> str:
        rows = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(" ".join(row))
        return " ".join(rows)