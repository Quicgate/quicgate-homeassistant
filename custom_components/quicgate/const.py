"""Constants for the quicgate integration."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "quicgate"
LOGGER = logging.getLogger(__package__)

CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_NAME = "quicgate"
UPDATE_INTERVAL = timedelta(seconds=60)

# Where new versions of quicgate are announced.
RELEASES_URL = "https://api.github.com/repos/Quicgate/quicgate/releases/latest"
RELEASE_CHECK_INTERVAL = timedelta(hours=6)

# A certificate this close to its end means renewal is not working: quicgate
# renews well before this.
CERTIFICATE_SOON_DAYS = 14

# How many list entries (bans, backends) an entity carries as attributes.
MAX_LISTED = 25

# Why quicgate refused a request, in words.
BLOCK_REASONS = {
    "accessList": "access list",
    "banned": "banned address",
    "rateLimit": "rate limit",
    "exploit": "exploit filter",
    "bot": "bad bot filter",
    "clientCert": "client certificate",
    "sso": "single sign-on",
    "forwardAuth": "forward auth",
    "streamSource": "stream source filter",
}
