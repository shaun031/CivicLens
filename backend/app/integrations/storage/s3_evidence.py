from botocore.exceptions import BotoCoreError, ClientError

from app.integrations.storage.base import StorageCollision, StorageUnavailable, validate_key


class S3Evidence:
    def __init__(self, bucket: str, max_bytes: int, client=None):
        if not bucket:
            raise ValueError("EVIDENCE_BUCKET_NAME is required for S3")
        self.bucket, self.max_bytes, self._client = bucket, max_bytes, client

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                config=Config(
                    connect_timeout=3,
                    read_timeout=5,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        return self._client

    def put(self, key: str, data: bytes) -> None:
        validate_key(key)
        if not data or len(data) > self.max_bytes:
            raise StorageUnavailable("Invalid evidence size")
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType="image/jpeg",
                ServerSideEncryption="AES256",
                CacheControl="private, no-store",
                IfNoneMatch="*",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] in ("PreconditionFailed", "412"):
                raise StorageCollision from error
            raise StorageUnavailable from error
        except BotoCoreError as error:
            raise StorageUnavailable from error

    def get(self, key: str) -> bytes:
        validate_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            stream = response["Body"]
            try:
                if (
                    response.get("ContentType") != "image/jpeg"
                    or response.get("ContentLength", 0) > self.max_bytes
                ):
                    raise StorageUnavailable
                data = stream.read(self.max_bytes + 1)
            finally:
                stream.close()
            if len(data) > self.max_bytes:
                raise StorageUnavailable
            return data
        except (ClientError, BotoCoreError, OSError) as error:
            raise StorageUnavailable from error

    def delete(self, key: str) -> None:
        validate_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as error:
            raise StorageUnavailable from error
