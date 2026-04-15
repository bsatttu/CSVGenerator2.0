"""
Session persistence for CSV Generator 2.0.

Pure-Python module (no Qt imports). Each session is a folder on disk containing:
    session.json          - metadata (set name, sport, box, image path, timestamps, status)
    listings.parquet      - the editable pandas DataFrame
    input_snapshot.csv    - copy of the original input CSV
    outputs/              - generated output CSVs

The root sessions directory also contains an index.json that mirrors session
metadata for fast listing/search without walking the tree.
"""

import json
import os
import re
import shutil
from datetime import datetime
from typing import List, Optional

import pandas as pd


INDEX_FILE = "index.json"
SESSION_META_FILE = "session.json"
LISTINGS_FILE = "listings.parquet"
INPUT_SNAPSHOT_FILE = "input_snapshot.csv"
OUTPUTS_DIR = "outputs"


def _safe_slug(text: str) -> str:
    """Filesystem-safe slug derived from text (keeps letters, digits, -, _)."""
    if not text:
        return "session"
    cleaned = re.sub(r'[^A-Za-z0-9_\-]+', '', text)
    return cleaned or "session"


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _year_from_iso(iso: str) -> str:
    return iso[:4] if iso else datetime.now().strftime('%Y')


class SessionManager:
    """Manages on-disk sessions under a configurable root directory."""

    def __init__(self, root_directory: str):
        self.root = root_directory
        _ensure_dir(self.root)
        self.index_path = os.path.join(self.root, INDEX_FILE)

    # ------------------------------------------------------------------ index

    def _load_index(self) -> List[dict]:
        if not os.path.isfile(self.index_path):
            return []
        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _save_index(self, entries: List[dict]) -> None:
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2)

    def _upsert_index(self, entry: dict) -> None:
        entries = self._load_index()
        entries = [e for e in entries if e.get('id') != entry['id']]
        entries.append(entry)
        # Sort newest first
        entries.sort(key=lambda e: e.get('updated_at', ''), reverse=True)
        self._save_index(entries)

    def _remove_from_index(self, session_id: str) -> None:
        entries = [e for e in self._load_index() if e.get('id') != session_id]
        self._save_index(entries)

    def list_sessions(self) -> List[dict]:
        """Return all session index entries, newest first."""
        return self._load_index()

    def search_sessions(self, query: str = "", year: Optional[str] = None) -> List[dict]:
        """Filter index entries by a case-insensitive substring query and/or year."""
        query = (query or "").strip().lower()
        results = []
        for e in self._load_index():
            if year and e.get('year') != year:
                continue
            if query:
                haystack = " ".join([
                    str(e.get('card_set', '')),
                    str(e.get('card_set_short', '')),
                    str(e.get('box', '')),
                    str(e.get('sport', '')),
                    str(e.get('id', '')),
                ]).lower()
                if query not in haystack:
                    continue
            results.append(e)
        return results

    def available_years(self) -> List[str]:
        """All distinct years represented in the index, newest first."""
        years = sorted({e.get('year', '') for e in self._load_index() if e.get('year')},
                       reverse=True)
        return years

    def rebuild_index(self) -> int:
        """Walk the sessions tree and rebuild index.json from session.json files.
        Returns the number of sessions indexed."""
        entries: List[dict] = []
        if os.path.isdir(self.root):
            for year_name in os.listdir(self.root):
                year_dir = os.path.join(self.root, year_name)
                if not os.path.isdir(year_dir):
                    continue
                for session_name in os.listdir(year_dir):
                    session_dir = os.path.join(year_dir, session_name)
                    meta_path = os.path.join(session_dir, SESSION_META_FILE)
                    if os.path.isfile(meta_path):
                        try:
                            with open(meta_path, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                            entries.append(self._index_entry_from_meta(meta, session_dir))
                        except (json.JSONDecodeError, OSError):
                            continue
        entries.sort(key=lambda e: e.get('updated_at', ''), reverse=True)
        self._save_index(entries)
        return len(entries)

    # ---------------------------------------------------------------- sessions

    @staticmethod
    def _index_entry_from_meta(meta: dict, session_dir: str) -> dict:
        return {
            'id': meta.get('id'),
            'year': meta.get('year'),
            'created_at': meta.get('created_at'),
            'updated_at': meta.get('updated_at'),
            'card_set': meta.get('card_set'),
            'card_set_short': meta.get('card_set_short'),
            'box': meta.get('box'),
            'sport': meta.get('sport'),
            'status': meta.get('status', 'draft'),
            'path': session_dir,
        }

    def create_session(self,
                        card_set: str = "",
                        card_set_short: str = "",
                        box: str = "",
                        sport: str = "",
                        image_path: str = "",
                        input_path: str = "") -> dict:
        """Create a new session folder and return its metadata (including `path`)."""
        now = _now_iso()
        year = _year_from_iso(now)
        stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        slug = _safe_slug(card_set_short or card_set or "session")
        session_id = f"{stamp}_{slug}"
        session_dir = os.path.join(self.root, year, session_id)
        _ensure_dir(session_dir)
        _ensure_dir(os.path.join(session_dir, OUTPUTS_DIR))

        meta = {
            'id': session_id,
            'year': year,
            'created_at': now,
            'updated_at': now,
            'card_set': card_set,
            'card_set_short': card_set_short,
            'box': box,
            'sport': sport,
            'image_path': image_path,
            'input_path': input_path,
            'status': 'draft',
        }
        meta['path'] = session_dir

        self._write_meta(session_dir, meta)
        self._upsert_index(self._index_entry_from_meta(meta, session_dir))

        # Copy the input file as a snapshot if it exists
        if input_path and os.path.isfile(input_path):
            try:
                shutil.copy2(input_path, os.path.join(session_dir, INPUT_SNAPSHOT_FILE))
            except OSError:
                pass

        return meta

    def _write_meta(self, session_dir: str, meta: dict) -> None:
        # Don't persist the runtime-only `path` key; it's recomputed from folder location.
        to_write = {k: v for k, v in meta.items() if k != 'path'}
        with open(os.path.join(session_dir, SESSION_META_FILE), 'w', encoding='utf-8') as f:
            json.dump(to_write, f, indent=2)

    def save_session(self, session_meta: dict, listings_df: Optional[pd.DataFrame] = None,
                      status: Optional[str] = None) -> dict:
        """Persist updated metadata and (optionally) the listings DataFrame."""
        session_dir = session_meta.get('path')
        if not session_dir or not os.path.isdir(session_dir):
            raise ValueError("Session path missing or does not exist: " + str(session_dir))

        session_meta = dict(session_meta)
        session_meta['updated_at'] = _now_iso()
        if status:
            session_meta['status'] = status

        self._write_meta(session_dir, session_meta)

        if listings_df is not None:
            try:
                listings_df.to_parquet(os.path.join(session_dir, LISTINGS_FILE))
            except (ImportError, ValueError):
                # Fall back to CSV if pyarrow/fastparquet isn't available
                listings_df.to_csv(os.path.join(session_dir, LISTINGS_FILE + '.csv'), index=False)

        self._upsert_index(self._index_entry_from_meta(session_meta, session_dir))
        return session_meta

    def load_session(self, session_id_or_path: str) -> dict:
        """Load session metadata plus the listings DataFrame (if present).

        Accepts either a session id (matched against the index) or a direct folder path.
        The returned dict includes a 'listings' DataFrame key (may be None).
        """
        session_dir = None
        if os.path.isdir(session_id_or_path):
            session_dir = session_id_or_path
        else:
            for entry in self._load_index():
                if entry.get('id') == session_id_or_path:
                    session_dir = entry.get('path')
                    break

        if not session_dir or not os.path.isdir(session_dir):
            raise FileNotFoundError("Session not found: " + str(session_id_or_path))

        meta_path = os.path.join(session_dir, SESSION_META_FILE)
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        meta['path'] = session_dir

        listings_path = os.path.join(session_dir, LISTINGS_FILE)
        listings_csv_fallback = listings_path + '.csv'
        listings = None
        if os.path.isfile(listings_path):
            try:
                listings = pd.read_parquet(listings_path)
            except (ImportError, ValueError):
                listings = None
        if listings is None and os.path.isfile(listings_csv_fallback):
            listings = pd.read_csv(listings_csv_fallback)
        if listings is None:
            snapshot = os.path.join(session_dir, INPUT_SNAPSHOT_FILE)
            if os.path.isfile(snapshot):
                listings = pd.read_csv(snapshot)

        meta['listings'] = listings
        return meta

    def delete_session(self, session_id: str) -> bool:
        """Remove a session from disk and the index."""
        for entry in self._load_index():
            if entry.get('id') == session_id:
                session_dir = entry.get('path')
                if session_dir and os.path.isdir(session_dir):
                    shutil.rmtree(session_dir, ignore_errors=True)
                self._remove_from_index(session_id)
                return True
        return False

    def outputs_dir(self, session_meta: dict) -> str:
        """Return (and ensure) the outputs/ folder for a session."""
        path = os.path.join(session_meta['path'], OUTPUTS_DIR)
        _ensure_dir(path)
        return path
