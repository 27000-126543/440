from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.dispatch import (
    TrainDispatchResponse,
    TrainDispatchCreate,
    BrakeTestRequest,
)
from app.services.dispatch_service import (
    create_train_dispatch,
    get_train_dispatches,
    verify_sequence,
    record_brake_test,
    issue_departure_command,
)

router = APIRouter(prefix="/dispatch", tags=["发车管理"])


@router.post("", response_model=TrainDispatchResponse)
def create_dispatch(dispatch_data: TrainDispatchCreate, db: Session = Depends(get_db)):
    return create_train_dispatch(db, dispatch_data)


@router.get("", response_model=List[TrainDispatchResponse])
def list_dispatches(
    status: Optional[str] = None,
    train_no: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return get_train_dispatches(db, status, train_no, skip, limit)


@router.post("/{dispatch_id}/verify-sequence")
def verify_seq(dispatch_id: int, db: Session = Depends(get_db)):
    result = verify_sequence(db, dispatch_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.post("/{dispatch_id}/brake-test")
def brake_test(dispatch_id: int, test_data: BrakeTestRequest, db: Session = Depends(get_db)):
    result = record_brake_test(db, dispatch_id, test_data)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.post("/{dispatch_id}/depart")
def depart(dispatch_id: int, driver: str, db: Session = Depends(get_db)):
    result = issue_departure_command(db, dispatch_id, driver)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result
