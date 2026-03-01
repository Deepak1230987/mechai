"""
API Gateway route definitions.

Routes traffic to internal services:
  /auth/*   → Auth Service   (no JWT required for login/register)
  /models/* → CAD Service    (JWT required)

All routes are thin proxies — no business logic here.
"""

from fastapi import APIRouter, Depends, Request, Response

from shared.config import get_settings
from api_gateway.dependencies import require_auth, optional_auth, CurrentUser
from api_gateway.proxy import proxy_request

settings = get_settings()
gateway_router = APIRouter()


# ─── Auth routes (public — no JWT required) ───────────────────────────────────

@gateway_router.api_route(
    "/auth/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def auth_proxy(
    request: Request,
    path: str,
    user: CurrentUser | None = Depends(optional_auth),
):
    """
    Proxy all /auth/* requests to the Auth Service.
    Login and Register are public; /auth/me needs a token.
    """
    extra_headers = {}
    if user:
        extra_headers["X-User-ID"] = user.user_id
        extra_headers["X-User-Role"] = user.role

    # For /auth/me, inject user_id as query parameter so auth service can use it
    target_path = f"/auth/{path}"
    if path == "me" and user:
        target_path = f"/auth/me?user_id={user.user_id}"

    return await proxy_request(
        request=request,
        target_base_url=settings.AUTH_SERVICE_URL,
        target_path=target_path,
        extra_headers=extra_headers,
    )


# ─── Models routes (protected — JWT required) ────────────────────────────────

@gateway_router.api_route(
    "/models/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def models_proxy(
    request: Request,
    path: str,
    user: CurrentUser = Depends(require_auth),
):
    """
    Proxy all /models/* requests to the CAD Service.
    JWT is required — user context is injected via headers.
    """
    return await proxy_request(
        request=request,
        target_base_url=settings.CAD_SERVICE_URL,
        target_path=f"/models/{path}",
        extra_headers={
            "X-User-ID": user.user_id,
            "X-User-Role": user.role,
        },
    )


# Also handle /models root (no trailing path)
@gateway_router.api_route(
    "/models",
    methods=["GET", "POST"],
)
async def models_root_proxy(
    request: Request,
    user: CurrentUser = Depends(require_auth),
):
    """Proxy /models (root) requests to CAD Service."""
    return await proxy_request(
        request=request,
        target_base_url=settings.CAD_SERVICE_URL,
        target_path="/models/",
        extra_headers={
            "X-User-ID": user.user_id,
            "X-User-Role": user.role,
        },
    )


# ─── AI / Planning routes (protected — JWT required) ─────────────────────────

@gateway_router.api_route(
    "/planning/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def planning_proxy(
    request: Request,
    path: str,
    user: CurrentUser = Depends(require_auth),
):
    """Proxy all /planning/* requests to the AI Service."""
    return await proxy_request(
        request=request,
        target_base_url=settings.AI_SERVICE_URL,
        target_path=f"/planning/{path}",
        extra_headers={
            "X-User-ID": user.user_id,
            "X-User-Role": user.role,
        },
    )


@gateway_router.api_route(
    "/planning",
    methods=["GET", "POST"],
)
async def planning_root_proxy(
    request: Request,
    user: CurrentUser = Depends(require_auth),
):
    """Proxy /planning (root) requests to AI Service."""
    return await proxy_request(
        request=request,
        target_base_url=settings.AI_SERVICE_URL,
        target_path="/planning/",
        extra_headers={
            "X-User-ID": user.user_id,
            "X-User-Role": user.role,
        },
    )


# ─── Intelligence routes (Phase C — protected) ──────────────────────────────

@gateway_router.api_route(
    "/intelligence/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def intelligence_proxy(
    request: Request,
    path: str,
    user: CurrentUser = Depends(require_auth),
):
    """Proxy all /intelligence/* requests to the AI Service (Phase C)."""
    return await proxy_request(
        request=request,
        target_base_url=settings.AI_SERVICE_URL,
        target_path=f"/intelligence/{path}",
        extra_headers={
            "X-User-ID": user.user_id,
            "X-User-Role": user.role,
        },
    )
