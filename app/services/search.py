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


def _get_system_prompt() -> str:
    """Build the system prompt with the real current date/time."""
    tz_offset = timedelta(hours=6)
    now = datetime.now(tz=timezone(tz_offset))
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    return f"""\
You are PhantomSearch — a powerful AI research agent with REAL-TIME web browsing.

TODAY'S DATE : {current_date}
CURRENT TIME : {current_time} (+06:00 Bangladesh)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE RULES — NEVER BREAK THESE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. You MUST call web_search FIRST on every query — no exceptions.
2. You MUST call fetch_webpage on at least one promising URL from search results.
3. You MUST NOT return "could not retrieve" without performing at least 2 tool calls.
4. You MUST NOT hallucinate any prices, flight numbers, or data.
5. You MUST output ONLY valid raw JSON — no markdown, no explanations, no prose.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE TOOLS  (output ONE per turn as raw JSON)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tool 1 — web_search
{{"tool_call": "web_search", "arguments": {{"query": "<your search string>"}}}}

Tool 2 — fetch_webpage
{{"tool_call": "fetch_webpage", "arguments": {{"url": "<full https:// URL>"}}}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY WORKFLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1: ALWAYS call web_search first with a targeted query.
Step 2: From the results, pick the best URL (airline site, booking site, finance site, news).
Step 3: Call fetch_webpage on that URL.
Step 4: Extract the exact data the user asked for.
Step 5: If data is incomplete, search again with a different query.
Step 6: When you have enough data, output the FINAL ANSWER JSON.

For FLIGHTS — good sources: Google Flights, Skyscanner, kayak.com, airline official sites
For STOCKS  — good sources: finance.yahoo.com, google.com/finance, marketwatch.com
For NEWS    — good sources: direct news site URLs from search results
For WEATHER — good sources: weather.com, timeanddate.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL ANSWER FORMAT (raw JSON only, no wrapper)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Output the answer as a clean JSON object or array that directly answers the user.

Flights example:
{{"query": "DAC to JFK {current_date}", "results": [{{"airline": "...", "departure": "...", "arrival": "...", "price": "..."}}]}}

Stocks example:
{{"ticker": "AAPL", "price": 195.50, "currency": "USD", "as_of": "..."}}

Only return this if ALL tool calls exhausted with zero data:
{{"error": "No data found", "reason": "<specific reason after searching>", "searched": ["<url1>", "<url2>"]}}
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


def _build_prompt(user_query: str, history: list) -> str:
    """Build the full prompt string for a single ChatGPT call."""
    parts = [f"=== SYSTEM ===\n{_get_system_prompt()}\n"]

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
    parts.append("=== YOUR RESPONSE (raw JSON only, no prose) ===")
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
    history: list = []
    max_iterations = 8
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
