"""Save and load index using pickle."""

import pickle
from pathlib import Path
from multimedia_search.core.index import IndexBuilder, IndexReader
from multimedia_search.utils.exceptions import IndexNotFoundError

class IndexPersistence:
    """Handles serialization of index data."""

    @staticmethod
    def save(index_builder: IndexBuilder, path: Path) -> None:
        """Serialize index data to disk."""
        data = index_builder.get_data()
        with open(path, "wb") as f:
            pickle.dump(data, f)

    @staticmethod
    def load(path: Path) -> IndexReader:
        """Load index data from disk and return an IndexReader."""
        if not path.exists():
            raise IndexNotFoundError(f"No index found at {path}")
        with open(path, "rb") as f:
            data = pickle.load(f)
        return IndexReader(data)