"""HTTP clients for the other two services. 5-second timeout, and the
caller's JWT is forwarded (design 6.2, 11).

* JudiciaryClient.create_court_case  - the referral (write, must succeed)
* JudiciaryClient.get_court_case     - read the live court record (tracking)
* CorrectionalClient.get_inmate      - read the live custody record (tracking)
"""
import logging
from typing import Optional

import httpx

from .errors import BadGatewayError, ConflictError

log = logging.getLogger("police.clients")


class RemoteReadError(Exception):
    """A read from another service failed. The message is safe to show a user."""


def _read(http: httpx.Client, url: str, token: str, user: str, service: str) -> dict:
    try:
        resp = http.get(url, headers={"Authorization": f"Bearer {token}"})
    except httpx.TimeoutException:
        log.warning("user=%s GET %s -> timeout", user, url)
        raise RemoteReadError(f"The {service} service did not respond in time")
    except httpx.HTTPError as exc:
        log.warning("user=%s GET %s -> %s", user, url, exc.__class__.__name__)
        raise RemoteReadError(f"The {service} service is unavailable")
    log.info("user=%s GET %s -> %s", user, url, resp.status_code)
    if resp.status_code == 200:
        try:
            data = resp.json()
        except ValueError:
            raise RemoteReadError(f"The {service} service returned an unexpected response")
        if isinstance(data, dict):
            return data
        raise RemoteReadError(f"The {service} service returned an unexpected response")
    if resp.status_code == 403:
        raise RemoteReadError(f"Your role may not read {service} records")
    if resp.status_code == 404:
        raise RemoteReadError(f"The {service} service has no such record")
    raise RemoteReadError(f"The {service} service answered HTTP {resp.status_code}")


class JudiciaryClient:
    def __init__(self, base_url: str, timeout: float = 5.0, client: Optional[httpx.Client] = None):
        self.base_url = base_url.rstrip("/")
        self.http = client or httpx.Client(timeout=timeout)

    def create_court_case(self, payload: dict, token: str, user: str) -> str:
        """POST /court-cases. Returns the court_case_id.
        Raises BadGatewayError if Judiciary is unreachable or fails, so the
        caller changes nothing in its own database (NFR-03)."""
        url = f"{self.base_url}/court-cases"
        try:
            resp = self.http.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
        except httpx.TimeoutException:
            log.warning("user=%s POST %s -> timeout", user, url)
            raise BadGatewayError("The Judiciary service did not respond in time; try again later")
        except httpx.HTTPError as exc:
            log.warning("user=%s POST %s -> %s", user, url, exc.__class__.__name__)
            raise BadGatewayError("The Judiciary service is unavailable; try again later")

        log.info("user=%s POST %s -> %s", user, url, resp.status_code)

        if resp.status_code == 201:
            try:
                court_case_id = resp.json()["court_case_id"]
            except (ValueError, KeyError, TypeError):
                raise BadGatewayError("The Judiciary service returned an unexpected response")
            if not isinstance(court_case_id, str) or not court_case_id:
                raise BadGatewayError("The Judiciary service returned an unexpected response")
            return court_case_id
        if resp.status_code == 409:
            raise ConflictError("The Judiciary service already holds a court case for this police case")
        raise BadGatewayError(f"The Judiciary service rejected the referral (HTTP {resp.status_code})")

    def get_court_case(self, court_case_id: str, token: str, user: str) -> dict:
        """GET /court-cases/{id}. Raises RemoteReadError on any failure."""
        return _read(self.http, f"{self.base_url}/court-cases/{court_case_id}", token, user, "Judiciary")


class CorrectionalClient:
    def __init__(self, base_url: str, timeout: float = 5.0, client: Optional[httpx.Client] = None):
        self.base_url = base_url.rstrip("/")
        self.http = client or httpx.Client(timeout=timeout)

    def get_inmate(self, inmate_id: str, token: str, user: str) -> dict:
        """GET /inmates/{id}. Raises RemoteReadError on any failure."""
        return _read(self.http, f"{self.base_url}/inmates/{inmate_id}", token, user, "Correctional")
