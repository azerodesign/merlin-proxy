import os
import json
import uuid
import requests
import re
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Merlin Proxy",
    description="Proxy API Merlin ke format OpenAI dengan auto-refresh token & API Key auth",
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

# Tampilkan API key di log startup (untuk Railway)
print("=" * 60)
print("🔐 PROXY API KEY (gunakan untuk autentikasi):")
print(f"   {PROXY_API_KEY}")
print("=" * 60)
print("📌 Cara pakai: kirim header 'X-API-Key' atau 'Authorization: Bearer <key>'")
print("=" * 60)

BASE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/event-stream, text/event-stream",
    "x-merlin-version": "web-merlin",
    "Origin": "https://www.getmerlin.in",
    "Referer": "https://www.getmerlin.in/id/chat"
}

# =============== MODEL ===============
# Daftar model yang tersedia (dari model.py)
AVAILABLE_MODELS = [
    "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4-turbo", "gpt-3.5-turbo",
    "o1-mini", "o3-mini",
    "claude-4.8-opus", "claude-4.7-opus", "claude-4.6-opus", "claude-4.6-sonnet",
    "claude-4.5-haiku", "claude-3.7-sonnet", "claude-3.5-sonnet",
    "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
    "gemini-3.5-flash", "gemini-3.1-pro", "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash",
    "gemini-2.0-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash",
    "grok-4.3", "grok-3",
    "deepseek-chat",
    "glm-5.1",
    "minimax-m2.7", "minimax-m2.5"
]

MODEL_MAP = {
    "gpt-4o": "claude-4.8-opus",
    "gpt-4o-mini": "claude-4.8-opus",
    "gpt-4.1": "claude-4.8-opus",
    "gpt-4-turbo": "claude-4.8-opus",
    "gpt-3.5-turbo": "claude-4.8-opus",
    "o1-mini": "claude-4.8-opus",
    "o3-mini": "claude-4.8-opus",
    "claude-4.8-opus": "claude-4.8-opus",
    "claude-4.7-opus": "claude-4.7-opus",
    "claude-4.6-opus": "claude-4.6-opus",
    "claude-4.6-sonnet": "claude-4.6-sonnet",
    "claude-4.5-haiku": "claude-4.5-haiku",
    "claude-3.7-sonnet": "claude-3.7-sonnet",
    "claude-3.5-sonnet": "claude-3.5-sonnet",
    "claude-3-opus": "claude-3-opus",
    "claude-3-sonnet": "claude-3-sonnet",
    "claude-3-haiku": "claude-3-haiku",
    "gemini-3.5-flash": "gemini-3.5-flash",
    "gemini-3.1-pro": "gemini-3.1-pro",
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite": "gemini-2.5-flash-lite",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.0-pro": "gemini-2.0-pro",
    "gemini-2.0-flash": "gemini-2.0-flash",
    "gemini-1.5-pro": "gemini-1.5-pro",
    "gemini-1.5-flash": "gemini-1.5-flash",
    "grok-4.3": "grok-4.3",
    "grok-3": "grok-3",
    "deepseek-chat": "deepseek-chat",
    "glm-5.1": "glm-5.1",
    "minimax-m2.7": "minimax-m2.7",
    "minimax-m2.5": "minimax-m2.5",
}

def get_merlin_model(user_model: str) -> str:
    return MODEL_MAP.get(user_model, "claude-4.8-opus")
# ===========================================

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "claude-4.8-opus"
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000
    stream: Optional[bool] = False

# =============== AUTH ===============
def verify_api_key(authorization: Optional[str] = Header(None), x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    # Coba dari Authorization: Bearer <key>
    api_key = None
    if authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]
    elif x_api_key:
        api_key = x_api_key
    
    if not api_key:
        raise HTTPException(status_code=401, detail="API Key required. Provide 'Authorization: Bearer <key>' or 'X-API-Key: <key>' header")
    
    if api_key != PROXY_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
    return api_key
# ===========================================

def generate_uuid():
    return str(uuid.uuid4())

