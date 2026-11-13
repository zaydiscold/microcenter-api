class MicroCenterError(Exception):
    """Base for controlled client failures."""


class BlockedError(MicroCenterError):
    """The storefront denied/challenged access. Stop; do not rotate identities."""


class ParseError(MicroCenterError):
    """Unexpected storefront markup; do not present it as an empty catalog."""


class RateLimitedError(MicroCenterError):
    """Upstream rate limit; respect Retry-After before a manual retry."""

    def __init__(self, retry_after=None):
        self.retry_after = retry_after
        super().__init__(
            f"Upstream rate limited this client (Retry-After: {retry_after or 'unspecified'}); scan checkpoint retained"
        )
