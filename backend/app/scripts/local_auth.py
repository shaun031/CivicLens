import argparse
import json

from app.core.config import get_settings
from app.services.auth_service import AuthService


def main() -> None:
    parser = argparse.ArgumentParser(description="Local authentication database tools")
    parser.add_argument("command", choices=["init", "outbox"])
    args = parser.parse_args()
    settings = get_settings()
    if settings.app_env != "local" or settings.auth_provider != "local":
        parser.error("Local authentication tools require APP_ENV=local and local authentication")
    service = AuthService(settings)
    service.store.initialize()
    if args.command == "init":
        print("Shared local schema v3 initialized safely (existing accounts/complaints preserved).")
    else:
        directory = settings.local_db_path.parent / "outbox"
        for path in sorted(directory.glob("*.json")):
            entry = json.loads(path.read_text(encoding="utf-8"))
            print(f"{entry['email']}: {entry['reset_url']}")
        print("Private development outbox only. Expired/used links are rejected by the API.")


if __name__ == "__main__":
    main()