def login_to_merlin() -> str:
    print("🔐 Mencoba login otomatis ke Merlin...")
    if not MERLIN_EMAIL or not MERLIN_PASSWORD:
        print("❌ Email atau password tidak diisi di .env")
        return None
    if not FIREBASE_API_KEY:
        print("❌ Firebase API Key tidak diisi di .env")
        return None
    
    login_url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    payload = {"email": MERLIN_EMAIL, "password": MERLIN_PASSWORD, "returnSecureToken": True}
    
    try:
        resp = requests.post(f"{login_url}?key={FIREBASE_API_KEY}", json=payload, timeout=30)
        if resp.status_code == 200:
            token = resp.json().get("idToken")
            if token:
                print("✅ Login berhasil, token baru didapat.")
                return token
    except Exception as e:
        print(f"❌ Error login: {str(e)}")
    return None

def get_headers_with_token(token=None):
    headers = BASE_HEADERS.copy()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    return headers

def build_merlin_payload(openai_req: ChatCompletionRequest) -> Dict[str, Any]:
    user_messages = [m for m in openai_req.messages if m.role == "user"]
    last_user_msg = user_messages[-1] if user_messages else openai_req.messages[-1]
    merlin_model = get_merlin_model(openai_req.model)
    chat_id = generate_uuid()
    message_id = generate_uuid()
    child_id = generate_uuid()
    return {
        "attachments": [],
        "chatId": chat_id,
        "language": "AUTO",
        "message": {
            "childId": child_id,
            "content": last_user_msg.content,
            "context": "",
            "id": message_id,
            "parentId": "root"
        },
        "mode": "UNIFIED_CHAT",
        "model": merlin_model,
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

def extract_content_from_sse(response_text: str) -> str:
    content_parts = []
    pattern = r'data: ({.*?})\n'
    for match in re.findall(pattern, response_text, re.DOTALL):
        try:
            data = json.loads(match)
            if not isinstance(data, dict):
                continue
            if 'data' in data and isinstance(data['data'], dict):
                inner = data['data']
                if 'text' in inner and inner['text']:
                    content_parts.append(inner['text'])
                elif 'content' in inner and inner['content']:
                    content_parts.append(inner['content'])
            if 'text' in data and data['text']:
                content_parts.append(data['text'])
            elif 'content' in data and data['content']:
                content_parts.append(data['content'])
            if 'payload' in data and isinstance(data['payload'], dict):
                if 'text' in data['payload'] and data['payload']['text']:
                    content_parts.append(data['payload']['text'])
        except:
            continue
    return ''.join(content_parts).strip()

def call_merlin_with_retry(payload, token, max_retries=2):
    global AUTH_TOKEN
    for attempt in range(max_retries + 1):
        headers = get_headers_with_token(token or AUTH_TOKEN)
        try:
            resp = requests.post(MERLIN_API_URL, json=payload, headers=headers, timeout=120, stream=True)
            if resp.status_code == 401 and attempt < max_retries:
                print("⏰ Token expired, mencoba refresh...")
                new_token = login_to_merlin()
                if new_token:
                    AUTH_TOKEN = new_token
                    token = new_token
                    try:
                        with open('.env', 'r') as f:
                            lines = f.readlines()
                        with open('.env', 'w') as f:
                            for line in lines:
                                if line.startswith('AUTH_TOKEN='):
                                    f.write(f'AUTH_TOKEN={new_token}\n')
                                else:
                                    f.write(line)
                    except:
                        pass
                    continue
            return resp
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                print(f"⚠️ Retry {attempt+1}/{max_retries}: {str(e)}")
                continue
            raise e
    raise HTTPException(status_code=502, detail="Gagal hubungi Merlin")

# =============== ENDPOINTS ===============

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/v1/models")
async def list_models(auth: str = Depends(verify_api_key)):
    """Endpoint untuk list model (OpenAI compatible)"""
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": 1700000000,
                "owned_by": "merlin-proxy"
            }
            for model_id in AVAILABLE_MODELS
        ]
    }

@app.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionRequest, auth: str = Depends(verify_api_key)):
    payload = build_merlin_payload(body)
    print("📤 Payload:", json.dumps(payload, indent=2)[:500])
    
    resp = call_merlin_with_retry(payload, None)
    content = extract_content_from_sse(resp.text)
    print("🔍 Hasil:", content[:100] if content else "(kosong)")
    
    if not content:
        content = "Maaf, saya tidak dapat memproses permintaan Anda."
    
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(uuid.uuid4().time_low),
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }

# =============== ROOT ===============
@app.get("/")
async def root():
    return {
        "message": "Merlin Proxy is running",
        "endpoints": {
            "health": "/health",
            "models": "/v1/models",
            "chat": "/v1/chat/completions"
        },
        "auth": "API Key required (Bearer token or X-API-Key header)"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)