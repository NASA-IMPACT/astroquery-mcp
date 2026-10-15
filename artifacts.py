"""Artifact store: keeps science products (FITS, spectra, tarballs, ...) out of the model context.

Retrieval calls write files into a fresh per-call directory inside the store. Each file is
registered as an artifact and described by a small JSON-able descriptor (archive, product ID,
filename, content type, size, sha256, original download URL, local path, MCP resource URI).
The bytes themselves are only reachable out-of-band via the `astroquery://artifacts/{id}`
MCP resource or the local path.
"""

import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from astropy.io import fits

logger = logging.getLogger(__name__)

RESOURCE_URI = "astroquery://artifacts/{artifact_id}"
ARTIFACT_ID_RE = re.compile(r"^[0-9a-f]{16}$")

FITS_EXTENSIONS = (".fits", ".fit", ".fts", ".fits.gz", ".fit.gz", ".fits.bz2", ".fits.fz")
CONTENT_TYPES = {
    ".fits": "application/fits", ".fit": "application/fits", ".fts": "application/fits",
    ".fz": "application/fits", ".vot": "application/x-votable+xml", ".votable": "application/x-votable+xml",
    ".ecsv": "text/plain", ".npy": "application/x-npy", ".tar": "application/x-tar",
}
COMPRESSION_EXTENSIONS = (".gz", ".bz2", ".xz", ".zip")
# Primary-header keywords worth showing the model; everything else stays in the file
SUMMARY_KEYWORDS = (
    "TELESCOP", "INSTRUME", "DETECTOR", "FILTER", "OBJECT", "DATE-OBS", "EXPTIME",
    "RA_TARG", "DEC_TARG", "BUNIT", "ORIGIN",
)
MAX_SUMMARY_HDUS = 10

_chdir_lock = threading.RLock()


