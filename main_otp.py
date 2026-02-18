from fastapi import FastAPI, Request, BackgroundTasks
import redis
import os
import re

app = FastAPI()

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(redis_url, decode_responses=True)

def extrair_otp(texto):
    # Procura por uma sequência de 6 dígitos no texto
    match = re.search(r'\b\d{6}\b', texto)
    return match.group(0) if match else None

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    events = await request.json()
    
    for event in events:
        email = event.get("email")
        text_content = event.get("body", "") 
        otp = extrair_otp(text_content)
        
        if email and otp:
            # Salva o código por 2 minutos
            r.set(f"otp:{email}", otp, ex=120)
            print(f"OTP {otp} recebido para {email}")
            
    return {"status": "received"}

@app.get("/check-otp")
async def check_otp(email: str):
    otp = r.get(f"otp:{email}")
    return {"otp": otp} if otp else {"status": "pending"}