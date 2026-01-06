from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Sequence


@dataclass(frozen=True)
class BuildResult:
    output_dir: Path


def build_site(
    repo_root: Path,
    *,
    hugo_binary: str = "hugo",
    hugo_args: Sequence[str] = ("--minify",),
    output_dir: Path = Path("public"),
    clean: bool = True,
) -> BuildResult:
    output_dir = output_dir if output_dir.is_absolute() else (repo_root / output_dir)
    resources_dir = repo_root / "resources"

    if clean:
        shutil.rmtree(output_dir, ignore_errors=True)
        shutil.rmtree(resources_dir, ignore_errors=True)

    cmd = [hugo_binary, *hugo_args, "-d", str(output_dir)]
    subprocess.run(cmd, cwd=repo_root, check=True)
    return BuildResult(output_dir=output_dir)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build Hugo site to public/ (for canonical extraction).")
    parser.add_argument("--repo-root", default=".", help="Repository root (default: .)")
    parser.add_argument("--output-dir", default="public", help="Hugo output directory (default: public)")
    parser.add_argument("--no-clean", action="store_true", help="Do not delete output/resources before build")
    args = parser.parse_args()

    build_site(
        Path(args.repo_root).resolve(),
        output_dir=Path(args.output_dir),
        clean=not args.no_clean,
    )

