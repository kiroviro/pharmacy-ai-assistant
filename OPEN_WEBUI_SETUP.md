# Open WebUI Setup for ViaPharma

This guide explains how to run ViaPharma with Open WebUI as the frontend.

## Architecture

```
┌─────────────────┐     HTTP/REST     ┌─────────────────┐
│   Open WebUI    │ ───────────────▶  │  API Server     │
│   (Frontend)    │    /v1/chat/...   │  (FastAPI)      │
│   Port 3000     │                   │  Port 8000      │
└─────────────────┘                   └────────┬────────┘
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │    Pipeline     │
                                      │   (MedGemma)    │
                                      └─────────────────┘
```

## Step 1: Start the API Server

First, start the ViaPharma API server:

```bash
# From the project directory
python api_server.py
```

The server will start on `http://localhost:8000`. You should see:
```
Starting ViaPharma API server...
OpenAI-compatible endpoints available at:
  - GET  /v1/models
  - POST /v1/chat/completions

Connect Open WebUI to: http://localhost:8000/v1
```

Verify it's working:
```bash
# Check models endpoint
curl http://localhost:8000/v1/models

# Check health status
curl http://localhost:8000/health

# Get Bulgarian hints for UI
curl http://localhost:8000/hints
```

## Step 2: Install Open WebUI

### Option A: Docker (Recommended)

```bash
docker run -d \
  --name open-webui \
  -p 3000:8080 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=dummy \
  -e WEBUI_AUTH=false \
  -v open-webui:/app/backend/data \
  ghcr.io/open-webui/open-webui:main
```

**Note for Linux:** Replace `host.docker.internal` with your machine's IP address or use `--network host`.

### Option B: pip install

```bash
pip install open-webui
open-webui serve --port 3000
```

Then configure the API endpoint in the UI settings.

## Step 3: Configure Open WebUI

1. Open `http://localhost:3000` in your browser
2. Create an account (first user becomes admin)
3. Go to **Settings** → **Connections**
4. Under **OpenAI API**:
   - **API Base URL**: `http://localhost:8000/v1`
   - **API Key**: `dummy` (any value works, not validated)
5. Click **Save**

## Step 4: Select the Model

1. In the chat interface, click on the model selector (top left)
2. Select **viapharma-medgemma**
3. Start chatting in Bulgarian!

## Optional: Configure System Prompt

To set up the Bulgarian pharmacy assistant persona:

1. Go to **Settings** → **Models**
2. Click on **viapharma-medgemma**
3. Add a system prompt:

```
Вие сте ViaPharma Аптечен Асистент - виртуален фармацевтичен консултант.

Вашата роля:
- Разбирате симптоми, описани на български език
- Препоръчвате подходящи продукти без рецепта (OTC)
- Давате информация за дозировка и предупреждения

Важно: При сериозни симптоми насочвайте към лекар.
```

## Running Both Services

For convenience, you can run both services:

**Terminal 1 - API Server:**
```bash
python api_server.py
```

**Terminal 2 - Open WebUI (Docker):**
```bash
docker start open-webui
# or if first time:
docker run -d --name open-webui -p 3000:8080 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=dummy \
  ghcr.io/open-webui/open-webui:main
```

## Troubleshooting

### "Connection refused" error
- Ensure the API server is running on port 8000
- Check firewall settings

### Model not appearing
- Verify the API is responding: `curl http://localhost:8000/v1/models`
- Refresh the Open WebUI page

### Docker can't connect to localhost
- Use `host.docker.internal` (Mac/Windows) or `--network host` (Linux)
- Or use your machine's IP address instead of localhost

### Slow first response
- MedGemma loads on first request (~30-60 seconds)
- Subsequent requests will be faster
