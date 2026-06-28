from collections import namedtuple
import io
from pathlib import Path
from typing import Optional


ValueMetaData = namedtuple('ValueMetaData', ['size', 'index'])


class LoomCore:
    """A vector database."""
    ENTRY_METADATA_BYTESIZE = 4
    KEY_METADATA_BYTESIZE = 4

    @property
    def metadata_bytesize(self) -> int:
        return self.ENTRY_METADATA_BYTESIZE + self.KEY_METADATA_BYTESIZE

    def __init__(self, data_dir: str | Path):
        """Initialize the database."""
        self._data_dir = Path(data_dir)
        self._db_file = Path(self._data_dir, 'db.loom')
        self._cache: Optional[dict[str, ValueMetaData]] = None

    def _is_bootstrapped(self) -> bool:
        """Check if the database is bootstrapped."""
        constraints = [self._data_dir.exists(), self._db_file.exists(), self._cache is not None]
        return False if not all(constraints) else True

    def boot(self) -> None:
        """Bootstrap the database."""
        if not self._data_dir.exists():
            self._data_dir.mkdir(parents=True)

        self._db_file.touch(exist_ok=True)

        # Build in-memory cache
        self._cache = {}
        with self._db_file.open(mode='rb') as f:
            while entry_size := int.from_bytes(f.read(self.ENTRY_METADATA_BYTESIZE), byteorder='big'):
                key_size = int.from_bytes(f.read(self.KEY_METADATA_BYTESIZE), byteorder='big')
                key = f.read(key_size).decode('utf-8')

                self._cache[key] = ValueMetaData(entry_size - key_size, f.tell())
                f.seek(entry_size - key_size, io.SEEK_CUR)


    def set(self, key: str, value: str) -> None:
        """Set `value` to `key`."""
        if not self._is_bootstrapped():
            raise RuntimeError('Database is not bootstrapped. Invoke LoomCore.boot() first.')

        encoded_key = key.encode('utf-8')
        with self._db_file.open(mode='ab') as f:
            encoded_entry = encoded_key + value.encode('utf-8')
            key_size = len(encoded_key)
            entry_size = len(encoded_entry)

            key_size_bytes = key_size.to_bytes(self.KEY_METADATA_BYTESIZE, byteorder='big')
            entry_size_bytes = entry_size.to_bytes(self.ENTRY_METADATA_BYTESIZE, byteorder='big')
            f.write(entry_size_bytes + key_size_bytes + encoded_entry)
            value_size = entry_size - key_size
            self._cache[key] = ValueMetaData(value_size, f.tell() - value_size)

    def get(self, key: str) -> str | None:
        """Retrieve value associated with `key`."""
        if not self._is_bootstrapped():
            raise RuntimeError('Database is not bootstrapped. Invoke LoomCore.boot() first.')

        value_metadata = self._cache.get(key)
        if value_metadata is None:
            return None

        with open(self._db_file, 'rb') as f:
            f.seek(value_metadata.index, io.SEEK_SET)
            entry = f.read(value_metadata.size).decode('utf-8')
            return entry
