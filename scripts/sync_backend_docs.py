#!/usr/bin/env python3
"""Copy backend MkDocs pages into a frontend MkDocs project.

The frontend mkdocs.yml remains the final source of truth. This script only
replaces the block between two explicit markers so frontend navigation changes
outside that block are preserved.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DEFAULT_START_MARKER = "  # BEGIN BACKEND DOCS"
DEFAULT_END_MARKER = "  # END BACKEND DOCS"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def copy_backend_docs(source_docs: Path, target_docs: Path) -> None:
    target_docs.mkdir(parents=True, exist_ok=True)

    for source in source_docs.glob("*.md"):
        shutil.copy2(source, target_docs / source.name)


def indented_backend_nav(nav_fragment: Path) -> list[str]:
    lines = read_text(nav_fragment).splitlines()
    return [f"  {line}" if line else "" for line in lines]


def replace_marked_block(
    mkdocs_content: str,
    replacement_lines: list[str],
    start_marker: str,
    end_marker: str,
) -> str:
    lines = mkdocs_content.splitlines()

    try:
        start_index = lines.index(start_marker)
        end_index = lines.index(end_marker)
    except ValueError as exc:
        raise SystemExit(
            "Impossible de trouver les marqueurs dans mkdocs.yml.\n"
            "Ajoute ce bloc sous `nav:` dans le mkdocs.yml frontend :\n\n"
            f"{start_marker}\n"
            f"{end_marker}\n"
        ) from exc

    if end_index <= start_index:
        raise SystemExit("Les marqueurs backend du mkdocs.yml sont dans le mauvais ordre.")

    new_lines = (
        lines[: start_index + 1]
        + replacement_lines
        + lines[end_index:]
    )
    return "\n".join(new_lines) + "\n"


def sync(frontend_root: Path, backend_root: Path, target_subdir: str) -> None:
    source_docs = backend_root / "docs"
    nav_fragment = source_docs / "backend-nav.yml"
    target_docs = frontend_root / "docs" / target_subdir
    frontend_mkdocs = frontend_root / "mkdocs.yml"

    if not frontend_mkdocs.exists():
        raise SystemExit(f"Fichier introuvable: {frontend_mkdocs}")

    if not nav_fragment.exists():
        raise SystemExit(f"Fragment de navigation introuvable: {nav_fragment}")

    copy_backend_docs(source_docs, target_docs)

    content = read_text(frontend_mkdocs)
    updated = replace_marked_block(
        content,
        indented_backend_nav(nav_fragment),
        DEFAULT_START_MARKER,
        DEFAULT_END_MARKER,
    )
    write_text(frontend_mkdocs, updated)

    print(f"Documentation backend copiee dans {target_docs}")
    print(f"Navigation backend synchronisee dans {frontend_mkdocs}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronise la doc MkDocs backend vers un projet MkDocs frontend.",
    )
    parser.add_argument(
        "frontend_root",
        type=Path,
        help="Chemin vers le repo frontend qui contient mkdocs.yml et docs/.",
    )
    parser.add_argument(
        "--backend-root",
        type=Path,
        default=project_root(),
        help="Chemin vers le repo backend. Par defaut: racine du script.",
    )
    parser.add_argument(
        "--target-subdir",
        default="backend",
        help="Sous-dossier de docs/ dans le frontend. Par defaut: backend.",
    )
    args = parser.parse_args()

    sync(
        frontend_root=args.frontend_root.resolve(),
        backend_root=args.backend_root.resolve(),
        target_subdir=args.target_subdir.strip("/"),
    )


if __name__ == "__main__":
    main()
