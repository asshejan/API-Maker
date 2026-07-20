"""PhantomAPI — Simplified endpoints /query and /chat."""

from typing import Any, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import verify_api_key
from app.services.search import process_search_query
from app.services.chat import process_chat_completion

router = APIRouter(tags=["Simplified API"])


class QueryRequest(BaseModel):
    """Payload for POST /query."""

    query: str = Field(..., description="The query to search or ask about.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "find me all available flights from Dubai to New York City today"
            }
        }
    }


class ChatRequest(BaseModel):
    """Payload for POST /chat."""

    messages: Optional[List[dict]] = Field(None, description="List of messages representing the conversation history.")
    message: Optional[str] = Field(None, description="A single user message to start or continue a conversation.")
    input: Optional[Union[str, List[dict]]] = Field(None, description="Alternative field for message or messages list.")
    query: Optional[str] = Field(None, description="Alternative field for the user message.")

    model: Optional[str] = Field("gpt-4o-mini", description="Model name to return in response.")
    instructions: Optional[str] = Field(None, description="System instructions/prompt to guide the model.")
    system_prompt: Optional[str] = Field(None, description="Alternative field for system instructions.")
    tools: Optional[list] = Field(None, description="List of tools available for function calling.")

    def resolved_messages(self) -> List[dict]:
        """Convert input arguments to a standardised messages list."""
        resolved: List[dict] = []
        if self.messages:
            resolved = [dict(m) for m in self.messages]
        elif isinstance(self.input, list):
            resolved = [dict(m) for m in self.input]
        else:
            user_text = self.message or self.query or ""
            if isinstance(self.input, str):
                user_text = self.input
            if user_text:
                resolved = [{"role": "user", "content": user_text}]

        # Normalise / Inject System Instructions
        sys_content = (self.instructions or self.system_prompt or "").strip()
        if sys_content:
            if resolved and resolved[0].get("role") == "system":
                resolved[0]["content"] = sys_content
            else:
                resolved.insert(0, {"role": "system", "content": sys_content})

        return resolved


# ── /query ───────────────────────────────────────────────────────────────────

@router.get("/query", summary="Query Everything (GET)", dependencies=[Depends(verify_api_key)])
async def query_get(
    query: str = Query(..., description="The query to search or ask about (e.g. flight tickets, stock price)."),
):
    """
    Query everything using natural language (GET).
    Executes search and webpage fetching to extract the answer.
    """
    user_query = query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query parameter 'query' cannot be empty.")
    return process_search_query(user_query)


@router.post("/query", summary="Query Everything (POST)", dependencies=[Depends(verify_api_key)])
async def query_post(payload: QueryRequest):
    """
    Query everything using natural language (POST).
    Executes search and webpage fetching to extract the answer.
    """
    user_query = payload.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query field 'query' cannot be empty.")
    return process_search_query(user_query)


# ── /chat ─────────────────────────────────────────────────────────────────────

@router.post("/chat", summary="Conversational Chat (POST)", dependencies=[Depends(verify_api_key)])
async def chat_post(payload: ChatRequest):
    """
    Start or continue a conversational chat (POST).
    """
    messages = payload.resolved_messages()
    if not messages:
        raise HTTPException(status_code=400, detail="Provide 'messages', 'message', 'input', or 'query' in the JSON body.")
    
    model = payload.model or "gpt-4o-mini"
    return process_chat_completion(messages, model, payload.tools)
