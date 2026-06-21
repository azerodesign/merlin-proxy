import os
import json
import uuid
import time
import re
from typing import List, Optional, Dict, Any

import requests
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from akun import ACCOUNTS

load_dotenv()

app = FastAPI(
    title="Merlin Proxy Multi-Akun (No-Stream)",
    description="Proxy API Merlin → OpenAI, stream dimatikan paksa",
    version="4.0.0"
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
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "sk-9894908a-3827-446c-9769-cde7065b5b68")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyAvCgtQ4XbmlQGIynDT-v_M8eLaXrKmtiM")
MERLIN_API_URL = "https://www.getmerlin.in/arcane/api/v2/thread/unified"

TOKENS = {}
last_index = -1

print("=" * 60)
print(f"🔐 PROXY API KEY: {PROXY_API_KEY}")
print(f"👥 Total akun: {len(ACCOUNTS)}")
for i, acc in enumerate(ACCOUNTS):
    print(f"  {i+1}. {acc['email']}")
print("=" * 60)
print("⚠️  Streaming dimatikan paksa (Hermes Gateway compatible)")
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
def verify_api_key(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
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
    stream: Optional[bool] = False  # tetap diterima tapi diabaikan

# =============== UTILITY ===============
def generate_uuid() -> str:
    return str(uuid.uuid4())

def login_to_merlin(email: str, password: str, proxy_url: str = None) -> Optional[str]:
    print(f"🔐 Login: {email}")
    if not email or not password:
        return None
    url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    try:
        resp = requests.post(f"{url}?key={FIREBASE_API_KEY}", json=payload, proxies=proxies, timeout=30)
        if resp.status_code == 200:
            token = resp.json().get("idToken")
            if token:
                print(f"✅ Login berhasil: {email}")
                return token
        print(f"❌ Login gagal ({resp.status_code})")
    except Exception as e:
        print(f"❌ Error login: {e}")
    return None

def get_headers_with_token(token: str) -> dict:
    headers = BASE_HEADERS.copy()
    if token:
        headers["Authorization"] = f"Bearer {token}"
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
    # Coba event: message ... data: {...}
    pattern = r'event: message\s+data: ({.*?})\n'
    for match in re.findall(pattern, text, re.DOTALL):
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
    if parts:
        return ''.join(parts).strip()

    # Fallback semua data: {...}
    pattern2 = r'data: ({.*?})\n'
    for match in re.findall(pattern2, text, re.DOTALL):
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
    if parts:
        return ''.join(parts).strip()

    # Fallback terakhir: coba JSON langsung
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if 'response' in data:
                return data['response']
            if 'content' in data:
                return data['content']
            if 'text' in data:
                return data['text']
    except:
        pass

    return ""

def call_merlin_with_account(index: int, payload: dict) -> tuple:
    if index >= len(ACCOUNTS):
        return None, "Akun tidak ditemukan"

    acc = ACCOUNTS[index]
    email = acc["email"]
    proxy_url = acc.get("proxy")

    token = TOKENS.get(index)
    if not token:
        token = login_to_merlin(email, acc["password"], proxy_url)
        if token:
            TOKENS[index] = token
        else:
            return None, f"Gagal login: {email}"

    headers = get_headers_with_token(token)
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    try:
        resp = requests.post(
            MERLIN_API_URL,
            json=payload,
            headers=headers,
            proxies=proxies,
            timeout=180,
            stream=True
        )

        if resp.status_code == 401:
            print(f"⏰ Token expired: {email}, refresh...")
            new_token = login_to_merlin(email, acc["password"], proxy_url)
            if new_token:
                TOKENS[index] = new_token
                headers = get_headers_with_token(new_token)
                resp = requests.post(
                    MERLIN_API_URL,
                    json=payload,
                    headers=headers,
                    proxies=proxies,
                    timeout=180,
                    stream=True
                )
            else:
                return None, f"Refresh gagal: {email}"

        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"

        content = extract_content_from_sse(resp.text)
        if not content:
            return None, "Response kosong"

        return content, None

    except requests.exceptions.Timeout:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)

def get_next_account() -> int:
    global last_index
    if not ACCOUNTS:
        return -1
    last_index = (last_index + 1) % len(ACCOUNTS)
    return last_index

# =============== ENDPOINTS ===============
@app.get("/health")
async def health():
    return {"status": "ok", "accounts": len(ACCOUNTS)}

@app.get("/v1/models")
async def list_models(auth: str = Depends(verify_api_key)):
    return {
        "object": "list",
        "data": [{"id": m, "object": "model", "created": 1700000000, "owned_by": "merlin-proxy"} for m in AVAILABLE_MODELS]
    }

@app.post("/v1/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    auth: str = Depends(verify_api_key)
):
    # 🔥 STREAMING DIMATIKAN PAKSA
    # Hermes Gateway lebih stabil dengan non-stream
    attempts = len(ACCOUNTS)
    if attempts == 0:
        raise HTTPException(503, "Tidak ada akun")

    for _ in range(attempts):
        idx = get_next_account()
        if idx == -1:
            break

        payload = build_merlin_payload(req)
        content, error = call_merlin_with_account(idx, payload)

        if content:
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
        print(f"❌ Akun {idx+1} gagal: {error}")

    raise HTTPException(503, "Semua akun gagal")

@app.get("/")
async def root():
    return {
        "message": "Merlin Proxy (No-Stream)",
        "endpoints": {
            "health": "/health",
            "models": "/v1/models",
            "chat": "/v1/chat/completions"
        },
        "auth": "Bearer token or X-API-Key header",
        "accounts": len(ACCOUNTS)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)