"""Keep dependency diagnostics from leaking OAuth material or webhook URLs."""

import logging


class _PrivateTransport(logging.Filter):
    def filter(self, record):
        # Spotipy DEBUG includes bearer headers, PKCE verifiers and refresh tokens.
        # Emit our sanitized user-facing errors instead of transport payloads.
        return False


_FILTER = _PrivateTransport()


def protect_transport_logs():
    for name in (
        "spotipy.client",
        "spotipy.oauth2",
        "spotipy.cache_handler",
        "urllib3.connectionpool",
        "urllib3.util.retry",
    ):
        logger = logging.getLogger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)
