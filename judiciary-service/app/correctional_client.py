"""HTTP clients for the other two services. 5-second timeout, and the
caller's JWT is forwarded (design 6.2, 11).

CorrectionalClient (writes): every method raises BadGatewayError when the
Correctional service is unreachable or fails, so the caller saves nothing in
its own database (design 11: fail without partial updates).

PoliceClient (feedback): tells the Police service what the court decided.
This is best effort: the court decision is already saved, so a Police outage
must not undo it. The result is stored on the court case (police_sync) and
the court officer can resend it later.
"""
import logging
from typing import Optional

import httpx

from .errors import BadGatewayError, ConflictError

log = logging.getLogger("judiciary.clients")

# Sent on every call we make, so the other service knows the request came
# from the Judiciary and does not notify us back about our own decision.
ORIGIN = {"X-Origin-Service": "judiciary"}


class RemoteReadError(Exception):
    """A read from another service failed. The message is safe to show a user."""


def _read(http: httpx.Client, url: str, token: str, user: str, service: str) -> dict:
    try:
        resp = http.get(url, headers={"Authorization": f"Bearer {token}", **ORIGIN})
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


class CorrectionalClient:
    def __init__(self, base_url: str, timeout: float = 5.0, client: Optional[httpx.Client] = None):
        self.base_url = base_url.rstrip("/")
        self.http = client or httpx.Client(timeout=timeout)

    # ----- plumbing -----
    def _call(self, method: str, path: str, token: str, user: str, body: dict) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            resp = self.http.request(method, url, json=body,
                                     headers={"Authorization": f"Bearer {token}", **ORIGIN})
        except httpx.TimeoutException:
            log.warning("user=%s %s %s -> timeout", user, method, url)
            raise BadGatewayError("The Correctional service did not respond in time; try again later")
        except httpx.HTTPError as exc:
            log.warning("user=%s %s %s -> %s", user, method, url, exc.__class__.__name__)
            raise BadGatewayError("The Correctional service is unavailable; try again later")
        log.info("user=%s %s %s -> %s", user, method, url, resp.status_code)
        return resp

    @staticmethod
    def _message(resp: httpx.Response) -> str:
        try:
            return str(resp.json().get("message", ""))
        except (ValueError, AttributeError):
            return ""

    def _fail(self, resp: httpx.Response, what: str):
        detail = self._message(resp)
        if resp.status_code == 409:      # e.g. court case already has an inmate / inmate already released
            raise ConflictError(f"Correctional service refused the {what}: {detail or 'conflict'}")
        raise BadGatewayError(
            f"The Correctional service rejected the {what} (HTTP {resp.status_code})"
            + (f": {detail}" if detail else ""))

    # ----- operations (design 5.4) -----
    def admit(self, payload: dict, token: str, user: str) -> str:
        """POST /inmates -> inmate_id"""
        resp = self._call("POST", "/inmates", token, user, payload)
        if resp.status_code != 201:
            self._fail(resp, "admission")
        try:
            inmate_id = resp.json()["inmate_id"]
        except (ValueError, KeyError, TypeError):
            raise BadGatewayError("The Correctional service returned an unexpected response")
        if not isinstance(inmate_id, str) or not inmate_id:
            raise BadGatewayError("The Correctional service returned an unexpected response")
        return inmate_id

    def set_convicted(self, inmate_id: str, sentence_months: int, token: str, user: str) -> None:
        """PUT /inmates/{id}/status -> CONVICTED"""
        resp = self._call("PUT", f"/inmates/{inmate_id}/status", token, user,
                          {"status": "CONVICTED", "sentence_months": sentence_months})
        if resp.status_code != 200:
            self._fail(resp, "status update")

    def release(self, inmate_id: str, reason: str, notes: Optional[str], token: str, user: str) -> None:
        """POST /inmates/{id}/release (ACQUITTED, BAIL_GRANTED or COURT_ORDER)"""
        body = {"reason": reason}
        if notes:
            body["notes"] = notes
        resp = self._call("POST", f"/inmates/{inmate_id}/release", token, user, body)
        if resp.status_code != 200:
            self._fail(resp, "release order")

    def get_inmate(self, inmate_id: str, token: str, user: str) -> dict:
        """GET /inmates/{id} (linked-records view). Raises RemoteReadError."""
        return _read(self.http, f"{self.base_url}/inmates/{inmate_id}", token, user, "Correctional")


class PoliceClient:
    def __init__(self, base_url: str, timeout: float = 5.0, client: Optional[httpx.Client] = None):
        self.base_url = base_url.rstrip("/")
        self.http = client or httpx.Client(timeout=timeout)

    def send_court_update(self, police_case_id: str, payload: dict, token: str, user: str) -> tuple[bool, str]:
        """POST /cases/{id}/court-updates. Never raises: returns (ok, message)."""
        url = f"{self.base_url}/cases/{police_case_id}/court-updates"
        try:
            resp = self.http.post(url, json=payload, headers={"Authorization": f"Bearer {token}", **ORIGIN})
        except httpx.TimeoutException:
            log.warning("user=%s POST %s -> timeout", user, url)
            return False, "The Police service did not respond in time"
        except httpx.HTTPError as exc:
            log.warning("user=%s POST %s -> %s", user, url, exc.__class__.__name__)
            return False, "The Police service is unavailable"
        log.info("user=%s POST %s -> %s", user, url, resp.status_code)
        if resp.status_code == 200:
            return True, "Police case updated"
        try:
            detail = str(resp.json().get("message", ""))
        except (ValueError, AttributeError):
            detail = ""
        return False, f"The Police service answered HTTP {resp.status_code}" + (f": {detail}" if detail else "")

    def get_case(self, police_case_id: str, token: str, user: str) -> dict:
        """GET /cases/{id} (linked-records view). Raises RemoteReadError."""
        return _read(self.http, f"{self.base_url}/cases/{police_case_id}", token, user, "Police")
