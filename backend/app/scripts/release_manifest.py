"""Generate a non-secret source/dependency inventory; does NOT certify deployment readiness."""

import argparse
import hashlib
import json
import platform
import sqlite3
import tomllib
from datetime import UTC, datetime
from importlib.metadata import distributions
from pathlib import Path


def manifest(root):
    root = Path(root).resolve()
    files = set()
    for relative in (
        "backend/app",
        "frontend/src",
        "frontend/e2e",
        "infrastructure/lib",
        "infrastructure/test",
        "scripts",
        "tests/integration",
        "backend/tests",
        "docs",
    ):
        for path in (root / relative).rglob("*"):
            if path.is_file() and path.suffix in (".py", ".ts", ".tsx", ".css", ".md", ".ps1"):
                files.add(path)
    for relative in (
        "README.md",
        "PHASE_PROGRESS.md",
        "RELEASE_NOTES.md",
        ".gitignore",
        "backend/pyproject.toml",
        "backend/requirements.txt",
        "backend/.env.example",
        "frontend/.env.example",
        "frontend/package.json",
        "frontend/package-lock.json",
        "infrastructure/package.json",
        "infrastructure/package-lock.json",
        "infrastructure/cdk.json",
        "infrastructure/tsconfig.json",
        "frontend/tsconfig.json",
        "frontend/tsconfig.app.json",
        "frontend/tsconfig.browser.json",
        "frontend/tsconfig.node.json",
        "frontend/vite.config.ts",
        "frontend/playwright.config.ts",
    ):
        if (root / relative).is_file():
            files.add(root / relative)
    source = {
        str(p.relative_to(root).as_posix()): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(files)
    }
    versions = {
        "backend": tomllib.loads((root / "backend/pyproject.toml").read_text())["project"][
            "version"
        ]
    }
    for component in ("frontend", "infrastructure"):
        versions[component] = json.loads((root / component / "package.json").read_text())["version"]
    return {
        "manifestVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "releaseCandidate": "phase13-local-validation",
        "versions": versions,
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "installedPython": sorted({f"{d.metadata['Name']}=={d.version}" for d in distributions()}),
        "files": source,
        "sourceDigest": hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest(),
        "databaseSchema": 8,
        "eventSchema": 1,
        "cloudStatus": "BLOCKED",
        "limitations": "Source inventory, NOT a Linux deployment artifact, hash-pinned "
        "installation lock, signed attestation or proof of live cloud behavior. Environment "
        "values, database contents, evidence and reset outbox deliberately excluded.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = manifest(Path(__file__).resolve().parents[3])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
    print(
        json.dumps(
            {
                "status": "PASS",
                "versions": result["versions"],
                "files": len(result["files"]),
                "cloudStatus": "BLOCKED",
            }
        )
    )


if __name__ == "__main__":
    main()
