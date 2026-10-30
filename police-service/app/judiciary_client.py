"""HTTP client for the Judiciary service (the only service Police call).
Uses a 5-second timeout and forwards the caller's JWT (design 6.2, 11)."""
import logging
from typing import Optional

import httpx

from .errors import BadGatewayError, ConflictError

log = logging.getLogger("police.judiciary")


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
