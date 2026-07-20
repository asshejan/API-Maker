"""PhantomAPI — GET & POST /search  and  /v1/search."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import verify_api_key
from app.services.search import process_search_query

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    """Body for POST /search or POST /v1/search."""

    q: Optional[str] = Field(
        default=None,
        description="Search query in human language.",
        examples=["find me all available tickets from Dhaka to US today"],
    )
    query: Optional[str] = Field(
        default=None,
        description="Alternative field name for the search query.",
        examples=["Find me last 6 months GP stock prices"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"q": "find me all available tickets from Dhaka to US today"},
                {"query": "Find me last 6 months GP stock prices"},
            ]
        }
    }

    def resolved_query(self) -> str:
        """Return the first non-empty query text."""
        return (self.q or self.query or "").strip()


# ── GET /search ──────────────────────────────────────────────────────────────

@router.get("/search", summary="Search (GET)", dependencies=[Depends(verify_api_key)])
async def search_get(
    q: str = Query(..., description="Search query in human language."),
):
    """
    Perform a natural-language search via GET.

    Example:
    ```
    GET /search?q=find+me+flights+from+Dhaka+to+JFK+today
    Authorization: Bearer <API_SECRET_KEY>
    ```
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' cannot be empty.")
    return process_search_query(q.strip())


# ── POST /search ─────────────────────────────────────────────────────────────

@router.post("/search", summary="Search (POST)", dependencies=[Depends(verify_api_key)])
async def search_post(payload: SearchRequest):
    """
    Perform a natural-language search via POST JSON body.

    Example body:
    ```json
    { "q": "Find me last 6 months GP stock prices" }
    ```
    """
    text = payload.resolved_query()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="Provide 'q' or 'query' in the JSON body.",
        )
    return process_search_query(text)
