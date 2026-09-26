import codecs
import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

IGNORED_DIRS = frozenset(
    {
        ".git", ".svn", ".hg", ".vs", ".idea", ".vscode",
        "bin", "obj", "packages", "node_modules", "vendor",
        "__pycache__", ".venv", "venv", "target", "dist", "build",
    }
)  # fmt: skip


class LocalFileSource:
    """Walks a directory skipping build output and third-party folders."""

    def iter_paths(self, root: Path) -> Iterable[PurePosixPath]:
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d.lower() not in IGNORED_DIRS)
            relative = Path(current).relative_to(root)
            for name in sorted(files):
                if not (Path(current) / name).is_symlink():
                    yield PurePosixPath(root.name, *relative.parts, name)

    def read_text(self, root: Path, path: PurePosixPath) -> str:
        candidate = root.parent.joinpath(*path.parts).resolve()
        if not candidate.is_relative_to(root.resolve()):
            raise ValueError(f"file is outside the scanned root: {path}")
        return decode(candidate.read_bytes())


def decode(data: bytes) -> str:
    """Legacy files mix UTF-16 (with BOM), UTF-8 and Windows-1252."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")
