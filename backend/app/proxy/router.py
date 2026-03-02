"""
Proxy router — mirrors AI provider cloud endpoints on localhost:8080.

Request flow:
  Client → localhost:8080/v1/... → [local screening] → <provider>/v1/... → [restore] → Client

Provider is detected from the model name in the request body, or the X-Provider
header (e.g. X-Provider: openai). Supported providers: mistral, openai, anthropic,
gemini, groq, xai.

WebSocket events are broadcast to the dashboard at each stage so the
pipeline view stays live.
"""
import json
import uuid
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from app.config import settings
from app.screening.image_ocr_nlp import screen_image
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
    "accept-encoding",  # Let httpx negotiate encoding — it knows what it can decompress
    "x-provider",       # Internal routing header, never forwarded
}


# ── Provider registry ──────────────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    base_url: str
    api_key_attr: str                   # attribute name on `settings`
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    extra_headers: dict = field(default_factory=dict)


_PROVIDERS: dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        base_url="https://api.openai.com",
        api_key_attr="openai_api_key",
    ),
    "anthropic": ProviderConfig(
        base_url="https://api.anthropic.com",
        api_key_attr="anthropic_api_key",
        auth_header="x-api-key",
        auth_prefix="",
        extra_headers={"anthropic-version": "2023-06-01"},
    ),
    "gemini": ProviderConfig(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_attr="gemini_api_key",
    ),
    "mistral": ProviderConfig(
        base_url="",           # resolved dynamically from settings.mistral_base_url
        api_key_attr="mistral_api_key",
    ),
    "groq": ProviderConfig(
        base_url="https://api.groq.com/openai",
        api_key_attr="groq_api_key",
    ),
    "xai": ProviderConfig(
        base_url="https://api.x.ai",
        api_key_attr="xai_api_key",
    ),
}

# Model prefix → provider (sorted longest-first so more-specific prefixes win)
_MODEL_MAP: list[tuple[str, str]] = sorted([
    ("claude",       "anthropic"),
    ("open-mistral", "mistral"),
    ("ministral",    "mistral"),
    ("codestral",    "mistral"),
    ("mistral",      "mistral"),
    ("gpt-",         "openai"),
    ("o1",           "openai"),
    ("o3",           "openai"),
    ("o4",           "openai"),
    ("chatgpt",      "openai"),
    ("gemini",       "gemini"),
    ("grok",         "xai"),
    ("llama",        "groq"),
    ("mixtral",      "groq"),
    ("gemma",        "groq"),
    ("qwen",         "groq"),
    ("deepseek",     "groq"),
], key=lambda x: -len(x[0]))


def _detect_provider(body: dict | None, req_headers: dict) -> str:
    """Return provider key from X-Provider header or model name. Default: mistral."""
    explicit = req_headers.get("x-provider", "").lower().strip()
    if explicit in _PROVIDERS:
        return explicit
    model = (body or {}).get("model", "").lower()
    for prefix, provider in _MODEL_MAP:
        if model.startswith(prefix):
            return provider
    return "mistral"


