"""Dataset upload API. Protected by ADMIN_API_TOKEN (bearer). Default is a dry run: nothing is written until dry_run=false."""
from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from ..config import get_settings
from ..datasets.importer import ImportOptions, import_file
from ..datasets.parse import UploadError
from ..datasets.spec import KINDS, spec_json
from ..datasets.templates import template_bytes

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def require_admin(authorization: Annotated[str | None, Header()] = None) -> str:
    token = get_settings().admin_api_token
    if not token:
        raise HTTPException(503, "uploads disabled: ADMIN_API_TOKEN is not configured")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not supplied or not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(401, "invalid token", headers={"WWW-Authenticate": "Bearer"})
    return "api"


def _kind(kind: str) -> str:
    if kind not in KINDS:
        raise HTTPException(404, f"unknown dataset kind: {kind}")
    return kind


@router.get("/spec")
async def spec() -> dict[str, object]:
    return spec_json()


@router.get("/{kind}/template.csv")
async def template(kind: str) -> Response:
    _kind(kind)
    return Response(template_bytes(kind), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="omnidata-{kind}-modelo.csv"'})


@router.get("")
async def list_uploads(request: Request, _: str = Depends(require_admin)) -> list[dict[str, Any]]:
    with request.app.state.connect() as conn, conn.cursor() as cur:
        cur.execute("select id, kind, filename, status, total_rows, imported_rows, error_count, summary, created_at "
                    "from app.dataset_upload order by created_at desc limit 50")
        return [{**r, "id": str(r["id"]), "created_at": r["created_at"].isoformat()} for r in cur.fetchall()]


@router.post("/{kind}")
async def upload(request: Request, kind: str, file: Annotated[UploadFile, File()], dry_run: Annotated[bool, Form()] = True,
                 allow_partial: Annotated[bool, Form()] = False, replace: Annotated[bool, Form()] = False,
                 import_notes: Annotated[bool, Form()] = True, stage_order: Annotated[str, Form()] = "",
                 user: str = Depends(require_admin)) -> JSONResponse:
    _kind(kind)
    s = get_settings()
    data = await file.read(s.dataset_max_bytes + 1)  # never buffer more than the limit
    opts = ImportOptions(dry_run=dry_run, allow_partial=allow_partial, replace=replace, import_notes=import_notes,
                         stage_order=[x.strip() for x in stage_order.split(",") if x.strip()] or None, uploaded_by=user)
    try:
        with request.app.state.connect() as conn:
            res = import_file(conn, kind, data, file.filename or "upload", opts, max_bytes=s.dataset_max_bytes, max_rows=s.dataset_max_rows)
    except UploadError as exc:
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=413 if exc.code == "too_big" else 422)
    return JSONResponse(res.to_dict(), status_code=422 if res.status == "rejected" else 200)
