"""Endpoints the sidebar panels call that the clean rebuild never implemented.

Without these the frontend hits the SPA fallback, gets HTML back, fails to
parse it and shows a red error in "My Files", "Trusted Partners", "Free
Credits Box" and the ads form. They are backed by in-memory state only; no
file storage or moderation pipeline exists in this rebuild.
"""
import secrets
import time

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from store import UPLOADS, ADS, token_from_header, user_for

router = APIRouter(prefix="/api", tags=["community"])


def _user(authorization: str):
    session = user_for(token_from_header(authorization))
    if not session:
        return None, JSONResponse({"error": "Authentication token is required."}, 401)
    return session["user"], None


@router.get("/my-files")
async def my_files(authorization: str = Header(default="")):
    user, err = _user(authorization)
    if err:
        return err
    return {"success": True, "files": UPLOADS.get(user["id"], [])}


@router.delete("/my-files")
async def delete_file(req: Request, authorization: str = Header(default="")):
    user, err = _user(authorization)
    if err:
        return err
    body = await req.json()
    UPLOADS[user["id"]] = [f for f in UPLOADS.get(user["id"], [])
                           if f["id"] != body.get("id")]
    return {"success": True}


@router.get("/get-file-url")
async def get_file_url(fileKey: str = "", authorization: str = Header(default="")):
    user, err = _user(authorization)
    if err:
        return err
    for record in UPLOADS.get(user["id"], []):
        if record["fileKey"] == fileKey:
            return {"success": True, "url": record["url"]}
    return JSONResponse({"error": "File not found."}, 404)


@router.get("/partners")
async def partners(authorization: str = Header(default="")):
    user, err = _user(authorization)
    if err:
        return err
    # No partner inventory in this rebuild; an empty list renders the empty state.
    return {"success": True, "partners": []}


@router.get("/advertisement")
async def ads_list(authorization: str = Header(default="")):
    user, err = _user(authorization)
    if err:
        return err
    return {"success": True, "ads": ADS}


@router.post("/advertisement")
async def ads_submit(req: Request, authorization: str = Header(default="")):
    body = await req.json()
    if not (body.get("productName") or "").strip():
        return JSONResponse({"error": "Product name is required."}, 400)
    record = {
        "id": secrets.token_hex(8),
        "productName": body.get("productName"),
        "productDetails": body.get("productDetails"),
        "pricing": body.get("pricing"),
        "contactInfo": body.get("contactInfo"),
        "type": body.get("type", "tool"),
        "plan": body.get("plan"),
        "image1Url": body.get("image1"),
        "image2Url": body.get("image2"),
        "status": "pending",
        "createdAt": int(time.time() * 1000),
    }
    ADS.append(record)
    return {"success": True, "ad": record,
            "message": "Advertisement submitted successfully for review."}


@router.get("/mystery-box")
async def mystery_box_status(authorization: str = Header(default="")):
    user, err = _user(authorization)
    if err:
        return err
    # No ad inventory is configured, so report the graceful "nothing to claim"
    # state instead of an error the UI would paint red.
    return {"success": True, "canClaim": True, "hasAd": False,
            "message": "No ads available right now. Check back later."}


@router.post("/mystery-box")
async def mystery_box_claim(req: Request, authorization: str = Header(default="")):
    user, err = _user(authorization)
    if err:
        return err
    return JSONResponse({"error": "No ads available right now."}, 409)
