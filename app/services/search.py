"""PhantomAPI — Agentic Search Service.

Handles human-language queries through a multi-step reasoning loop:
  1. ChatGPT decides what to search / fetch
  2. Playwright performs the actual web operation
  3. Results are fed back to ChatGPT
  4. ChatGPT returns a clean, structured JSON answer

Supports any query: flights, stock prices, news, weather, etc.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from app.services.browser import engine

# ── Current time (from system metadata) ────────────────────────────────────
_TZ_OFFSET = timedelta(hours=6)
_NOW = datetime(2026, 7, 20, 20, 46, 3, tzinfo=timezone(_TZ_OFFSET))
CURRENT_DATE = _NOW.strftime("%Y-%m-%d")
CURRENT_TIME = _NOW.strftime("%H:%M:%S")
CURRENT_TZ   = "+06:00"

# ── System prompt injected at the top of every ChatGPT call ────────────────
_SYSTEM_PROMPT = f"""\
You are PhantomSearch, an expert AI research assistant powered by real-time web browsing.

TODAY'S DATE : {CURRENT_DATE}
CURRENT TIME : {CURRENT_TIME} ({CURRENT_TZ})

═══════════════════════════════════════════════════════════
TOOLS YOU MAY USE  (call one per turn, JSON-only output)
═══════════════════════════════════════════════════════════

1. web_search  — query a search engine
   {{
     "tool_call": "web_search",
     "arguments": {{ "query": "<concise search string>" }}
   }}

2. fetch_webpage  — load & scrape a specific URL
   {{
     "tool_call": "fetch_webpage",
     "arguments": {{ "url": "<full https URL>" }}
   }}

═══════════════════════════════════════════════════════════
WORKFLOW
═══════════════════════════════════════════════════════════
• For LIVE data (flights, stock prices, weather, news, sports scores …)
  you MUST call a tool. Never hallucinate live data.
• Think step-by-step: search → pick the best URL → fetch → extract data.
• After fetching sufficient data, output the FINAL ANSWER JSON.

═══════════════════════════════════════════════════════════
FINAL ANSWER FORMAT
═══════════════════════════════════════════════════════════
When you have all the data, output ONLY valid JSON — no markdown code fences,
no explanation, no surrounding text. The JSON must directly answer the user's
request, structured sensibly:

• Flights query   → follow the flight results schema (search metadata + results[])
• Stock prices    → array of OHLCV objects
• General lookup  → whatever structure best represents the answer

If you truly cannot find live data, return:
{{
  "error": "Could not retrieve live data",
  "reason": "<brief explanation>",
  "partial_results": []
}}
"""


# ── Helpers ─────────────────────────────────────────────────────────────────

def _parse_json(text: str) -> Any:
    """Parse JSON from ChatGPT output, stripping markdown fences if present."""
    cleaned = text.strip()

    # Strip ```json ... ``` or ``` ... ```
    fence_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", cleaned, re.DOTALL | re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    else:
        any_fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
        if any_fence:
            cleaned = any_fence.group(1).strip()

    # Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object or array anywhere in the text
    for pattern in (r"(\{[\s\S]*\})", r"(\[[\s\S]*\])"):
        m = re.search(pattern, cleaned)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue

    raise ValueError(f"No valid JSON found in response:\n{text[:300]}")


def _build_prompt(user_query: str, history: list[dict]) -> str:
    """Build the full prompt string for a single ChatGPT call."""
    parts = [f"=== SYSTEM ===\n{_SYSTEM_PROMPT}\n"]

    if history:
        parts.append("=== CONVERSATION HISTORY ===")
        for msg in history:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                parts.append(f"[User]\n{content}")
            elif role == "assistant":
                parts.append(f"[Assistant]\n{content}")
            elif role == "tool":
                tool_name = msg.get("name", "tool")
                parts.append(f"[Tool result — {tool_name}]\n{content}")

    parts.append(f"=== USER QUERY ===\n{user_query}")
    parts.append("=== YOUR RESPONSE (JSON only) ===")
    return "\n\n".join(parts)


def _execute_tool(tool_name: str, arguments: dict) -> str:
    """Run a tool call and return a string result ready for the next prompt."""
    try:
        if tool_name == "web_search":
            query = arguments.get("query", "")
            if not query:
                return json.dumps({"error": "Missing 'query' argument."})
            results = engine.search_web(query)
            return json.dumps(results, ensure_ascii=False, indent=2)

        elif tool_name == "fetch_webpage":
            url = arguments.get("url", "")
            if not url:
                return json.dumps({"error": "Missing 'url' argument."})
            page_data = engine.fetch_url(url)
            return json.dumps(page_data, ensure_ascii=False, indent=2)

        else:
            return json.dumps({"error": f"Unknown tool: '{tool_name}'"})

    except Exception as exc:
        print(f"[PhantomSearch] ⚠ Tool '{tool_name}' raised: {exc}")
        return json.dumps({"error": str(exc)})


# ── Main entry-point ─────────────────────────────────────────────────────────

def process_search_query(query: str) -> Any:
    """
    Run the agentic search loop for *query*.

    Returns a Python object (dict or list) that FastAPI will serialise to JSON.
    """
    print(f"[PhantomSearch] ▶ Query: {query!r}")
    history: list[dict] = []
    max_iterations = 6
    last_raw = ""

    for iteration in range(1, max_iterations + 1):
        prompt = _build_prompt(query, history)
        print(f"[PhantomSearch] 🔄 Iteration {iteration}/{max_iterations} — calling ChatGPT…")

        try:
            raw = engine.chat(prompt)
        except Exception as exc:
            print(f"[PhantomSearch] ❌ ChatGPT call failed: {exc}")
            return {"error": "ChatGPT call failed", "detail": str(exc)}

        last_raw = raw
        print(f"[PhantomSearch] 📩 Response ({len(raw)} chars): {raw[:120]}…")

        # Try to parse whatever ChatGPT returned
        try:
            parsed = _parse_json(raw)
        except ValueError as exc:
            print(f"[PhantomSearch] ⚠ JSON parse failed: {exc}")
            history.append({"role": "assistant", "content": raw})
            history.append({
                "role": "tool",
                "name": "system",
                "content": (
                    "Your last response was not valid JSON. "
                    "Please respond with ONLY a valid JSON tool call or ONLY the final JSON answer."
                ),
            })
            continue

        # ── Tool call? ──────────────────────────────────────────────────
        if isinstance(parsed, dict) and "tool_call" in parsed:
            tool_name = parsed["tool_call"]
            arguments  = parsed.get("arguments", {})
            print(f"[PhantomSearch] 🔧 Tool call: {tool_name}({arguments})")

            history.append({"role": "assistant", "content": raw})
            tool_result = _execute_tool(tool_name, arguments)
            print(f"[PhantomSearch] ✅ Tool result ({len(tool_result)} chars)")
            history.append({"role": "tool", "name": tool_name, "content": tool_result})
            continue

        # ── Final answer ────────────────────────────────────────────────
        print("[PhantomSearch] ✔ Final answer received.")
        return parsed

    # Exhausted iterations — try to return whatever we have
    print("[PhantomSearch] ⚠ Max iterations reached.")
    try:
        return _parse_json(last_raw)
    except ValueError:
        return {
            "error": "Could not produce a structured answer within the iteration limit.",
            "last_response": last_raw,
        }
