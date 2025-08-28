"""OAuth helper for Google APIs.

Provides a minimal local webserver OAuth flow using `google-auth` and
`google-auth-oauthlib` InstalledAppFlow. Saves credentials to a file and
handles token refresh via the library.

Security note: store credentials files with restrictive filesystem permissions
(600) and avoid committing them to source control.

Usage example:

from helpers.oauth_helper import run_local_oauth_flow
SCOPES = ["https://www.googleapis.com/auth/calendar"]
creds = run_local_oauth_flow("/path/to/client_secrets.json", SCOPES, "/path/to/token.json")

Requirements:
- Create OAuth 2.0 Client ID in Google Cloud Console (Desktop or Web application).
- Set redirect URIs to http://localhost:PORT/ or use the default installed app flow.
- Download client_secrets.json and pass its path to `run_local_oauth_flow`.

"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

try:  # optional imports
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    _HAS_GOOGLE = True
except Exception:  # pragma: no cover - optional dependencies
    # Provide minimal fallbacks to avoid import errors during static tests
    InstalledAppFlow = None  # type: ignore
    Credentials = None  # type: ignore
    Request = None  # type: ignore
    _HAS_GOOGLE = False


def _ensure_dir_for_file(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def run_local_oauth_flow(client_secrets_file: str, scopes: Iterable[str], credentials_path: str, host: str = "localhost", port: int = 8080):
    """Run an InstalledAppFlow local server flow and save credentials to a file.

    - client_secrets_file: path to the downloaded client_secret.json from GCP
    - scopes: iterable of OAuth scopes
    - credentials_path: output path where credentials will be saved (JSON)
    - host/port: local redirect host/port for the flow

    Returns google.oauth2.credentials.Credentials on success.

    Example:
        creds = run_local_oauth_flow("client_secrets.json", ["https://www.googleapis.com/auth/calendar"], "~/.credentials/calendar-token.json")

    Notes on Google Cloud Console configuration:
    - Create OAuth 2.0 Client ID (choose Desktop app or Web application).
    - If using a Web application client, add redirect URI: http://localhost:8080/
    - If using a Desktop client, InstalledAppFlow will handle loopback automatically.

    If google libraries are not installed, raises RuntimeError.
    """
    if not _HAS_GOOGLE:
        raise RuntimeError("Google auth libraries are not installed. Install google-auth, google-auth-oauthlib.")

    client_secrets_file = os.path.expanduser(client_secrets_file)
    credentials_path = os.path.expanduser(credentials_path)

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, scopes=scopes)
    # Use the local server flow which opens the browser and listens for the redirect
    logger.info("Starting local OAuth flow on %s:%s", host, port)
    creds = flow.run_local_server(host=host, port=port)

    # Persist credentials to file with restrictive permissions
    _ensure_dir_for_file(credentials_path)
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    # Save raw credentials JSON; the google lib can rehydrate from this
    with open(credentials_path, "w") as fh:
        json.dump(data, fh)
    try:
        os.chmod(credentials_path, 0o600)
    except Exception:
        logger.debug("Could not set restrictive permissions on %s", credentials_path)

    return creds


def load_credentials(credentials_path: str, scopes: Optional[Iterable[str]] = None):
    """Load credentials from file and refresh if needed.

    Returns google.oauth2.credentials.Credentials instance if available, otherwise None.
    """
    if not _HAS_GOOGLE:
        raise RuntimeError("Google auth libraries are not installed. Install google-auth, google-auth-oauthlib.")

    credentials_path = os.path.expanduser(credentials_path)
    if not os.path.exists(credentials_path):
        return None

    with open(credentials_path, "r") as fh:
        data = json.load(fh)

    creds = Credentials(token=data.get("token"), refresh_token=data.get("refresh_token"), token_uri=data.get("token_uri"), client_id=data.get("client_id"), client_secret=data.get("client_secret"), scopes=list(scopes) if scopes else data.get("scopes"))

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token and Request:
        try:
            creds.refresh(Request())
            # persist refreshed token
            _ensure_dir_for_file(credentials_path)
            with open(credentials_path, "w") as fh:
                json.dump({
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": list(creds.scopes) if creds.scopes else [],
                }, fh)
        except Exception:
            logger.exception("Failed to refresh credentials")
    return creds
