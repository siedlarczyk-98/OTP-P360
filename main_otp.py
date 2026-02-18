from fastapi import FastAPI, Request
import redis
import os
import re
import json
import asyncio

# Imports do Playwright
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

app = FastAPI()

# Configuração do Redis
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    REDIS_HOST = os.getenv("REDISHOST", "localhost")
    REDIS_PORT = os.getenv("REDISPORT", "6379")
    REDIS_PASS = os.getenv("REDISPASSWORD", "")
    REDIS_URL = f"redis://:{REDIS_PASS}@{REDIS_HOST}:{REDIS_PORT}"

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
        events = await request.json()
        print(f"DEBUG: Recebido {len(events)} eventos")

        for event in events:
            email = event.get("email", "").lower()
            if not email.endswith(DOMINIO_PERMITIDO):
                print(f"BLOQUEADO: Domínio inválido para {email}")
                continue
            
            otp = event.get("otp_code") or extrair_otp(event.get("body", ""))
            
            if email and otp:
                r.set(f"otp:{email}", otp, ex=120) 
                print(f"SUCESSO: OTP {otp} armazenado para {email}")
            
        return {"status": "received"}
    except Exception as e:
        print(f"ERRO NO WEBHOOK: {str(e)}")
        return {"status": "error", "message": "check logs"}

@app.get("/login-automatizado")
async def login_automatizado(email: str):
    email = email.lower()
    
    # Inicia o contexto do Playwright
    async with async_playwright() as p:
        # Lança o navegador. No Railway,headless=True é obrigatório.
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await stealth_async(page) # Aplica técnicas para evitar detecção

        try:
            # 1. ACESSO: Mude para a URL real da plataforma
            await page.goto("https://plataforma-do-cliente.com/login", wait_until="networkidle")
            
            # 2. EMAIL: Preenche o campo de e-mail (ajuste o seletor se necessário)
            await page.fill('input[type="email"]', email)
            await page.keyboard.press("Enter") # Ou page.click("seletor-do-botao")

            # 3. ESPERA (POLLING): Aguarda o OTP chegar no Redis
            otp = None
            for _ in range(15): # Tenta por ~22 segundos (15 * 1.5s)
                otp = r.get(f"otp:{email}")
                if otp:
                    break
                await asyncio.sleep(1.5)
            
            if not otp:
                await browser.close()
                return {"status": "error", "message": "Timeout: OTP não chegou no Redis"}

            # 4. OTP: Preenche o código (ajuste o seletor)
            # Dica: use page.locator('input[name="otp"]').fill(otp) se o fill direto falhar
            await page.fill('input[name="otp_field_name"]', otp)
            await page.keyboard.press("Enter")
            
            # 5. FINALIZAÇÃO: Aguarda carregar a home pós-login
            await page.wait_for_load_state("networkidle")

            # 6. CAPTURA: Pega os cookies de autenticação
            cookies = await context.cookies()
            
            await browser.close()
            return {
                "status": "success",
                "email": email,
                "cookies": cookies
            }

        except Exception as e:
            await browser.close()
            return {"status": "error", "message": str(e)}