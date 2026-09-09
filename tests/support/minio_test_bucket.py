"""Safety guards for fixture-owned MinIO buckets."""

import re


class UnsafeTestBucketError(RuntimeError):
    """Raised before cleanup when a MinIO bucket is not proven disposable."""


def assert_disposable_bucket_name(
    bucket_name: str,
    *,
    expected_prefix: str,
    owned_bucket_name: str | None = None,
) -> None:
    """Reject buckets outside the fixture-owned prefix and UUID contract."""
    if not re.fullmatch(r"[a-z0-9]+-test-", expected_prefix):
        raise UnsafeTestBucketError("test bucket prefix is invalid")
    normalized = bucket_name.strip().lower()
    if not normalized.startswith(expected_prefix):
        raise UnsafeTestBucketError(
            f"bucket must start with the test prefix {expected_prefix!r}"
        )
    suffix = normalized.removeprefix(expected_prefix)
    if not re.fullmatch(r"[0-9a-f]{32}", suffix):
        raise UnsafeTestBucketError("bucket name must end with a generated UUID")
    if owned_bucket_name is not None and normalized != owned_bucket_name:
        raise UnsafeTestBucketError("refusing to remove a bucket not owned by this fixture")
