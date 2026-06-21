import os
import json
import uuid
import time
import re
import asyncio
from typing import List, Optional, Dict, Any, AsyncGenerator

import requests
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Merlin Proxy",
    description="OpenAI-compatible proxy for Merlin AI",
    version="2.0.0"
)

# =============== CORS ===============
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============== KONFIGURASI ===============
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
MERLIN_API_URL = os.getenv("MERLIN_API_URL", "https://www.getmerlin.in/arcane/api/v2/thread/unified")
MERLIN_EMAIL = os.getenv("MERLIN_EMAIL", "")
MERLIN_PASSWORD = os.getenv("MERLIN_PASSWORD", "")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "sk-9894908a-3827-446c-9769-cde7065b5b68")

print("=" * 60)
print("🔐 PROXY API KEY:", PROXY_API_KEY)
print("=" * 60)

BASE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/event-stream, text/event-stream",
    "x-merlin-version": "web-merlin",
    "Origin": "https://www.getmerlin.in",
    "Referer": "https://www.getmerlin.in/id/chat"
}

# =============== MODEL LIST ===============
AVAILABLE_MODELS = [
    "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4-turbo", "gpt-3.5-turbo",
    "o1-mini", "o3-mini",
    "claude-4.8-opus", "claude-4.7-opus", "claude-4.6-opus",
    "claude-4.6-sonnet", "claude-4.5-haiku",
    "claude-3.7-sonnet", "claude-3.5-sonnet",
    "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
    "gemini-3.5-flash", "gemini-3.1-pro", "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash",
    "gemini-2.0-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash",
    "grok-4.3", "grok-3",
    "deepseek-chat", "glm-5.1", "minimax-m2.7", "minimax-m2.5"
]

MODEL_MAP = {m: m for m in AVAILABLE_MODELS}
MODEL_MAP.update({
    "gpt-4o": "claude-4.8-opus",
    "gpt-4o-mini": "claude-4.8-opus",
    "gpt-4.1": "claude-4.8-opus",
    "gpt-4-turbo": "claude-4.8-opus",
    "gpt-3.5-turbo": "claude-4.8-opus",
    "o1-mini": "claude-4.8-opus",
    "o3-mini": "claude-4.8-opus",
})

def get_merlin_model(user_model: str) -> str:
    return MODEL_MAP.get(user_model, "claude-4.8-opus")

# =============== AUTH ===============
def verify_api_key(authorization: Optional[str] = Header(None), x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    api_key = None
    if authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]
    elif x_api_key:
        api_key = x_api_key
    if not api_key:
        raise HTTPException(status_code=401, detail="API Key required")
    if api_key != PROXY_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

# =============== CLASS ===============
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "claude-4.8-opus"
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000
    stream: Optional[bool] = False

# =============== MERLIN FUNCTIONS ===============
def generate_uuid():
    return str(uuid.uuid4())

def login_to_merlin() -> str:
    print("🔐 Mencoba login otomatis...")
    if not MERLIN_EMAIL or not MERLIN_PASSWORD or not FIREBASE_API_KEY:
        return None
    url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    try:
        resp = requests.post(
            f"{url}?key={FIREBASE_API_KEY}",
            json={"email": MERLIN_EMAIL, "password": MERLIN_PASSWORD, "returnSecureToken": True},
            timeout=30
        )
        if resp.status_code == 200:
            token = resp.json().get("idToken")
            if token:
                print("✅ Login berhasil")
                return token
    except Exception as e:
        print(f"❌ Login error: {e}")
    return None

def get_headers_with_token(token=None):
    headers = BASE_HEADERS.copy()
    t = token or AUTH_TOKEN
    if t:
        headers["Authorization"] = f"Bearer {t}"
    return headers

def build_merlin_payload(req: ChatCompletionRequest) -> Dict[str, Any]:
    user_msgs = [m for m in req.messages if m.role == "user"]
    last = user_msgs[-1] if user_msgs else req.messages[-1]
    return {
        "attachments": [],
        "chatId": generate_uuid(),
        "language": "AUTO",
        "message": {
            "childId": generate_uuid(),
            "content": last.content,
            "context": "",
            "id": generate_uuid(),
            "parentId": "root"
        },
        "mode": "UNIFIED_CHAT",
        "model": get_merlin_model(req.model),
        "metadata": {
            "noTask": True,
            "isWebpageChat": False,
            "deepResearch": False,
            "webAccess": True,
            "proFinderMode": False,
            "mcpConfig": {"isEnabled": False},
            "merlinMagic": False
        }
    }

def extract_content_from_sse(text: str) -> str:
    parts = []
    for match in re.findall(r'data: ({.*?})\n', text, re.DOTALL):
        try:
            data = json.loads(match)
            if 'data' in data and isinstance(data['data'], dict):
                inner = data['data']
                if inner.get('text'):
                    parts.append(inner['text'])
                elif inner.get('content'):
                    parts.append(inner['content'])
            if data.get('text'):
                parts.append(data['text'])
            elif data.get('content'):
                parts.append(data['content'])
        except:
            continue
    return ''.join(parts).strip()

def call_merlin(payload):
    global AUTH_TOKEN
    for attempt in range(3):
        headers = get_headers_with_token(AUTH_TOKEN)
        resp = requests.post(MERLIN_API_URL, json=payload, headers=headers, timeout=120, stream=True)
        if resp.status_code == 401:
            print("⏰ Token expired, refresh...")
            new = login_to_merlin()
            if new:
                AUTH_TOKEN = new
                continue
        return resp
    raise HTTPException(502, "Gagal hubungi Merlin")

# =============== STREAMING ===============
async def stream_generator(payload, model):
    resp = call_merlin(payload)
    full_content = ""
    for line in resp.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                try:
                    data = json.loads(line[6:])
                    if 'data' in data and isinstance(data['data'], dict):
                        text = data['data'].get('text', '')
                        if text:
                            full_content += text
                            chunk = {
                                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": text},
                                    "finish_reason": None
                                }]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                except:
                    pass
    # Send final chunk
    final = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop"
        }]
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"

# =============== ENDPOINTS ===============
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/v1/models")
async def list_models(auth: str = Depends(verify_api_key)):
    return {
        "object": "list",
        "data": [
            {"id": m, "object": "model", "created": 1700000000, "owned_by": "merlin-proxy"}
            for m in AVAILABLE_MODELS
        ]
    }

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, auth: str = Depends(verify_api_key)):
    if req.stream:
        payload = build_merlin_payload(req)
        return StreamingResponse(
            stream_generator(payload, req.model),
            media_type="text/event-stream"
        )
    else:
        payload = build_merlin_payload(req)
        resp = call_merlin(payload)
        content = extract_content_from_sse(resp.text)
        if not content:
            content = "Maaf, tidak dapat memproses permintaan."
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

@app.get("/")
async def root():
    return {
        "message": "Merlin Proxy running",
        "endpoints": {
            "health": "/health",
            "models": "/v1/models",
            "chat": "/v1/chat/completions"
        },
        "auth": "Bearer token or X-API-Key header"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)