"""Direct public JSON catalog client, with a separately named storefront fallback."""

from .discovery import DiscoveryClient as Client
from .client import Client as StorefrontClient
from .errors import MicroCenterError, BlockedError, ParseError

__all__ = [
    "Client",
    "StorefrontClient",
    "MicroCenterError",
    "BlockedError",
    "ParseError",
]
__version__ = "0.1.0"
