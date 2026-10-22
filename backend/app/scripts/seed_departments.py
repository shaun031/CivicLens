"""Explicit, idempotent local configuration seed; never provisions accounts or contacts AWS."""

import argparse
import json
from uuid import uuid4

from app.core.config import get_settings
from app.main import create_app
from app.models.incident import Actor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-demo-configuration", action="store_true", required=True)
    args = parser.parse_args()
    settings = get_settings()
    if settings.complaint_provider != "sqlite" or settings.auth_provider != "local":
        parser.error("Local SQLite mode is required; cloud transport is forbidden")
    app = create_app(settings)
    app.state.auth_service.store.initialize()
    print(
        json.dumps(
            app.state.work_service.repository.seed(
                {
                    "operationId": str(uuid4()),
                    "reason": "Trusted local operator seeded editable demonstration departments",
                    "confirmed": args.confirm_demo_configuration,
                },
                Actor("local-department-seed", "ADMIN"),
            )
        )
    )


if __name__ == "__main__":
    main()
