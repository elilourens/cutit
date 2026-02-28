"""
Proxy router — mirrors Mistral cloud endpoints on localhost:8080.

Request flow:
  Client → localhost:8080/v1/... → [local screening] → api.mistral.ai/v1/... → [restore] → Client

WebSocket events are broadcast to the dashboard at each stage so the
pipeline view stays live.
"""
import json
import uuid

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from app.config import settings
from app.screening.image import screen_image
from app.screening.text import screen_text
from app.vault.store import vault
from app.ws.manager import manager

router = APIRouter()

# Headers we never forward upstream
_HOP_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
}


# ── Message screening ─────────────────────────────────────────────────────────

async def _screen_content_part(part: dict, session_id: str) -> tuple[dict, list]:
    """Screen a single multimodal content part. Returns (screened_part, findings)."""
    findings = []

    if part.get("type") == "text":
        redacted, hits = await screen_text(part["text"], session_id)
        return {**part, "text": redacted}, hits

    if part.get("type") == "image_url":
        url = part.get("image_url", {}).get("url", "")
        if url.startswith("data:"):
            header, b64 = url.split(",", 1)
            redacted_b64, regions = await screen_image(b64)
            findings = [
                {"entity_type": "IMAGE_REGION", "label": r.get("label"), "source": "vision"}
                for r in regions
            ]
            return {**part, "image_url": {"url": f"{header},{redacted_b64}"}}, findings

    return part, findings


async def _screen_messages(messages: list, session_id: str) -> tuple[list, list]:
    """Screen every message in the list. Returns (screened_messages, all_findings)."""
    screened = []
    all_findings = []

    for msg in messages:
        content = msg.get("content", "")

        if isinstance(content, str):
            redacted, hits = await screen_text(content, session_id)
            screened.append({**msg, "content": redacted})
            all_findings.extend(hits)

        elif isinstance(content, list):
            new_parts = []
            for part in content:
                screened_part, hits = await _screen_content_part(part, session_id)
                new_parts.append(screened_part)
                all_findings.extend(hits)
            screened.append({**msg, "content": new_parts})

        else:
            screened.append(msg)

    return screened, all_findings


# ── Proxy handler ─────────────────────────────────────────────────────────────

@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    session_id = str(uuid.uuid4())

    raw_body = await request.body()
    body: dict | None = None
    screened_body = raw_body
    original_messages = None
    all_findings: list = []

    # Parse JSON body
    ct = request.headers.get("content-type", "")
    if raw_body and "application/json" in ct:
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            pass

    # ── Event: request intercepted ─────────────────────────────────────────
    await manager.broadcast(
        "request_intercepted",
        {
            "path": f"/v1/{path}",
            "method": request.method,
            "has_messages": bool(body and "messages" in body),
        },
        session_id,
    )

    # ── Screen messages ────────────────────────────────────────────────────
    if body and "messages" in body:
        original_messages = body["messages"]

        await manager.broadcast(
            "screening_started",
            {"message_count": len(original_messages)},
            session_id,
        )

        screened_messages, all_findings = await _screen_messages(
            original_messages, session_id
        )
        body["messages"] = screened_messages
        screened_body = json.dumps(body).encode()

        await manager.broadcast(
            "screening_done",
            {
                "findings_count": len(all_findings),
                "findings": all_findings,
                "vault_size": len(vault.get_session(session_id)),
            },
            session_id,
        )

        if all_findings:
            await manager.broadcast(
                "vault_updated",
                {
                    "session_id": session_id,
                    # Show fake keys only — never broadcast real values
                    "fakes": list(vault.get_session(session_id).keys()),
                },
                session_id,
            )

    # ── Build upstream request ─────────────────────────────────────────────
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_HEADERS
    }
    # Inject API key from env if provided (allows clients to omit it)
    if settings.mistral_api_key:
        headers["Authorization"] = f"Bearer {settings.mistral_api_key}"

    target_url = f"{settings.mistral_base_url}/v1/{path}"

    await manager.broadcast(
        "forwarding",
        {"target": target_url, "redacted_count": len(all_findings)},
        session_id,
    )

    # ── Forward to Mistral cloud ───────────────────────────────────────────
    async with httpx.AsyncClient(timeout=120.0) as client:
        upstream = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=screened_body,
            params=dict(request.query_params),
        )
        response_bytes = upstream.content

    await manager.broadcast(
        "response_received",
        {"status": upstream.status_code, "bytes": len(response_bytes)},
        session_id,
    )

    # ── Restore real values in response ───────────────────────────────────
    final_bytes = response_bytes
    session_vault = vault.get_session(session_id)

    if session_vault:
        try:
            response_text = response_bytes.decode("utf-8")
            restored = vault.restore(session_id, response_text)
            final_bytes = restored.encode("utf-8")

            # Broadcast pipeline snapshot to dashboard
            def _preview(messages, idx=0):
                if not messages:
                    return ""
                c = messages[idx].get("content", "")
                if isinstance(c, list):
                    texts = [p["text"] for p in c if p.get("type") == "text"]
                    return "\n".join(texts)[:300]
                return (c if isinstance(c, str) else str(c))[:300]

            def _extract_image(messages, idx=0):
                if not messages:
                    return None
                content = messages[idx].get("content", "")
                if isinstance(content, list):
                    for part in content:
                        if part.get("type") == "image_url":
                            url = part.get("image_url", {}).get("url", "")
                            if url.startswith("data:"):
                                return url
                return None

            await manager.broadcast(
                "pipeline_snapshot",
                {
                    "original": _preview(original_messages) if original_messages else "",
                    "screened": _preview(body["messages"]) if body and "messages" in body else "",
                    "cloud_response": response_text[:300],
                    "reconstructed": restored[:300],
                    "findings": len(all_findings),
                    "vault": {k: "●●●●●" for k in session_vault},  # mask real values
                    "original_image": _extract_image(original_messages) if original_messages else None,
                    "screened_image": _extract_image(body["messages"]) if body and "messages" in body else None,
                },
                session_id,
            )
        except Exception:
            pass

    # Strip hop-by-hop headers from upstream response
    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in _HOP_HEADERS | {"content-encoding"}
    }

    return Response(
        content=final_bytes,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
