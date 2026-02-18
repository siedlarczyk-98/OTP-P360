from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import redis
import os
import re
import json
import asyncio
from playwright.async_api import async_playwright

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

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    try:
        events = await request.json()
        for event in events:
            email = event.get("email", "").lower()
            if not email.endswith(DOMINIO_PERMITIDO): continue
            
            otp = event.get("otp_code") or extrair_otp(event.get("body", ""))
            if email and otp:
                r.set(f"otp:{email}", otp, ex=120)
                print(f"DEBUG: OTP {otp} capturado para {email}")
        return {"status": "received"}
    except Exception as e:
        print(f"ERRO WEBHOOK: {e}")
        return {"status": "error"}

@app.get("/login-automatizado")
async def login_automatizado(email: str):
    email = email.lower()
    if not email.endswith(DOMINIO_PERMITIDO):
        raise HTTPException(status_code=403, detail="Domínio não autorizado")

    # MUDANÇA AQUI: Detecta o caminho do Chromium no Railway
    # O Railway geralmente instala em /usr/bin/chromium ou /usr/bin/google-chrome
    chrome_executable = os.getenv("CHROME_PATH", "/usr/bin/chromium")

    async with async_playwright() as p:
        try:
            # Lançamento com caminho explícito para evitar erro "Executable doesn't exist"
            browser = await p.chromium.launch(
                headless=True, 
                executable_path=chrome_executable,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
        except Exception as launch_error:
            # Fallback caso o caminho acima falhe (tenta o padrão do sistema)
            print(f"Aviso: Falha ao carregar chromium em {chrome_executable}. Tentando automático...")
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            locale="es-EC"
        )
        page = await context.new_page()

        try:
            print(f"DEBUG: Iniciando login para {email}")
            await page.goto("https://auth.paciente360.com.br/login", wait_until="networkidle", timeout=60000)
            
            # Passo 1: Email
            await page.get_by_placeholder(REGEX_CAMPO_EMAIL).fill(email)
            await page.get_by_role("button", name=REGEX_BOTAO_LOGIN).click()
            print("DEBUG: E-mail enviado, aguardando OTP no Redis...")

            # Passo 2: Espera OTP (Polling)
            otp = None
            for _ in range(25): 
                otp = r.get(f"otp:{email}")
                if otp: break
                await asyncio.sleep(1.5)
            
            if not otp:
                print(f"TIMEOUT: OTP não encontrado para {email}")
                await browser.close()
                return {"status": "error", "message": "OTP não recebido. Tente novamente."}

            # Passo 3: Preencher OTP
            print(f"DEBUG: OTP {otp} encontrado. Inserindo...")
            try:
                await page.get_by_placeholder(REGEX_CAMPO_OTP).fill(otp)
            except:
                await page.keyboard.type(otp, delay=100)
            
            await page.keyboard.press("Enter")
            
            # Passo 4: Captura de Sessão
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            cookies = await context.cookies()
            await browser.close()
            print(f"SUCESSO: Cookies capturados para {email}")

            return gerar_html_redirecionamento(cookies)

        except Exception as e:
            print(f"ERRO NO ROBÔ: {str(e)}")
            await browser.close()
            return {"status": "error", "message": f"Falha na automação: {str(e)}"}

def gerar_html_redirecionamento(cookies):
    js_cookies = ""
    for c in cookies:
        js_cookies += f"document.cookie = '{c['name']}={c['value']}; domain=.paciente360.com.br; path=/; Secure; SameSite=None';\n"
    
    return HTMLResponse(content=f"""
    <html>
        <head><meta charset="UTF-8"><title>Acessando Laboratório...</title></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background: #f4f4f9;">
            <div style="max-width: 400px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: #2d3748;">¡Autenticación Exitosa!</h2>
                <p style="color: #4a5568;">Configurando su acceso a la plataforma...</p>
                <div style="margin: 20px 0;"><img src="https://i.gifer.com/ZZ5H.gif" width="50"></div>
            </div>
            <script>
                {js_cookies}
                setTimeout(() => {{
                    window.location.href = "https://app.paciente360.com.br/dashboard";
                }}, 1500);
            </script>
        </body>
    </html>
    """)