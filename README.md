# 👻 PhantomAPI

A FastAPI backend that turns the free ChatGPT web interface into a powerful **AI Search & Chat API** — no OpenAI key required.

Uses [Playwright](https://playwright.dev/) to drive a real Chrome browser, giving you:
- **`/v1/chat/completions`** — OpenAI-compatible chat endpoint
- **`/v1/responses`** — Modern Responses API endpoint
- **`/search`** — Agentic natural-language search that browses the web and returns structured JSON

---

## Features

- 🔍 **Human-language search** — ask anything, get back structured JSON (flights, stock prices, news, weather, …)
- 🤖 **Agentic web browsing** — automatically searches DuckDuckGo / Google and fetches relevant pages via Playwright
- 🔒 **API key auth** — all endpoints protected by a Bearer token
- 🌐 **OpenAI-compatible** — drop-in replacement for `/v1/chat/completions`
- 🖥️ **Built-in chat GUI** — served at `/gui`

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chrome
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set a strong API_SECRET_KEY
```

### 3. Run

```bash
python run.py
```

Server starts at `http://127.0.0.1:7777`

Open the chat UI: **http://127.0.0.1:7777/gui**

---

## API Reference

All endpoints require:
```
Authorization: Bearer <API_SECRET_KEY>
```

### `GET /search` — Natural Language Search

```bash
curl "http://localhost:7777/search?q=find+me+flights+from+Dhaka+to+JFK+today" \
  -H "Authorization: Bearer your-secret-key"
```

### `POST /search` — Natural Language Search (POST)

```bash
curl -X POST "http://localhost:7777/search" \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"q": "Find me last 6 months GP stock prices"}'
```

**Example response — flights:**
```json
{
  "search": {
    "origin": "DAC",
    "destination": "Any US Airport",
    "departure_date": "2026-07-20"
  },
  "results": [
    {
      "airline": "Qatar Airways",
      "flight_number": "QR639",
      "departure": {"airport": "DAC", "time": "03:15"},
      "arrival": {"airport": "JFK", "time": "15:30"},
      "stops": 1,
      "price": {"amount": 1185, "currency": "USD"}
    }
  ],
  "total_results": 17
}
```

**Example response — stock prices:**
```json
[
  {"date": "2026-07-16", "open": 258.6, "high": 259.0, "low": 257.2, "close": 257.5, "volume": 118570},
  {"date": "2026-07-15", "open": 259.0, "high": 259.0, "low": 256.6, "close": 257.5, "volume": 254210}
]
```

### `POST /v1/chat/completions` — OpenAI-compatible chat

```bash
curl -X POST "http://localhost:7777/v1/chat/completions" \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}], "model": "gpt-4o-mini"}'
```

### `GET /v1/models` — List models

```bash
curl "http://localhost:7777/v1/models" \
  -H "Authorization: Bearer your-secret-key"
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `API_SECRET_KEY` | `change-me` | Bearer token for all endpoints |
| `HOST` | `127.0.0.1` | Server bind host |
| `PORT` | `7777` | Server port |
| `HEADLESS` | `true` | Run Chrome headlessly |
| `BROWSER_TIMEOUT` | `120000` | Browser timeout in ms |

---

## Project Structure

```
PhantomAPI/
├── app/
│   ├── api/v1/
│   │   ├── chat.py        # POST /v1/chat/completions
│   │   ├── responses.py   # POST /v1/responses
│   │   ├── models.py      # GET /v1/models
│   │   └── search.py      # GET+POST /search & /v1/search
│   ├── services/
│   │   ├── browser.py     # Playwright engine (chat + web search + fetch)
│   │   ├── chat.py        # Chat service logic
│   │   └── search.py      # Agentic search loop
│   ├── schemas/           # Pydantic request/response models
│   ├── utils/             # Prompt builder, parser
│   ├── config.py
│   ├── dependencies.py
│   └── main.py
├── static/
│   └── index.html         # Chat GUI
├── tests/
├── run.py                 # Entry point
└── requirements.txt
```

---

## How the Search Works

1. User sends a natural-language query (e.g. *"find flights from Dhaka to US today"*)
2. ChatGPT (via Playwright) decides what to search
3. PhantomAPI searches DuckDuckGo → picks best URLs → fetches pages with Playwright
4. Page content is fed back to ChatGPT
5. ChatGPT returns a clean, structured JSON answer

Up to **6 reasoning iterations** are performed automatically.

---

## License

MIT
