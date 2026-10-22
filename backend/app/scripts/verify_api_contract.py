"""Compare real FastAPI OpenAPI routes with a locally synthesized CloudFormation template."""

import argparse
import itertools
import json
import re
from pathlib import Path


def normalized(path):
    return re.sub(r"\{[^}]+\}", "{}", path)


def operations(spec):
    values = set()
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method.upper() not in ("GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS", "HEAD"):
                continue
            variants = [path]
            for parameter in operation.get("parameters", []):
                schema = parameter.get("schema", {})
                if parameter["in"] == "path" and "enum" in schema:
                    variants = [
                        p.replace("{" + parameter["name"] + "}", str(value))
                        for p, value in itertools.product(variants, schema["enum"])
                    ]
            values.update(f"{method.upper()} {normalized(p)}" for p in variants)
    return values


def compare(spec, template):
    api = operations(spec)
    resources = template["Resources"].values()
    routes = {
        normalized(r["Properties"]["RouteKey"])
        for r in resources
        if r["Type"] == "AWS::ApiGatewayV2::Route"
    }
    # Cognito owns production registration/reset/login; local-only endpoints are absent in cloud.
    missing = sorted(api - routes)
    extra = sorted(routes - api)
    return {
        "status": "FAIL" if missing or extra else "PASS",
        "openApiOperations": len(api),
        "cloudRoutes": len(routes),
        "missingCloudRoutes": missing,
        "missingApiRoutes": extra,
    }


def main():
    from app.core.config import Settings
    from app.main import create_app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    args = parser.parse_args()
    settings = Settings(
        _env_file=None,
        app_env="aws",
        debug=False,
        cors_origins=[],
        cognito_issuer="https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_Offline",
        cognito_client_id="offlineclient",
        cognito_domain="https://offline.auth.ap-south-1.amazoncognito.com",
        complaints_table_name="offline-complaints",
        evidence_bucket_name="offline-evidence",
    )
    spec = create_app(settings).openapi()
    result = compare(spec, json.loads(args.template.read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
