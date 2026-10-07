"""Idempotently provision object-storage buckets for local development and CI.

Replaces MinIO's ``mc`` CLI (ADR-0005): uses only the S3 API so it works against RustFS, S3 or R2.
Production buckets are provisioned by infrastructure-as-code, not by this script.
"""

import sys

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    bucket = settings.s3_bucket_documents

    try:
        s3.head_bucket(Bucket=bucket)
        print(f"bucket exists: {bucket}")  # noqa: T201 - CLI output
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        print(f"bucket created: {bucket}")  # noqa: T201

    s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    if _supports_public_access_block(s3, bucket):
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )

    if settings.cors_allowed_origins:
        s3.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": settings.cors_allowed_origins,
                        "AllowedMethods": ["GET", "PUT"],
                        "AllowedHeaders": ["*"],
                        "ExposeHeaders": ["ETag"],
                        "MaxAgeSeconds": 600,
                    }
                ]
            },
        )
    print("storage ready")  # noqa: T201
    return 0


def _supports_public_access_block(s3: object, bucket: str) -> bool:
    """Some S3-compatible stores do not implement PublicAccessBlock; buckets are private by default."""
    try:
        s3.get_public_access_block(Bucket=bucket)  # type: ignore[attr-defined]
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        return code == "NoSuchPublicAccessBlockConfiguration"
    return True


if __name__ == "__main__":
    sys.exit(main())
