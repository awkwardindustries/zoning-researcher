## Run Locally

### Prerequisites
- Python >= 3.11
- Azure OpenAI Endpoint
- Azure OpenAI Key
- Azure OpenAI Model / Deployment Name

### Run script

```bash
# Create a virtual environment
python -m venv .browser-venv
source .browser-venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install

# Run using stdio transport (default)
uv run browser_tool

# Run using SSE transport on custom port (default 8000)
uv run browser_tool --transport sse --port 8080
```