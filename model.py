# model.py - Hanya model yang terbukti OK (dari hasil test)
# ==========================================================

MODEL_MAP = {
    # ========== GOOGLE ==========
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
    
    # ========== GPT ==========
    "gpt-5.5": "gpt-5.5",
    "gpt-5.4": "gpt-5.4",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4.1": "gpt-4.1",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt-3.5-turbo": "gpt-3.5-turbo",
    "o1-mini": "o1-mini",
    "o3-mini": "o3-mini",
    
    # ========== CLAUDE ==========
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
    
    # ========== GROK ==========
    "grok-4.3": "grok-4.3",
    "grok-3": "grok-3",
    
    # ========== DEEPSEEK ==========
    "deepseek-chat": "deepseek-chat",
    
    # ========== GLM ==========
    "glm-5.1": "glm-5.1",
    
    # ========== MINIMAX ==========
    "minimax-m2.7": "minimax-m2.7",
    "minimax-m2.5": "minimax-m2.5",
}

AVAILABLE_MODELS = list(MODEL_MAP.keys())

def get_merlin_model(user_model: str) -> str:
    if user_model in MODEL_MAP:
        return MODEL_MAP[user_model]
    for key, value in MODEL_MAP.items():
        if key.lower() == user_model.lower():
            return value
    return "claude-4.8-opus"

def is_model_supported(model: str) -> bool:
    return model in MODEL_MAP or model.lower() in [k.lower() for k in MODEL_MAP.keys()]

def get_all_models() -> list:
    return sorted(AVAILABLE_MODELS)

def get_models_by_provider(provider: str) -> list:
    provider = provider.lower()
    return sorted([m for m in AVAILABLE_MODELS if provider in m.lower()])

if __name__ == "__main__":
    print("=" * 60)
    print("📋 MODEL YANG DIDUKUNG (Hanya yang OK)")
    print("=" * 60)
    for i, model in enumerate(sorted(AVAILABLE_MODELS), 1):
        print(f"{i:3}. {model}")
    print("=" * 60)
    print(f"✅ Total: {len(AVAILABLE_MODELS)} model aktif")