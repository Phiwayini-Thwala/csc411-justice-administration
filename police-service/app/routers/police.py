"""Router layer for suspects, arrests, cases, charges and referral.
Endpoints only validate input, check the role and call the service layer."""
from fastapi import APIRouter, Depends

from ..deps import READ_ROLES, WRITE_ROLES, get_police_service, require_roles
from ..schemas import (
    ArrestCreate, ArrestOut, CaseCreate, CaseOut, ChargeCreate, ChargeOut, SuspectCreate, SuspectOut,
)
from ..security import Principal
from ..services import PoliceService

router = APIRouter(tags=["police"])

writer = require_roles(*WRITE_ROLES)
reader = require_roles(*READ_ROLES)


@router.post("/suspects", response_model=SuspectOut, status_code=201)
def create_suspect(
    body: SuspectCreate,
    who: Principal = Depends(writer),
    service: PoliceService = Depends(get_police_service),
):
    return service.register_suspect(body, who)


@router.get("/suspects/{suspect_id}", response_model=SuspectOut)
def get_suspect(
    suspect_id: str,
    who: Principal = Depends(reader),
    service: PoliceService = Depends(get_police_service),
):
    return service.get_suspect(suspect_id)


@router.post("/arrests", response_model=ArrestOut, status_code=201)
def create_arrest(
    body: ArrestCreate,
    who: Principal = Depends(writer),
    service: PoliceService = Depends(get_police_service),
):
    return service.record_arrest(body, who)


@router.post("/cases", response_model=CaseOut, status_code=201)
def create_case(
    body: CaseCreate,
    who: Principal = Depends(writer),
    service: PoliceService = Depends(get_police_service),
):
    return service.create_case(body.arrest_id, who)


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(
    case_id: str,
    who: Principal = Depends(reader),
    service: PoliceService = Depends(get_police_service),
):
    return service.get_case(case_id)


@router.post("/cases/{case_id}/charges", response_model=ChargeOut, status_code=201)
def add_charge(
    case_id: str,
    body: ChargeCreate,
    who: Principal = Depends(writer),
    service: PoliceService = Depends(get_police_service),
):
    return service.add_charge(case_id, body, who)


@router.post("/cases/{case_id}/refer", response_model=CaseOut)
def refer_case(
    case_id: str,
    who: Principal = Depends(writer),
    service: PoliceService = Depends(get_police_service),
):
    return service.refer_case(case_id, who)
