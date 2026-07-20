"""PhantomAPI — Authentication dependencies."""

from fastapi import Request, HTTPException
from app.config import settings


async def verify_api_key(request: Request) -> str:
    """Validate the Bearer token from the Authorization header.

    Authentication is BYPASSED when API_SECRET_KEY is empty or set to "none".
    Any other value (including the default placeholder) enforces auth.
    """
    key = settings.API_SECRET_KEY.strip()
    if not key or key.lower() == "none":
        return ""  # Auth disabled

    authorization = request.headers.get("authorization", "")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header.")

    # Strip "Bearer " prefix
    token = authorization.replace("Bearer ", "").strip()

    if token != settings.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key.")

    return token
