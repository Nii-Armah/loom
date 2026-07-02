from dataclasses import dataclass
import enum
import io
import os
from pathlib import Path
from typing import Optional


@dataclass
class EntryMetaData:
    start: int
    value_index: int
    end: int


class EntryStatus(enum.IntEnum):
    ACTIVE = 1
    DELETED = 2


class LoomCore:
    """A vector database."""
    ENTRY_STATUS_BYTESIZE = 1
    VALUE_METADATA_BYTESIZE = 4
    KEY_METADATA_BYTESIZE = 4

    @property
    def metadata_bytesize(self) -> int:
        return self.ENTRY_STATUS_BYTESIZE + self.VALUE_METADATA_BYTESIZE + self.KEY_METADATA_BYTESIZE

    def __init__(self, data_dir: str | Path):
        """Initialize the database."""
        self._data_dir = Path(data_dir)
        self._db_file = Path(self._data_dir, 'db.loom')
        self._cache: Optional[dict[str, EntryMetaData]] = None

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
            while status := int.from_bytes(f.read(self.ENTRY_STATUS_BYTESIZE), byteorder='big'):
                start = f.tell() - self.ENTRY_STATUS_BYTESIZE
                key_size = int.from_bytes(f.read(self.KEY_METADATA_BYTESIZE), byteorder='big')
                value_size = int.from_bytes(f.read(self.VALUE_METADATA_BYTESIZE), byteorder='big')
                key = f.read(key_size).decode('utf-8')

                if status == EntryStatus.ACTIVE:
                    self._cache[key] = EntryMetaData(start=start, value_index=f.tell(), end=f.tell() + value_size - 1)

                else:
                    self._cache.pop(key, None)

                f.seek(value_size, io.SEEK_CUR)

    def _set(self, key: str, value: str, status: int) -> None:
        with self._db_file.open(mode='ab') as f:
            start = f.tell()
            encoded_status = status.to_bytes(self.ENTRY_STATUS_BYTESIZE, byteorder='big')
            encoded_key = key.encode('utf-8')
            encoded_value = value.encode('utf-8')
            encoded_key_size = len(encoded_key).to_bytes(self.KEY_METADATA_BYTESIZE, byteorder='big')
            encoded_value_size = len(encoded_value).to_bytes(self.VALUE_METADATA_BYTESIZE, byteorder='big')
            entry = encoded_status + encoded_key_size + encoded_value_size + encoded_key + encoded_value
            f.write(entry)

            value_index = start + self.metadata_bytesize + len(encoded_key)
            self._cache[key] = EntryMetaData(start=start, value_index=value_index, end=f.tell() - 1)

            if status == EntryStatus.DELETED:
                self._cache.pop(key, None)


    def set(self, key: str, value: str) -> None:
        """Set `value` to `key`."""
        if not self._is_bootstrapped():
            raise RuntimeError('Database is not bootstrapped. Invoke LoomCore.boot() first.')

        self._set(key, value, EntryStatus.ACTIVE)

    def get(self, key: str) -> str | None:
        """Retrieve value associated with `key`."""
        if not self._is_bootstrapped():
            raise RuntimeError('Database is not bootstrapped. Invoke LoomCore.boot() first.')

        entry_metadata = self._cache.get(key)
        if entry_metadata is None:
            return None

        with self._db_file.open(mode='rb') as f:
            f.seek(entry_metadata.start)
            status = int.from_bytes(f.read(self.ENTRY_STATUS_BYTESIZE))
            if status == EntryStatus.DELETED:
                return None

            f.seek(entry_metadata.value_index, os.SEEK_SET)
            value_size = entry_metadata.end - entry_metadata.value_index + 1
            value = f.read(value_size).decode('utf-8')
            return value

    def delete(self, key: str) -> None:
        """Delete entry associated with `key`."""
        if not self._is_bootstrapped():
            raise RuntimeError('Database is not bootstrapped. Invoke LoomCore.boot() first.')

        value = self.get(key)
        if value:
            self._set(key, value, EntryStatus.DELETED)

    def compact(self) -> None:
        """Compact all entries in database."""
        if not self._is_bootstrapped():
            raise RuntimeError('Database is not bootstrapped. Invoke LoomCore.boot() first.')

        assert isinstance(self._cache, dict)
        active_entries = []
        with self._db_file.open(mode='rb') as f:
            for key, entry_metadata in self._cache.items():
                entry_size = entry_metadata.end - entry_metadata.start + 1
                f.seek(entry_metadata.start, io.SEEK_SET)
                entry = f.read(entry_size)
                active_entries.append(entry)

        temp_file = self._data_dir / 'temp-db.loom'
        with temp_file.open(mode='wb') as f:
            f.write(b''.join(active_entries))
            f.flush()
            os.fsync(f.fileno())

        try:
            temp_file.replace(self._db_file)
            self.boot()
        except OSError:
            temp_file.unlink()