def default_store_dir() -> Path:
    """Per-user cache directory for downloaded products."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "astroquery-mcp" / "artifacts"


@contextmanager
def working_directory(path: Path) -> Iterator[None]:
    """chdir for the duration of a call; serialized because cwd is process-wide.

    (contextlib.chdir needs Python 3.11; we support 3.10.)
    """
    with _chdir_lock:
        previous = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(previous)


def guess_content_type(filename: str) -> tuple[str, str | None]:
    """Return (content_type, encoding) for a filename, e.g. ('application/fits', 'gzip')."""
    name = filename.lower()
    encoding = None
    for ext in COMPRESSION_EXTENSIONS:
        if name.endswith(ext):
            encoding = {".gz": "gzip", ".bz2": "bzip2", ".xz": "xz", ".zip": "zip"}[ext]
            name = name[: -len(ext)]
            break
    suffix = Path(name).suffix
    if suffix in CONTENT_TYPES:
        return CONTENT_TYPES[suffix], encoding
    if encoding == "zip":
        return "application/zip", None
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream", encoding


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fits_summary(path: Path) -> dict[str, Any] | None:
    """HDU names/types/shapes plus a few primary-header cards. Reads headers only, never data."""
    if not path.name.lower().endswith(FITS_EXTENSIONS):
        with open(path, "rb") as f:
            if f.read(9) != b"SIMPLE  =":
                return None
    try:
        with fits.open(path, lazy_load_hdus=True, memmap=True) as hdul:
            hdus = []
            for i, hdu in enumerate(hdul):
                if i >= MAX_SUMMARY_HDUS:
                    hdus.append({"note": "more HDUs omitted"})
                    break
                header = hdu.header
                naxis = header.get("NAXIS", 0)
                hdus.append({
                    "index": i,
                    "name": hdu.name,
                    "type": type(hdu).__name__,
                    "shape": [header.get(f"NAXIS{n}") for n in range(naxis, 0, -1)] if naxis else None,
                })
            primary = hdul[0].header
            keywords = {k: primary[k] for k in SUMMARY_KEYWORDS if k in primary}
        return {"hdus": hdus, "header": {k: v if isinstance(v, (int, float, bool)) else str(v) for k, v in keywords.items()}}
    except Exception as e:  # corrupt or unusual FITS: describe the file without a summary
        logger.debug(f"Could not summarize FITS file {path}: {e}")
        return None


def filename_from_url(url: str, fallback: str) -> str:
    name = Path(urlparse(url).path).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or fallback


class ArtifactStore:
    """Directory of downloaded products plus an index of their descriptors."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else default_store_dir()

    @property
    def index_dir(self) -> Path:
        return self.root / "index"

    def new_call_dir(self, archive: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        path = self.root / "downloads" / f"{stamp}-{archive}-{uuid.uuid4().hex[:8]}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def register(self, path: Path, archive: str, download_url: str | None = None) -> dict[str, Any]:
        """Describe a file on disk and record it in the index."""
        path = Path(path).resolve()
        checksum = sha256_file(path)
        artifact_id = checksum[:16]
        content_type, encoding = guess_content_type(path.name)
        descriptor = {
            "artifact_id": artifact_id,
            "archive": archive,
            "product_id": path.name.split(".")[0],
            "filename": path.name,
            "content_type": content_type,
            "content_encoding": encoding,
            "size_bytes": path.stat().st_size,
            "sha256": checksum,
            "download_url": download_url,
            "local_path": str(path),
            "resource_uri": RESOURCE_URI.format(artifact_id=artifact_id),
        }
        if summary := fits_summary(path):
            descriptor["fits_summary"] = summary
        self.index_dir.mkdir(parents=True, exist_ok=True)
        (self.index_dir / f"{artifact_id}.json").write_text(json.dumps(descriptor))
        return descriptor

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        if not ARTIFACT_ID_RE.match(artifact_id):
            return None
        index_file = self.index_dir / f"{artifact_id}.json"
        if not index_file.exists():
            return None
        return json.loads(index_file.read_text())

    def read_bytes(self, artifact_id: str) -> bytes:
        descriptor = self.get(artifact_id)
        if descriptor is None:
            raise FileNotFoundError(f"Unknown artifact: {artifact_id}")
        return Path(descriptor["local_path"]).read_bytes()


class ArtifactCall:
    """Collects the artifacts produced by one executor call.

    The call directory is created lazily, so calls that produce no products leave nothing behind.
    """

    def __init__(self, store: ArtifactStore, archive: str, accept_paths: bool = False):
        self.store = store
        self.archive = archive
        # Only retrieval calls may turn returned file paths into (resource-readable) artifacts
        self.accept_paths = accept_paths
        self._dir: Path | None = None
        self._urls: dict[Path, str] = {}
        self._registered: dict[Path, dict[str, Any]] = {}
        self._counter = 0

    @property
    def dir(self) -> Path:
        if self._dir is None:
            self._dir = self.store.new_call_dir(self.archive)
        return self._dir

    @property
    def has_dir(self) -> bool:
        return self._dir is not None

    @property
    def descriptors(self) -> list[dict[str, Any]]:
        return list(self._registered.values())

    def _unique_path(self, filename: str) -> Path:
        path = self.dir / filename
        while path.exists():
            self._counter += 1
            path = self.dir / f"{Path(filename).stem}_{self._counter}{Path(filename).suffix}"
        return path

    def note_url(self, path: str | Path, url: str) -> None:
        """Remember where a file came from, for files the library wrote itself."""
        self._urls[Path(path).resolve()] = url

    def add_file(self, path: str | Path, download_url: str | None = None) -> dict[str, Any]:
        path = Path(path).resolve()
        if path not in self._registered:
            self._registered[path] = self.store.register(path, self.archive, download_url or self._urls.get(path))
        return self._registered[path]

    def add_bytes(self, data: bytes, filename: str, download_url: str | None = None) -> dict[str, Any]:
        if Path(filename).suffix == "" and data[:9] == b"SIMPLE  =":
            filename += ".fits"
        path = self._unique_path(filename)
        path.write_bytes(data)
        return self.add_file(path, download_url)

    def add_hdulist(self, hdul: fits.HDUList, filename: str) -> dict[str, Any]:
        buffer = io.BytesIO()
        hdul.writeto(buffer)
        return self.add_bytes(buffer.getvalue(), filename)

    def collect_dir(self) -> None:
        """Register every file the library wrote into the call directory."""
        if self._dir is None:
            return
        for path in sorted(p for p in self._dir.rglob("*") if p.is_file()):
            self.add_file(path)

    def cleanup_if_empty(self) -> None:
        if self._dir is not None and not any(self._dir.iterdir()):
            self._dir.rmdir()


_store: ArtifactStore | None = None


def get_store() -> ArtifactStore:
    """Process-wide store (lazy). Root: ASTROQUERY_MCP_ARTIFACT_DIR, else config `artifacts.dir`,
    else the user cache dir."""
    global _store
    if _store is None:
        from config import get_config

        root = os.environ.get("ASTROQUERY_MCP_ARTIFACT_DIR") or get_config().artifacts.dir
        _store = ArtifactStore(Path(root).expanduser() if root else None)
    return _store
