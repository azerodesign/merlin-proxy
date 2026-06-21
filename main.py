import os
import json
import uuid
import requests
import re
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Merlin Proxy",
    description="Proxy API Merlin ke format OpenAI dengan auto-refresh token & API Key auth",
    version="2.0.0"
)

# =============== KONFIGURASI ===============
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
MERLIN_API_URL = os.getenv("MERLIN_API_URL", "https://www.getmerlin.in/arcane/api/v2/thread/unified")
MERLIN_EMAIL = os.getenv("MERLIN_EMAIL", "")
MERLIN_PASSWORD = os.getenv("MERLIN_PASSWORD", "")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")

# =============== API KEY STATIS ===============
# Gunakan key dari environment, atau default key yang diberikan
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "sk-9894908a-3827-446c-9769-cde7065b5b68")

# Tampilkan API key di log saat startup (agar terlihat di Railway logs)
print("=" * 60)
print("🔐 PROXY API KEY (gunakan ini untuk autentikasi):")
print(f"   {PROXY_API_KEY}")
print("=" * 60)
print("📌 Cara pakai: kirim header 'X-API-Key: <key>' pada setiap request")
print("=" * 60)

# Fungsi validasi API key
def verify_api_key(api_key: str = Header(None, alias="X-API-Key")):
    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    if api_key != PROXY_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key
# ===========================================

BASE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/event-stream, text/event-stream",
    "x-merlin-version": "web-merlin",
    "Origin": "https://www.getmerlin.in",
    "Referer": "https://www.getmerlin.in/id/chat"
}

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "claude-4.8-opus"
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000
    stream: Optional[bool] = False

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
    
    # Mapping model (bisa diambil dari model.py, tapi di sini sederhana)
    model_map = {
        "gpt-4o": "claude-4.8-opus",
        "gpt-4": "claude-4.8-opus",
        "claude-3.5-sonnet": "claude-4.8-opus",
        "claude-4.8-opus": "claude-4.8-opus"
    }
    merlin_model = model_map.get(openai_req.model, "claude-4.8-opus")
    
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
                    # Simpan ke .env
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

@app.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    auth: str = Depends(verify_api_key)  # <-- API Key authentication
):
    payload = build_merlin_payload(body)
    print("📤 Payload:", json.dumps(payload, indent=2)[:500])
    
    resp = call_merlin_with_retry(payload, None)
    content = extract_content_from_sse(resp.text)
    print("🔍 Hasil:", content[:100] if content else "(kosong)")
    
    if not content:
        content = "Maaf, saya tidak dapat memproses permintaan Anda."
    
    return JSONResponse(content={
        "choices": [{
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
            "index": 0
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    })

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)