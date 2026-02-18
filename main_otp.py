from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import redis
import os
import re
import json
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async_inject

app = FastAPI()

# --- CONFIGURAÇÃO REDIS ---
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    host = os.getenv("REDISHOST", "localhost")
    port = os.getenv("REDISPORT", "6379")
    password = os.getenv("REDISPASSWORD", "")
    REDIS_URL = f"redis://:{password}@{host}:{port}"

r = redis.from_url(REDIS_URL, decode_responses=True)

# --- CONFIGURAÇÕES DE NEGÓCIO ---
DOMINIO_PERMITIDO = "@uide.edu.ec"

# Regex poliglota para os botões e campos (PT, ES, EN)
REGEX_BOTAO_LOGIN = re.compile(r"(Receber|Recibir|Get).*(chave|clave|key|acceso|access)", re.I)
REGEX_CAMPO_EMAIL = re.compile(r"email|correo|usuario|user", re.I)
REGEX_CAMPO_OTP = re.compile(r"código|code|clave|otp", re.I)

def extrair_otp(texto):
    if not texto: return None
    match = re.search(r'\b\d{6}\b', texto)
    return match.group(0) if match else None

@app.get("/")
def home():
    try:
        r.ping()
        status = "Conectado"
    except:
        status = "Erro de conexão"
    return {"status": "Proxy OTP Online", "redis": status, "dominio": DOMINIO_PERMITIDO}

# --- WEBHOOK SENDGRID ---
@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    try:
        events = await request.json()
        for event in events:
            email = event.get("email", "").lower()
            if not email.endswith(DOMINIO_PERMITIDO):
                continue
            
            otp = event.get("otp_code") or extrair_otp(event.get("body", ""))
            if email and otp:
                r.set(f"otp:{email}", otp, ex=120)
                print(f"OTP {otp} guardado para {email}")
        return {"status": "received"}
    except Exception as e:
        print(f"Erro Webhook: {e}")
        return {"status": "error"}

# --- ROBÔ DE LOGIN (PLAYWRIGHT) ---
@app.get("/login-automatizado")
async def login_automatizado(email: str):
    email = email.lower()
    if not email.endswith(DOMINIO_PERMITIDO):
        raise HTTPException(status_code=403, detail="Domínio não autorizado")

    async with async_playwright() as p:
        # Lança o navegador com argumentos para rodar no Linux/Railway
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            locale="es-EC" # Forçamos espanhol para os alunos da UIDE
        )
        page = await context.new_page()
        await stealth_async_inject(page)

        try:
            # 1. Acessa a plataforma
            await page.goto("https://auth.paciente360.com.br/login", wait_until="networkidle", timeout=60000)
            
            # 2. Preenche E-mail e clica no botão (Regex Poliglota)
            await page.get_by_placeholder(REGEX_CAMPO_EMAIL).fill(email)
            await page.get_by_role("button", name=REGEX_BOTAO_LOGIN).click()

            # 3. Espera o OTP no Redis (Polling)
            otp = None
            for _ in range(20):
                otp = r.get(f"otp:{email}")
                if otp: break
                await asyncio.sleep(1.5)
            
            if not otp:
                await browser.close()
                return {"status": "error", "message": "OTP timeout"}

            # 4. Preenche o OTP (Simulando digitação humana)
            # Tentamos pelo placeholder, se não houver, digitamos direto na tela focada
            try:
                campo_otp = page.get_by_placeholder(REGEX_CAMPO_OTP)
                await campo_otp.fill(otp)
            except:
                await page.keyboard.type(otp)
            
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("networkidle")

            # 5. Captura Cookies
            cookies = await context.cookies()
            await browser.close()

            # Retornamos uma página HTML que "injeta" os cookies no navegador do aluno
            return gerar_html_redirecionamento(cookies)

        except Exception as e:
            await browser.close()
            return {"status": "error", "message": str(e)}

def gerar_html_redirecionamento(cookies):
    # Converte os cookies para um formato que o Javascript entenda (document.cookie)
    js_cookies = ""
    for c in cookies:
        js_cookies += f"document.cookie = '{c['name']}={c['value']}; domain={c['domain']}; path=/; Secure; SameSite=Lax';\n"
    
    html_content = f"""
    <html>
        <head><title>Acessando Laboratório...</title></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
            <h2>Autenticação concluída!</h2>
            <p>Estamos configurando seu acesso à Paciente360. Aguarde...</p>
            <script>
                {js_cookies}
                setTimeout(() => {{
                    window.location.href = "https://app.paciente360.com.br/dashboard";
                }}, 1000);
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)