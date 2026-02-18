from fastapi import FastAPI, Request
import redis
import os
import re
import json

app = FastAPI()

# Configuração robusta do Redis
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    REDIS_HOST = os.getenv("REDISHOST", "localhost")
    REDIS_PORT = os.getenv("REDISPORT", "6379")
    REDIS_PASS = os.getenv("REDISPASSWORD", "")
    REDIS_URL = f"redis://:{REDIS_PASS}@{REDIS_HOST}:{REDIS_PORT}"

# decode_responses=True evita que você receba 'bytes' e tenha que dar .decode() depois
r = redis.from_url(REDIS_URL, decode_responses=True)

DOMINIO_PERMITIDO = "@uide.edu.ec"

def extrair_otp(texto):
    if not texto:
        return None
    match = re.search(r'\b\d{6}\b', texto)
    return match.group(0) if match else None

@app.get("/")
def home():
    try:
        r.ping()
        status_redis = "Conectado"
    except Exception:
        status_redis = "Erro de conexão"
    
    return {
        "status": "Proxy de OTP Online",
        "filtro_dominio": DOMINIO_PERMITIDO,
        "redis": status_redis
    }

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    try:
        # Importante: O SendGrid pode enviar uma lista de eventos
        events = await request.json()
        
        # Log para debug no Railway
        print(f"DEBUG: Recebido {len(events)} eventos")

        for event in events:
            email = event.get("email", "").lower()
            
            # Filtro de domínio
            if not email.endswith(DOMINIO_PERMITIDO):
                print(f"BLOQUEADO: Domínio inválido para {email}")
                continue
            
            # Captura o OTP (tenta args customizados primeiro, depois texto)
            otp = event.get("otp_code") or extrair_otp(event.get("body", ""))
            
            if email and otp:
                # Chave com prefixo ajuda na organização do Redis
                r.set(f"otp:{email}", otp, ex=120) 
                print(f"SUCESSO: OTP {otp} armazenado para {email}")
            else:
                print(f"AVISO: Dados insuficientes no evento para {email}")
            
        return {"status": "received"}
    except Exception as e:
        print(f"ERRO CRÍTICO NO WEBHOOK: {str(e)}")
        # Retornamos 200 mesmo no erro para o SendGrid não ficar tentando reenviar infinitamente
        return {"status": "error", "message": "check logs"}

@app.get("/check-otp")
async def check_otp(email: str):
    email = email.lower()
    otp = r.get(f"otp:{email}")
    if otp:
        return {"status": "found", "otp": otp}
    return {"status": "pending", "message": "OTP ainda não recebido ou expirado."}