"""Disposable 1,000-record CPU/storage benchmark, never opens configured user data."""

import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.core.config import Settings
from app.repositories.auth_store import AuthStore
from app.scripts.benchmark_phase5 import seed
from app.scripts.evaluate_matching import synthetic_image
from app.services.complaint_factory import build_complaint_service
from app.services.duplicate_detection_service import build_duplicate_service


def benchmark(count=1000):
    with TemporaryDirectory(prefix="civiclens-phase6-") as folder:
        settings = Settings(_env_file=None, app_env="test", local_db_path=Path(folder) / "bench.db")
        store = AuthStore(settings.local_db_path)
        store.initialize()
        seed(store, count)
        with store.connection() as db:
            source = db.execute("SELECT complaint_id FROM complaints WHERE rowid=1").fetchone()[0]
            # Dense eligible PRIVATE region exercises bounded/truncated internal selection.
            db.execute(
                "UPDATE complaints SET latitude=12.97,longitude=77.59,category='POTHOLE',"
                "status='SUBMITTED' WHERE rowid<=200"
            )
            plan = [
                row[3]
                for row in db.execute(
                    "EXPLAIN QUERY PLAN SELECT complaint_id FROM "
                    "complaints INDEXED BY complaints_internal_geography "
                    "WHERE latitude BETWEEN 12.969 AND 12.971 LIMIT 101"
                )
            ]
        service = build_duplicate_service(settings, build_complaint_service(settings, store))
        # Small sanitized synthetic JPEGs exercise real private storage and fingerprint caching.
        with store.connection() as db:
            for row in db.execute("SELECT complaint_id,created_at FROM complaints WHERE rowid<=10"):
                image_id = str(uuid4())
                key = f"complaints/{row[0]}/{image_id}.jpg"
                content = synthetic_image()
                service.storage.put(key, content)
                db.execute(
                    "INSERT INTO complaint_images VALUES(?,?,?,?,?,?)",
                    (image_id, row[0], key, "image/jpeg", len(content), row[1]),
                )
        runs = []
        for _ in range(6):
            service.repository.enqueue(source)
            runs.append(service.process_one(source))
        return {
            "syntheticOnly": True,
            "records": count,
            "candidateBound": 100,
            "cold": runs[0],
            "warmMedianMs": {
                key: round(median(run["timings"][key] for run in runs[1:]), 3)
                for key in runs[0]["timings"]
            },
            "compared": runs[-1]["compared"],
            "truncated": runs[-1]["queryTruncated"],
            "queryPlan": plan,
            "images": 10,
            "limitations": "One CPU, serial SQLite, 10 small synthetic JPEGs with warm caching. "
            "Not representative full-resolution image or AWS latency.",
        }


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
