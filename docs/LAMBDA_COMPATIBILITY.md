# Lambda compatibility assessment — BLOCKED, offline only

Local verified runtime: Python3.13.2 Windows x64, Node22.20.0; CDK runtime:
Python3.13 Linux x86_64. Backend/SPA/infrastructure version remains0.1.0. FastAPI uses
the same factory through `app.lambda_handler.handler` (Mangum, lifespan OFF) and API
Gateway HTTP v2 integration. Health event/import-without-network fixtures pass;
this does NOT prove the complete deployed authentication/upload/processing flow.

Native runtime dependencies include Pillow, numpy, scipy, scikit-learn,
cryptography, cffi/Argon2, pydantic-core and optional uvicorn accelerators. Their
Windows `.pyd`/DLL wheels must never be copied into Lambda. The CDK asset deliberately
contains application source, not a deployable runtime. No Docker/WSL was required.

## Required packaging strategy (not executed)

Use a pinned Linux CI runner for Python3.13/x86_64 compatible with the Lambda Amazon
Linux runtime, resolve/pin the *runtime* dependency closure, verify wheel hashes,
and record an artifact manifest. Obtain compatible binary wheels only; fail if a
matching ABI/platform wheel is unavailable. A developer-side wheel selection probe
can use `pip download --platform manylinux2014_x86_64 --python-version 3.13
--implementation cp --abi cp313 --only-binary=:all:` with a reviewed pinned runtime
requirements file. This is a strategy, not a supplied working command: certain
packages may require a different manylinux tag and must be verified against the
actual target glibc/runtime. Do not silently build from Windows source distributions.

In Linux CI, import the app, Pillow/EXIF path, Argon2/crypto/JWT and matching/text/image
engines; exercise Mangum JSON and base64 multipart events with mocked persistence;
measure cold/warm memory/time and compressed/uncompressed artifact size. Dependencies
may exceed Lambda's permitted artifact limits; splitting into layers does not bypass
the aggregate unzipped package limit. No deployment-approved dependency lock, Linux
artifact or Lambda import/cold-start benchmark is currently certified.

AWS official instructions require compatible Linux binaries, architecture/runtime
and dependency packaging; see [Python packaging](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html)
and [cross-platform recipe](https://docs.aws.amazon.com/powertools/python/latest/build_recipes/cross-platform/).

## Payload and timeout assessment

API request body maximum3,407,872bytes (~3.25MiB). Base64 expands it to about4.54MB
before the v2 JSON envelope, below the documented6MB synchronous Lambda payload
limit under bounded normal headers/envelope. API Gateway's documented10MB maximum
is not the effective end-to-end Lambda upload limit. Protected JPEG responses
<=1.5MiB similarly require binary/base64 verification. This is arithmetic, NOT a
live maximum-size transport test. The existing
`test_http_api_v2_binary_multipart_and_evidence_response` exercises a small real
base64 multipart request and JPEG binary response through Mangum/local persistence;
it does not establish maximum-size/cloud/native compatibility. Add maximum-envelope
boundary and deployed smoke checks before declaring cloud evidence upload ready.
[Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html),
[Gateway quotas](https://docs.aws.amazon.com/general/latest/gr/apigateway.html).

API15s/256MB and Step30s/512MB are unprofiled source settings. Native sklearn imports,
image decoding and recurrence candidate loops can exceed them even if local requests
are fast. State-machine5min, consumer90s, queue visibility600s are structurally
compatible but not capacity-tested. No production latency/throughput claim is made.
