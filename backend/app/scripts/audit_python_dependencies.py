"""OPT-IN internet advisory check against PyPI JSON, not AWS. No packages are installed."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib.metadata import distributions
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def check(package):
    name, version = package
    url = f"https://pypi.org/pypi/{quote(name, safe='')}/{quote(version, safe='')}/json"
    try:
        request = Request(url, headers={"User-Agent": "CivicLens-phase13-advisory-check"})
        with urlopen(request, timeout=10) as response:
            content = response.read(2097153)
        if len(content) > 2097152:
            raise ValueError("Advisory response bound exceeded")
        result = json.loads(content)
        advisories = result["vulnerabilities"]
        if not isinstance(advisories, list):
            raise ValueError("Advisories unavailable")
        active = [a for a in advisories if not a.get("withdrawn")]
        return {
            "name": name,
            "version": version,
            "status": "FAIL" if active else "PASS",
            "advisories": [
                {
                    "id": a.get("id"),
                    "aliases": a.get("aliases", []),
                    "link": a.get("link"),
                    "fixedIn": a.get("fixed_in", []),
                }
                for a in active
            ],
        }
    except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError) as error:
        return {
            "name": name,
            "version": version,
            "status": "NOT_VERIFIED",
            "reason": type(error).__name__,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-pypi-network", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packages = sorted(
        {
            (d.metadata["Name"], d.version)
            for d in distributions()
            if d.metadata["Name"].lower() != "civiclens-api"
        }
    )
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(check, packages))
    status = (
        "FAIL"
        if any(r["status"] == "FAIL" for r in results)
        else ("NOT_VERIFIED" if any(r["status"] == "NOT_VERIFIED" for r in results) else "PASS")
    )
    report = {
        "status": status,
        "checkedAt": datetime.now(UTC).isoformat(),
        "packages": results,
        "source": "https://docs.pypi.org/api/json/",
        "limitations": "PyPI published release advisories only; not proof of no unknown flaws "
        "or malware. Local CivicLens package excluded, source-audited.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print(json.dumps(report))
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