def _build_target(provider: str, path: str) -> tuple[str, dict]:
    """Return (target_url, headers_to_inject) for the given provider."""
    cfg = _PROVIDERS[provider]
    base = settings.mistral_base_url if provider == "mistral" else cfg.base_url
    api_key = getattr(settings, cfg.api_key_attr, "").strip()
    inject: dict[str, str] = {**cfg.extra_headers}
    if api_key:
        inject[cfg.auth_header] = f"{cfg.auth_prefix}{api_key}"
    return f"{base}/v1/{path}", inject


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
        if msg.get("role") == "system":
            screened.append(msg)
            continue

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

    # Detect provider from model name / explicit header
    req_headers_lower = {k.lower(): v for k, v in request.headers.items()}
    provider = _detect_provider(body, req_headers_lower)

    # ── Event: request intercepted ─────────────────────────────────────────
    await manager.broadcast(
        "request_intercepted",
        {
            "path": f"/v1/{path}",
            "method": request.method,
            "has_messages": bool(body and "messages" in body),
            "provider": provider,
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

        # Only show findings from the last user message in the dashboard.
        # We still screen everything for privacy, but conversation history
        # findings from prior turns shouldn't pollute the display.
        _last_user_text = ""
        for msg in reversed(original_messages):
            if msg.get("role") == "user":
                c = msg.get("content", "")
                if isinstance(c, str):
                    _last_user_text = c
                elif isinstance(c, list):
                    _last_user_text = " ".join(p.get("text", "") for p in c if p.get("type") == "text")
                break
        display_findings = [f for f in all_findings if f.get("value", "") in _last_user_text]

        await manager.broadcast(
            "screening_done",
            {
                "findings_count": len(display_findings),
                "findings": display_findings,
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
        k.lower(): v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_HEADERS
    }

    target_url, auth_headers = _build_target(provider, path)
    headers.update({k.lower(): v for k, v in auth_headers.items()})

    await manager.broadcast(
        "forwarding",
        {"target": target_url, "provider": provider, "redacted_count": len(all_findings)},
        session_id,
    )

    # ── Forward to cloud provider ──────────────────────────────────────────
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
    response_text = ""
    restored = ""

    try:
        response_text = response_bytes.decode("utf-8")
        if not session_vault:
            restored = response_text
        elif "\ndata:" in response_text or response_text.startswith("data:"):
            # SSE stream — fakes may be split across chunks, so reassemble
            # the full text, restore, then rewrite as a single content chunk.
            parts, first_chunk = [], None
            for line in response_text.splitlines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    if first_chunk is None:
                        first_chunk = chunk
                    c = chunk["choices"][0]["delta"].get("content") or ""
                    if c:
                        parts.append(c)
                except Exception:
                    continue
            full_text = "".join(parts)
            full_restored = await vault.ollama_restore(session_id, full_text)
            restored = full_restored
            if first_chunk is not None:
                first_chunk["choices"][0]["delta"] = {"content": full_restored}
                first_chunk["choices"][0]["finish_reason"] = "stop"
                sse = f"data: {json.dumps(first_chunk)}\n\ndata: [DONE]\n\n"
                final_bytes = sse.encode("utf-8")
            else:
                final_bytes = response_bytes
        else:
            # Non-streaming JSON — restore only the message content, not the whole blob
            try:
                resp_json = json.loads(response_text)
                content = resp_json["choices"][0]["message"]["content"]
                restored_content = await vault.ollama_restore(session_id, content)
                resp_json["choices"][0]["message"]["content"] = restored_content
                restored = restored_content
                final_bytes = json.dumps(resp_json).encode("utf-8")
            except Exception:
                restored = vault.restore(session_id, response_text)
                final_bytes = restored.encode("utf-8")
    except Exception as e:
        print(f"[proxy] response decode/restore error: {e!r}  bytes={len(response_bytes)} prefix={response_bytes[:40]!r}")

    # ── Broadcast pipeline snapshot ────────────────────────────────────────
    if original_messages:
        def _last_user(messages):
            """Return the last user-role message, falling back to the last message."""
            user_msgs = [m for m in messages if m.get("role") == "user"]
            return user_msgs[-1] if user_msgs else (messages[-1] if messages else {})

        def _preview(messages):
            msg = _last_user(messages)
            c = msg.get("content", "")
            if isinstance(c, list):
                texts = [p["text"] for p in c if p.get("type") == "text"]
                return "\n".join(texts)[:500]
            return (c if isinstance(c, str) else str(c))[:500]

        def _extract_image(messages):
            content = _last_user(messages).get("content", "")
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            return url
            return None

        def _extract_reply(text: str) -> str:
            """Pull assistant text from a chat completion — handles both JSON and SSE streams."""
            if not text:
                return ""
            # Non-streaming: single JSON object
            try:
                data = json.loads(text)
                content = data["choices"][0]["message"]["content"]
                return (content if isinstance(content, str) else str(content))[:500]
            except Exception:
                pass
            # Streaming: accumulate delta.content from SSE lines
            parts = []
            for line in text.splitlines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    delta = chunk["choices"][0]["delta"]
                    if delta.get("content"):
                        parts.append(delta["content"])
                except Exception:
                    continue
            result = "".join(parts)
            return result[:500] if result else text[:200]

        try:
            await manager.broadcast(
                "pipeline_snapshot",
                {
                    "original": _preview(original_messages),
                    "screened": _preview(body["messages"]) if body and "messages" in body else "",
                    "cloud_response": (cloud_text := _extract_reply(response_text)),
                    "reconstructed": restored if session_vault else cloud_text,
                    "findings": len(display_findings),
                    "vault": {k: "●●●●●" for k in session_vault},
                    "original_image": _extract_image(original_messages),
                    "screened_image": _extract_image(body["messages"]) if body and "messages" in body else None,
                    "provider": provider,
                },
                session_id,
            )
        except Exception as e:
            print(f"[proxy] pipeline_snapshot broadcast error: {e!r}")

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
