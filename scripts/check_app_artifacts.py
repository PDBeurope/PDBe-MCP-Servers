"""Fail packaging if an MCP App bundle is absent, empty, or stale."""

import argparse
import tarfile
import zipfile
from pathlib import Path

EXPECTED = {
    "structure-explorer.html",
    "structure-comparison.html",
    "mvs-viewer.html",
}


def check_members(artifact: Path, members: dict[str, int]) -> None:
    ui_members = {
        Path(name).name: size
        for name, size in members.items()
        if "/pdbe_mcp_server/ui/" in "/" + name and name.endswith(".html")
    }
    if set(ui_members) != EXPECTED or not all(ui_members.values()):
        raise SystemExit(
            f"{artifact.name}: expected non-empty MCP App bundles {sorted(EXPECTED)}, "
            f"found {ui_members}. Run npm ci and npm run build in apps/structure-explorer."
        )
    print(f"{artifact.name}: all MCP App resources are present")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--require-sdist", action="store_true")
    args = parser.parse_args()
    wheels = sorted(args.directory.glob("*.whl"))
    sdists = sorted(args.directory.glob("*.tar.gz"))
    if not wheels or (args.require_sdist and not sdists):
        parser.error(
            "Expected a wheel" + (" and source archive" if args.require_sdist else "")
        )
    for artifact in wheels:
        with zipfile.ZipFile(artifact) as archive:
            check_members(
                artifact, {info.filename: info.file_size for info in archive.infolist()}
            )
    for artifact in sdists:
        with tarfile.open(artifact) as archive:
            check_members(
                artifact, {info.name: info.size for info in archive if info.isfile()}
            )


if __name__ == "__main__":
    main()
