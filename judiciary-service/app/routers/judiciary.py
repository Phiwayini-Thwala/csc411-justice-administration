"""Court case endpoints (contract: /court-cases...)."""
from typing import Optional

from fastapi import APIRouter, Depends, status

from ..deps import (CASE_READ_ROLES, COURT_ROLES, CUSTODY_ROLES, READ_ROLES, RECEIVE_ROLES,
                    get_judiciary_service, require_roles)
from ..schemas import (BailDecision, CourtCaseCreate, CourtCaseOut, CustodyEventIn, HearingCreate, HearingOut,
                       LinkedRecords, RemandDecision, VerdictDecision)
from ..security import Principal
from ..services import JudiciaryService

router = APIRouter(tags=["Judiciary"])


@router.post("/court-cases", response_model=CourtCaseOut, status_code=status.HTTP_201_CREATED,
             summary="Receive a case referred by the Police service")
def receive_case(body: CourtCaseCreate,
                 who: Principal = Depends(require_roles(*RECEIVE_ROLES)),
                 service: JudiciaryService = Depends(get_judiciary_service)):
    return CourtCaseOut.from_case(service.receive_case(body, who))


@router.get("/court-cases", response_model=list[CourtCaseOut],
            summary="List court cases (extra endpoint used by the court UI)")
def list_cases(status: Optional[str] = None,
               _who: Principal = Depends(require_roles(*READ_ROLES)),
               service: JudiciaryService = Depends(get_judiciary_service)):
    return [CourtCaseOut.from_case(c) for c in service.list_cases(status)]


@router.get("/court-cases/{court_case_id}", response_model=CourtCaseOut,
            summary="Get a court case with hearings and decisions")
def get_case(court_case_id: str,
             _who: Principal = Depends(require_roles(*CASE_READ_ROLES)),
             service: JudiciaryService = Depends(get_judiciary_service)):
    return CourtCaseOut.from_case(service.get_case(court_case_id))


@router.post("/court-cases/{court_case_id}/hearings", response_model=HearingOut,
             status_code=status.HTTP_201_CREATED, summary="Schedule a hearing")
def schedule_hearing(court_case_id: str, body: HearingCreate,
                     who: Principal = Depends(require_roles(*COURT_ROLES)),
                     service: JudiciaryService = Depends(get_judiciary_service)):
    return HearingOut.model_validate(service.schedule_hearing(court_case_id, body, who))


@router.post("/court-cases/{court_case_id}/bail", response_model=CourtCaseOut,
             summary="Grant bail (suspect is released on conditions)")
def grant_bail(court_case_id: str, body: BailDecision,
               who: Principal = Depends(require_roles(*COURT_ROLES)),
               service: JudiciaryService = Depends(get_judiciary_service)):
    return CourtCaseOut.from_case(service.grant_bail(court_case_id, body, who))


@router.post("/court-cases/{court_case_id}/remand", response_model=CourtCaseOut,
             summary="Remand suspect in custody")
def remand(court_case_id: str, body: RemandDecision,
           who: Principal = Depends(require_roles(*COURT_ROLES)),
           service: JudiciaryService = Depends(get_judiciary_service)):
    return CourtCaseOut.from_case(service.remand(court_case_id, body, who))


@router.post("/court-cases/{court_case_id}/verdict", response_model=CourtCaseOut,
             summary="Record verdict and, if guilty, the sentence")
def verdict(court_case_id: str, body: VerdictDecision,
            who: Principal = Depends(require_roles(*COURT_ROLES)),
            service: JudiciaryService = Depends(get_judiciary_service)):
    return CourtCaseOut.from_case(service.verdict(court_case_id, body, who))


@router.get("/court-cases/{court_case_id}/linked", response_model=LinkedRecords,
            summary="Live Police case and Correctional inmate records for this court case")
def linked(court_case_id: str,
           who: Principal = Depends(require_roles(*READ_ROLES)),
           service: JudiciaryService = Depends(get_judiciary_service)):
    return service.linked(court_case_id, who)


@router.post("/court-cases/{court_case_id}/custody-events", response_model=CourtCaseOut,
             summary="Receive a transfer or release from the Correctional service")
def custody_event(court_case_id: str, body: CustodyEventIn,
                  who: Principal = Depends(require_roles(*CUSTODY_ROLES)),
                  service: JudiciaryService = Depends(get_judiciary_service)):
    return CourtCaseOut.from_case(service.record_custody_event(court_case_id, body, who))


@router.post("/court-cases/{court_case_id}/notify-police", response_model=CourtCaseOut,
             summary="Send the current court status to the Police service again")
def notify_police(court_case_id: str,
                  who: Principal = Depends(require_roles(*COURT_ROLES)),
                  service: JudiciaryService = Depends(get_judiciary_service)):
    return CourtCaseOut.from_case(service.resend_to_police(court_case_id, who))
