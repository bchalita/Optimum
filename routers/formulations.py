from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import FormulationTemplate

router = APIRouter(prefix="/formulations", tags=["formulations"])


# --- Helpers ---


def _serialize_summary(t: FormulationTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "alias": t.alias,
        "category": t.category,
        "tags": t.tags,
        "description": t.description,
    }


def _serialize_full(t: FormulationTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "alias": t.alias,
        "category": t.category,
        "description": t.description,
        "decision_variables": t.decision_variables,
        "objective": t.objective,
        "constraints": t.constraints,
        "parameters": t.parameters,
        "tags": t.tags,
        "source": t.source,
    }


# --- Routes ---


@router.get("/search")
def search_formulations(q: str = "", db: Session = Depends(get_db)):
    if not q.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query parameter 'q' is required.",
        )

    query = q.strip().lower()
    templates = db.query(FormulationTemplate).all()

    results = []
    for t in templates:
        searchable = " ".join([
            t.name.lower(),
            t.alias.lower(),
            t.category.lower(),
            t.description.lower(),
            " ".join(tag.lower() for tag in (t.tags or [])),
        ])
        if query in searchable:
            results.append(_serialize_summary(t))

    return {
        "success": True,
        "data": results,
        "error": None,
    }


@router.get("/{formulation_id}")
def get_formulation(formulation_id: str, db: Session = Depends(get_db)):
    template = (
        db.query(FormulationTemplate)
        .filter(FormulationTemplate.id == formulation_id)
        .first()
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Formulation template '{formulation_id}' not found.",
        )
    return {
        "success": True,
        "data": _serialize_full(template),
        "error": None,
    }


@router.get("")
def list_formulations(db: Session = Depends(get_db)):
    templates = (
        db.query(FormulationTemplate)
        .order_by(FormulationTemplate.category, FormulationTemplate.name)
        .all()
    )
    return {
        "success": True,
        "data": [_serialize_summary(t) for t in templates],
        "error": None,
    }
