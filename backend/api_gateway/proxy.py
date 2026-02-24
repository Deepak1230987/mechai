"""
Async HTTP proxy utility.
Forwards requests from the gateway to internal services using httpx.
"""

import httpx
import logging
from fastapi import Request, Response

logger = logging.getLogger("api_gateway.proxy")

# Reusable async client (connection pooling)
_client = httpx.AsyncClient(timeout=30.0)


async def proxy_request(
    request: Request,
    target_base_url: str,
    target_path: str,
    extra_headers: dict[str, str] | None = None,
) -> Response:
    """
    Forward an incoming request to an internal service.

    Args:
        request: The original FastAPI request
        target_base_url: Base URL of the target service (e.g., http://localhost:8001)
        target_path: Path on the target service (e.g., /auth/login)
        extra_headers: Additional headers to inject (e.g., X-User-ID)

    Returns:
        FastAPI Response mirroring the upstream response.
    """
    url = f"{target_base_url}{target_path}"

    # Build headers — forward relevant originals and inject gateway headers
    headers = {}
    for key, value in request.headers.items():
        key_lower = key.lower()
        # Forward content-type and accept, skip host/connection
        if key_lower in ("content-type", "accept", "authorization"):
            headers[key] = value

    if extra_headers:
        headers.update(extra_headers)

    # Read the request body
    body = await request.body()

    # Build query string
    query = str(request.query_string, "utf-8") if request.query_string else None
    if query:
        url = f"{url}?{query}"

    logger.info(f"Proxying {request.method} {request.url.path} → {url}")

    try:
        upstream_response = await _client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body if body else None,
        )
    except httpx.RequestError as exc:
        logger.error(f"Proxy error: {exc}")
        return Response(
            content=f'{{"detail": "Service unavailable: {type(exc).__name__}"}}',
            status_code=502,
            media_type="application/json",
        )

    # Mirror the upstream response back to the client
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type", "application/json"),
    )
