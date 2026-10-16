"""Build a source-only plugin ZIP for the official QGIS plugin repository."""

from __future__ import annotations

import argparse
from configparser import ConfigParser
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

PACKAGE_NAME = "polskie_dane"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "__init__.py",
    "plugin.py",
    "metadata.txt",
    "LICENSE",
    "NOTICE.md",
    "README.md",
    "CHANGELOG.md",
)
SOURCE_DIRECTORIES = {
    "core": {".py"},
    "gui": {".py"},
    "services": {".py"},
    "resources": {".ui", ".qss", ".svg"},
}
MAX_ARCHIVE_SIZE = 25_000_000


def build_package(root: Path, output: Path) -> Path:
    """Package only runtime sources, resources, licensing and user docs."""
    metadata = ConfigParser(interpolation=None)
    metadata.read(root / "metadata.txt", encoding="utf-8")
    required = (
        "name",
        "description",
        "version",
        "qgisMinimumVersion",
        "author",
        "email",
        "about",
        "tracker",
        "repository",
    )
    for key in required:
        if not metadata.get("general", key, fallback="").strip():
            raise ValueError(f"Missing required metadata: {key}")

    paths = [root / name for name in ROOT_FILES]
    paths.extend(
        root / directory / "__init__.py"
        for directory in SOURCE_DIRECTORIES
        if directory != "resources"
    )
    icon = metadata.get("general", "icon")
    paths.append(root / icon)
    for path in paths:
        if not path.is_file():
            raise ValueError(f"Missing package file: {path.relative_to(root)}")
    for directory, extensions in SOURCE_DIRECTORIES.items():
        paths.extend(
            path
            for path in (root / directory).rglob("*")
            if path.is_file()
            and path.suffix in extensions
            and not any(
                part.startswith(".") or part == "__pycache__"
                for part in path.relative_to(root).parts
            )
        )
    paths = sorted(set(paths))
    for path in paths:
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Package path escapes repository: {path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in paths:
            name = f"{PACKAGE_NAME}/{path.relative_to(root).as_posix()}"
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    if output.stat().st_size > MAX_ARCHIVE_SIZE:
        output.unlink()
        raise ValueError("Plugin ZIP exceeds QGIS's 25 MB limit")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "dist" / "polskie_dane.zip",
    )
    args = parser.parse_args()
    output = build_package(REPOSITORY_ROOT, args.output)
    print(f"Created {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
