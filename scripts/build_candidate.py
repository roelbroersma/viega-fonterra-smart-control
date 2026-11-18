"""Build the source ZIP and SHA-256 manifests from this checkout or an unpacked ZIP."""

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    ".gitattributes",
    ".gitignore",
    "LICENSE",
    "README.md",
    "RELEASE.md",
    "THIRD_PARTY_NOTICES.md",
    "hacs.json",
    "pyproject.toml",
    "requirements-test.txt",
)
SOURCE_DIRS = (
    ".github",
    "custom_components",
    "docs",
    "requirements",
    "scripts",
    "tests",
    "validation",
)
IGNORED = {"__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs")
    output = parser.parse_args().output.resolve()
    relative_output = output.relative_to(ROOT) if output.is_relative_to(ROOT) else None
    if relative_output is not None and (
        not relative_output.parts or relative_output.parts[0] in SOURCE_DIRS
    ):
        parser.error("Output must be outside the archived source directories")

    manifest = ROOT / "custom_components/viega_fonterra_modbus/manifest.json"
    version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    files = [ROOT / name for name in ROOT_FILES]
    for directory in SOURCE_DIRS:
        source = ROOT / directory
        if not source.is_dir():
            raise FileNotFoundError(source)
        for path in source.rglob("*"):
            if path.is_file() and not IGNORED.intersection(path.relative_to(source).parts):
                files.append(path)

    entries = {file.relative_to(ROOT).as_posix(): file.read_bytes() for file in sorted(files)}
    sums = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(entries.items())
    )
    entries["SHA256SUMS.txt"] = sums.encode("utf-8")

    output.mkdir(parents=True, exist_ok=True)
    package = output / f"Fonterra-Home-Assistant-{version}.zip"
    with TemporaryDirectory(dir=output) as staging:
        archive_path = Path(staging) / package.name
        with ZipFile(archive_path, "w") as archive:
            for name, data in sorted(entries.items()):
                entry = ZipInfo(name)
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, data)
        with ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP verification failed")
        archive_path.replace(package)

    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    package.with_suffix(".zip.sha256").write_text(
        f"{digest}  {package.name}\n", encoding="utf-8", newline="\n"
    )
    print(f"{digest}  {package}")


if __name__ == "__main__":
    main()
