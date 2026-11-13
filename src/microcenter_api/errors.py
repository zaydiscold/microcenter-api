class MicroCenterError(Exception):
    """Base for controlled client failures."""


class BlockedError(MicroCenterError):
    """Access was denied. A 403 alone does not establish a browser challenge."""

    def __init__(self, message, *, status=None, challenge_detected=None):
        self.status = status
        self.challenge_detected = challenge_detected
        super().__init__(message)


class ParseError(MicroCenterError):
    """Unexpected storefront markup; do not present it as an empty catalog."""


class RateLimitedError(MicroCenterError):
    """Upstream rate limit; respect Retry-After before a manual retry."""

    def __init__(self, retry_after=None):
        self.retry_after = retry_after
        super().__init__(
            f"Upstream rate limited this client (Retry-After: {retry_after or 'unspecified'}); scan checkpoint retained"
        )
