## Run Locally

### Prerequisites
- Python >= 3.11
- Environment (expected at root `.env`)
   - Azure OpenAI Endpoint
   - Azure OpenAI Key
   - Azure OpenAI Model / Deployment Name

### Run script

```bash
# Run using stdio transport (default)
uv run browser_server

# Run using SSE transport on custom port (default 8000)
uv run browser_server --transport sse --port 8080
```