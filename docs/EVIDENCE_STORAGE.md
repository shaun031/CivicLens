# Private evidence — Phase 4

## Limits and processing

Accept at most two nonempty JPEG/PNG/WebP input files, at most 1,572,864 bytes (1.5 MiB) each. Actual decoded dimensions are limited to 4096px per side and 4,000,000 pixels; animations/multi-frame images are rejected. The complete incoming multipart stream is limited to 3,407,872 bytes (3.25 MiB), including fields/boundaries, even if Content-Length is absent or dishonest. Text parts and part counts are bounded before parsing can spool unlimited data.

Pillow verifies and fully decodes content, checks declared MIME against actual format, applies EXIF orientation, thumbnails to at most 2048px, composites transparency over white, copies into a fresh RGB image and re-encodes JPEG. Original EXIF/GPS, ICC, comments, source filename and other metadata are not carried over. Encoded output is bounded by the same 1.5 MiB maximum. Browser checks are convenience feedback only; all security checks run on the backend. See [Pillow image handling](https://pillow.readthedocs.io/en/stable/reference/Image.html) and [orientation operations](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html).

The conservative total cap leaves room for approximately 4.33 MiB of base64 data plus proxy event overhead within the future synchronous Lambda payload envelope. Actual API Gateway/Mangum binary handling is tested locally using a v2 base64 multipart event and JPEG response; production integration overhead/time/memory still needs Phase 14 measurement. Original files are not retained as hidden backups and raw binaries never enter SQLite/DynamoDB.

## Local filesystem

Default private root is `backend/data/evidence/`, beside the configured local database. Set LOCAL_EVIDENCE_ROOT to a dedicated absolute directory when changing it; never share a root between isolated tests and the developer database. Frontend public/dist directories are forbidden. No unauthenticated StaticFiles mount exists. Git ignores backend/data and CDK excludes it entirely.

Generated keys are exactly `complaints/{complaintUUID}/{imageUUID}.jpg`. Raw names/extensions are not path authority. Keys are allowlisted before resolution. Existing symlinks and Windows junctions in configured ancestors/components are rejected. Files are created exclusively (no overwrite), with POSIX 0600 files/0700 new private directories where supported, then flushed/fsynced before metadata commit. Reads are regular-file-only and bounded; final symlink traversal is refused on systems supporting O_NOFOLLOW. Windows inherits NTFS permissions: restrict the dedicated evidence root to the developer/service account. The application is not a defense against a privileged local account concurrently replacing private directory components; protect the root with OS ownership/ACLs.

## Authorized display

Every photo request authenticates the Phase 2 principal, requires active verified CITIZEN, loads the complaint by owner, verifies image membership, then reads its server-controlled key. No citizen can access another's image by guessing UUIDs. ADMIN/OFFICER broad evidence access remains unimplemented. JSON contains only safe metadata and relative authenticated API URLs, never storage keys or local paths. Responses use image/jpeg, generated inline filenames, nosniff and private/no-store caching. The frontend fetches bytes using its authenticated cookie/bearer client, creates a temporary object URL, and revokes it on cleanup. Failed retrieval shows an unavailable-image state.

## S3 adapter (not deployed)

S3Evidence implements the same put/get/delete contract with lazy boto3 clients and validated configuration. It writes only sanitized bounded JPEG bytes with ContentType=image/jpeg, SSE-S3 AES256, private/no-store caching and IfNoneMatch=*; no public ACL is set. It bounds returned bytes, closes SDK streams, and deletes only known staged keys during recovery. The retained bucket stays private. Lambda permissions are limited to s3:GetObject/PutObject/DeleteObject on `complaints/*`, not bucket listing or unrelated objects. SDK stubs/mocks cover behavior with live SDK transport forbidden during tests.

Browser-to-S3 presigned uploads and authorized presigned downloads are possible later optimizations but are not implemented. The current protocol consistently uploads through the authenticated FastAPI backend in both provider designs. No live upload/download/presigning call was performed in AWS.

## Failure, termination and recovery

Creation stages all accepted evidence before its database transaction. Definite failures delete only that attempt's known staged keys; metadata is rolled back and no complaint is published. Validation happens before writes. Partial local write failures remove owned partial files. Existing-key collisions never delete an older object. Cleanup failures are logged by safe complaint ID/error category without a path and can leave private orphans; no false success is returned.

File/object storage and a database are not one distributed transaction. A sudden process or machine failure can leave unreferenced private files, or an unavailable referenced file after storage damage. No automatic recursive cleanup runs at startup. After stopping writers and backing up the local database/evidence together, run this **read-only** trusted local audit:

```powershell
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m app.scripts.evidence_audit --minimum-age-hours 24
```

It compares generated keys against committed complaint_images metadata and reports missing references or sufficiently old unreferenced candidates. It does not delete, move or mutate anything. Review candidates against a consistent backup and any interrupted request before manually quarantining an exact validated file; never recursively delete the storage root. Restore missing referenced objects from backup or explicitly record unavailable evidence through a future approved repair workflow. Do not fabricate replacement photos or silently remove metadata. No power-loss/disk-failure atomicity guarantee is made.

For DynamoDB transaction/network ambiguity, preserve staged S3 objects and retry the same request key. Service code checks committed idempotency state where possible. Trusted operator reconciliation and durable pending-operation retention policies must be designed/tested before public cloud use; there is no deployed reconciler and the application role intentionally cannot list a whole bucket.
