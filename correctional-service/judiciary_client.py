"""HTTP client for the Judiciary service (5-second timeout, forwards the
caller's JWT, design 6.2 and 11).

* notify_custody_event - tell the court about a transfer or release. Best
  effort: our own change is already saved, so a Judiciary outage must not undo
  it. The result is stored on the inmate (court_sync) and can be resent.
* get_court_case       - read the court record behind an inmate (linked view).
"""
import logging
import os
from typing import Optional

import httpx

log = logging.getLogger("correctional.judiciary")

JUDICIARY_URL = os.getenv("JUDICIARY_URL", "http://localhost:8002").rstrip("/")
TIMEOUT = 5.0
ORIGIN = {"X-Origin-Service": "correctional"}

_http = httpx.Client(timeout=TIMEOUT)


def set_http_client(client: httpx.Client) -> None:
    """Used by the tests to replace the Judiciary with a mock transport."""
    global _http
    _http = client


def notify_custody_event(court_case_id: str, payload: dict, token: str, user: str) -> tuple[bool, str]:
    url = f"{JUDICIARY_URL}/court-cases/{court_case_id}/custody-events"
    try:
        resp = _http.post(url, json=payload, headers={"Authorization": f"Bearer {token}", **ORIGIN})
    except httpx.TimeoutException:
        log.warning("user=%s POST %s -> timeout", user, url)
        return False, "The Judiciary service did not respond in time"
    except httpx.HTTPError as exc:
        log.warning("user=%s POST %s -> %s", user, url, exc.__class__.__name__)
        return False, "The Judiciary service is unavailable"
    log.info("user=%s POST %s -> %s", user, url, resp.status_code)
    if resp.status_code == 200:
        return True, "Court record updated"
    try:
        detail = str(resp.json().get("message", ""))
    except (ValueError, AttributeError):
        detail = ""
    return False, f"The Judiciary service answered HTTP {resp.status_code}" + (f": {detail}" if detail else "")


def get_court_case(court_case_id: str, token: str, user: str) -> tuple[Optional[dict], Optional[str]]:
    """Returns (court_case, None) or (None, error message)."""
    url = f"{JUDICIARY_URL}/court-cases/{court_case_id}"
    try:
        resp = _http.get(url, headers={"Authorization": f"Bearer {token}", **ORIGIN})
    except httpx.TimeoutException:
        return None, "The Judiciary service did not respond in time"
    except httpx.HTTPError:
        return None, "The Judiciary service is unavailable"
    log.info("user=%s GET %s -> %s", user, url, resp.status_code)
    if resp.status_code == 200:
        try:
            data = resp.json()
        except ValueError:
            return None, "The Judiciary service returned an unexpected response"
        return (data, None) if isinstance(data, dict) else (None, "Unexpected response from the Judiciary")
    if resp.status_code == 403:
        return None, "Your role may not read court records"
    if resp.status_code == 404:
        return None, "The Judiciary service has no such court case"
    return None, f"The Judiciary service answered HTTP {resp.status_code}"
