from fastapi import FastAPI, Request
import redis
import os
import re
import json

app = FastAPI()

# O Railway injeta as variáveis automaticamente. 
# Se você tiver vinculado o serviço Redis ao seu serviço Python, 
# a variável REDIS_URL já estará disponível.
REDIS_URL = os.getenv("REDIS_URL")

# Se o Railway fornecer variáveis separadas (comum em versões novas), montamos a URL:
if not REDIS_URL:
    REDIS_HOST = os.getenv("REDISHOST", "localhost")
    REDIS_PORT = os.getenv("REDISPORT", "6379")
    REDIS_PASS = os.getenv("REDISPASSWORD", "")
    REDIS_URL = f"redis://:{REDIS_PASS}@{REDIS_HOST}:{REDIS_PORT}"

# Inicializa o Redis
r = redis.from_url(REDIS_URL, decode_responses=True)

def extrair_otp(texto):
    if not texto:
        return None
    # Procura por uma sequência de 6 dígitos no texto
    match = re.search(r'\b\d{6}\b', texto)
    return match.group(0) if match else None

@app.get("/")
def home():
    return {"status": "Proxy de OTP Online"}

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    try:
        events = await request.json()
        
        # Log para você ver o JSON bruto no Railway Logs
        print(f"Evento recebido: {json.dumps(events)}")
        
        for event in events:
            email = event.get("email")
            
            # Tenta pegar o OTP de 3 lugares possíveis:
            # 1. De um argumento customizado (mais seguro)
            # 2. Do corpo do e-mail (se o SendGrid estiver configurado para isso)
            # 3. De metadados do evento
            otp = event.get("otp_code") or extrair_otp(event.get("body", ""))
            
            if email and otp:
                # Salva o código por 2 minutos
                r.set(f"otp:{email}", otp, ex=120)
                print(f"SUCESSO: OTP {otp} armazenado para {email}")
            else:
                print(f"AVISO: Evento recebido para {email}, mas nenhum OTP encontrado.")
                
        return {"status": "received"}
    except Exception as e:
        print(f"ERRO no Webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/check-otp")
async def check_otp(email: str):
    otp = r.get(f"otp:{email}")
    if otp:
        return {"status": "found", "otp": otp}
    return {"status": "pending", "message": "Aguardando e-mail do SendGrid..."}