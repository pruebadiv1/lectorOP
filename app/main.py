from __future__ import annotations

import copy
import json
import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .config import BASE_DIR, UPLOAD_DIR, ensure_directories
from .database import OrderRecord, get_session, init_database
from .parser import ParserError, parse_winmaker_pdf
from .services import (
    DomainError,
    add_audit,
    add_manual_glass,
    add_manual_accessory,
    audit_events,
    confirm_typology,
    consolidated_accessories,
    finalize_order,
    make_csv,
    make_pdf,
    make_xlsx,
    public_order,
    resolve_description,
    toggle_glass_exclusion,
    toggle_accessory_exclusion,
    update_glass,
    update_accessory_observations,
    update_accessory_quantity,
)

ensure_directories()
init_database()
app = FastAPI(title="Preparador Winmaker", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")


class QuantityPayload(BaseModel):
    quantity: float = Field(ge=0)


class ExclusionPayload(BaseModel):
    excluded: bool


class ManualAccessoryPayload(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    quantity: float = Field(ge=0)
    detail: str = Field(min_length=1, max_length=500)
    observations: str = Field(default="", max_length=1000)


class DescriptionPayload(BaseModel):
    final_description: str = Field(min_length=1, max_length=500)


class ObservationsPayload(BaseModel):
    observations: str = Field(default="", max_length=1000)


class GlassPayload(BaseModel):
    quantity: float = Field(ge=0)
    measure: str = Field(min_length=3, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    observations: str = Field(default="", max_length=1000)


class ManualGlassPayload(GlassPayload):
    material_type: str = Field(pattern="^(glass|mesh)$")


def _order_or_404(session: Session, order_id: str) -> OrderRecord:
    order = session.get(OrderRecord, order_id)
    if not order:
        raise HTTPException(404, "No se encontró la orden.")
    return order


def _domain_call(callable_: object, *args: object, **kwargs: object) -> object:
    try:
        return callable_(*args, **kwargs)  # type: ignore[operator]
    except DomainError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "app" / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/orders")
def list_orders(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    orders = session.query(OrderRecord).order_by(OrderRecord.created_at.desc()).all()
    return [public_order(order, include_document=False) for order in orders]


@app.post("/api/orders", status_code=201)
def create_order(
    client_name: Annotated[str, Form(min_length=1, max_length=250)],
    pdf: Annotated[UploadFile, File()],
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if pdf.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(415, "Debe cargar un archivo PDF.")
    order_id = str(uuid.uuid4())
    safe_name = Path(pdf.filename or "orden.pdf").name
    stored_path = UPLOAD_DIR / f"{order_id}.pdf"
    with stored_path.open("wb") as destination:
        shutil.copyfileobj(pdf.file, destination)
    try:
        document = parse_winmaker_pdf(stored_path, client_name.strip())
    except ParserError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    original_document = copy.deepcopy(document)
    order = OrderRecord(
        id=order_id,
        client_name=client_name.strip(),
        source_filename=safe_name,
        source_sha256=document["document"]["sha256"],
        source_path=str(stored_path),
        status="en_revision",
        document_json=json.dumps(document, ensure_ascii=False, separators=(",", ":")),
        original_json=json.dumps(original_document, ensure_ascii=False, separators=(",", ":")),
    )
    session.add(order)
    add_audit(
        session,
        order,
        "order_created",
        payload={"client_name": client_name.strip(), "filename": safe_name},
    )
    session.commit()
    session.refresh(order)
    return public_order(order)


@app.get("/api/orders/{order_id}")
def get_order(order_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return public_order(_order_or_404(session, order_id))


@app.get("/api/orders/{order_id}/audit")
def get_audit(order_id: str, session: Session = Depends(get_session)) -> list[dict[str, object]]:
    _order_or_404(session, order_id)
    return audit_events(session, order_id)


@app.patch("/api/orders/{order_id}/typologies/{typology_id}/accessories/{accessory_id}/quantity")
def patch_quantity(
    order_id: str,
    typology_id: str,
    accessory_id: str,
    payload: QuantityPayload,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    order = _order_or_404(session, order_id)
    accessory = _domain_call(
        update_accessory_quantity,
        session,
        order,
        typology_id,
        accessory_id,
        payload.quantity,
    )
    session.commit()
    return accessory  # type: ignore[return-value]


@app.patch("/api/orders/{order_id}/typologies/{typology_id}/accessories/{accessory_id}/exclusion")
def patch_exclusion(
    order_id: str,
    typology_id: str,
    accessory_id: str,
    payload: ExclusionPayload,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    order = _order_or_404(session, order_id)
    accessory = _domain_call(
        toggle_accessory_exclusion,
        session,
        order,
        typology_id,
        accessory_id,
        payload.excluded,
    )
    session.commit()
    return accessory  # type: ignore[return-value]


@app.post("/api/orders/{order_id}/typologies/{typology_id}/accessories", status_code=201)
def post_manual_accessory(
    order_id: str,
    typology_id: str,
    payload: ManualAccessoryPayload,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    order = _order_or_404(session, order_id)
    accessory = _domain_call(
        add_manual_accessory,
        session,
        order,
        typology_id,
        payload.code,
        payload.quantity,
        payload.detail,
        payload.observations,
    )
    session.commit()
    return accessory  # type: ignore[return-value]


@app.patch("/api/orders/{order_id}/typologies/{typology_id}/accessories/{accessory_id}/observations")
def patch_accessory_observations(
    order_id: str,
    typology_id: str,
    accessory_id: str,
    payload: ObservationsPayload,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    order = _order_or_404(session, order_id)
    accessory = _domain_call(
        update_accessory_observations,
        session,
        order,
        typology_id,
        accessory_id,
        payload.observations,
    )
    session.commit()
    return accessory  # type: ignore[return-value]


@app.patch("/api/orders/{order_id}/typologies/{typology_id}/glasses/{glass_id}")
def patch_glass(
    order_id: str,
    typology_id: str,
    glass_id: str,
    payload: GlassPayload,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    order = _order_or_404(session, order_id)
    glass = _domain_call(
        update_glass,
        session,
        order,
        typology_id,
        glass_id,
        quantity=payload.quantity,
        measure=payload.measure,
        description=payload.description,
        observations=payload.observations,
    )
    session.commit()
    return glass  # type: ignore[return-value]


@app.patch("/api/orders/{order_id}/typologies/{typology_id}/glasses/{glass_id}/exclusion")
def patch_glass_exclusion(
    order_id: str,
    typology_id: str,
    glass_id: str,
    payload: ExclusionPayload,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    order = _order_or_404(session, order_id)
    glass = _domain_call(
        toggle_glass_exclusion,
        session,
        order,
        typology_id,
        glass_id,
        payload.excluded,
    )
    session.commit()
    return glass  # type: ignore[return-value]


@app.post("/api/orders/{order_id}/typologies/{typology_id}/glasses", status_code=201)
def post_manual_glass(
    order_id: str,
    typology_id: str,
    payload: ManualGlassPayload,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    order = _order_or_404(session, order_id)
    glass = _domain_call(
        add_manual_glass,
        session,
        order,
        typology_id,
        material_type=payload.material_type,
        quantity=payload.quantity,
        measure=payload.measure,
        description=payload.description,
        observations=payload.observations,
    )
    session.commit()
    return glass  # type: ignore[return-value]


@app.post("/api/orders/{order_id}/typologies/{typology_id}/confirm")
def post_confirm_typology(
    order_id: str,
    typology_id: str,
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    order = _order_or_404(session, order_id)
    _domain_call(confirm_typology, session, order, typology_id)
    session.commit()
    return {"ok": True}


@app.get("/api/orders/{order_id}/results/accessories")
def get_consolidated(order_id: str, session: Session = Depends(get_session)) -> list[dict[str, object]]:
    order = _order_or_404(session, order_id)
    return consolidated_accessories(order)


@app.put("/api/orders/{order_id}/results/accessories/{code}/description")
def put_description(
    order_id: str,
    code: str,
    payload: DescriptionPayload,
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    order = _order_or_404(session, order_id)
    _domain_call(resolve_description, session, order, code, payload.final_description)
    session.commit()
    return {"ok": True}


@app.post("/api/orders/{order_id}/finalize")
def post_finalize(order_id: str, session: Session = Depends(get_session)) -> dict[str, bool]:
    order = _order_or_404(session, order_id)
    _domain_call(finalize_order, session, order)
    session.commit()
    return {"ok": True}


@app.get("/api/orders/{order_id}/export/{kind}.xlsx")
def export_xlsx(order_id: str, kind: str, session: Session = Depends(get_session)) -> Response:
    if kind not in ("glasses", "accessories"):
        raise HTTPException(404, "Exportación no encontrada.")
    order = _order_or_404(session, order_id)
    return Response(
        make_xlsx(order, kind),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{kind}-{order.client_name}.xlsx"'},
    )


@app.get("/api/orders/{order_id}/export/{kind}.csv")
def export_csv(order_id: str, kind: str, session: Session = Depends(get_session)) -> Response:
    if kind not in ("glasses", "accessories"):
        raise HTTPException(404, "Exportación no encontrada.")
    order = _order_or_404(session, order_id)
    return Response(
        make_csv(order, kind),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{kind}-{order.client_name}.csv"'},
    )


@app.get("/api/orders/{order_id}/export/{kind}.pdf")
def export_pdf(order_id: str, kind: str, session: Session = Depends(get_session)) -> Response:
    if kind not in ("glasses", "accessories"):
        raise HTTPException(404, "Exportación no encontrada.")
    order = _order_or_404(session, order_id)
    return Response(
        make_pdf(order, kind),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{kind}-{order.client_name}.pdf"'},
    )
