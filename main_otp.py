from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import redis
import os
import re
import asyncio
from playwright.async_api import async_playwright

app = FastAPI()

# --- CONFIGURAÇÃO REDIS ---
REDIS_URL = os.getenv("REDIS_URL")
r = redis.from_url(REDIS_URL, decode_responses=True)

# --- CONFIGURAÇÕES DE NEGÓCIO ---
DOMINIO_PERMITIDO = "@uide.edu.ec"

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
            
            # Busca OTP no corpo do email ou campo específico
            body = event.get("body", "")
            match = re.search(r'\b\d{6}\b', body)
            otp = event.get("otp_code") or (match.group(0) if match else None)
            
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

    async with async_playwright() as p:
        try:
            # Lançamento padrão para Docker Playwright
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                locale="es-EC"
            )
            page = await context.new_page()

            print(f"DEBUG: Acessando site para {email}")
            await page.goto("https://auth.paciente360.com.br/login", wait_until="networkidle", timeout=60000)

            # --- PASSO 1: ENCONTRAR E PREENCHER EMAIL ---
            print("DEBUG: Localizando campo de email...")
            # Espera por qualquer input para garantir que o formulário carregou
            await page.wait_for_selector("input", timeout=15000)
            
            # Tenta preencher por múltiplos seletores (mais robusto)
            await page.locator('input[type="email"], input[name*="email" i], input[placeholder*="email" i]').first.fill(email)
            
            # Clica no botão de enviar (Busca por texto flexível)
            await page.locator('button:has-text("Receber"), button:has-text("Recibir"), button:has-text("Get"), button:has-text("Acessar")').first.click()
            print("DEBUG: Email enviado. Aguardando OTP no Redis...")

            # --- PASSO 2: ESPERA OTP (POLLING) ---
            otp = None
            for _ in range(30): # 45 segundos de espera total
                otp = r.get(f"otp:{email}")
                if otp: break
                await asyncio.sleep(1.5)
            
            if not otp:
                print(f"TIMEOUT: OTP não encontrado para {email}")
                await browser.close()
                return {"status": "error", "message": "OTP não recebido a tempo."}

            # --- PASSO 3: PREENCHER OTP ---
            print(f"DEBUG: Inserindo OTP {otp}...")
            # Espera o campo de código aparecer
            await page.wait_for_selector("input", timeout=10000)
            
            # Tenta preencher o código
            otp_field = page.locator('input[placeholder*="código" i], input[placeholder*="code" i], input[name*="otp" i]').first
            if await otp_field.is_visible():
                await otp_field.fill(otp)
            else:
                await page.keyboard.type(otp, delay=100)
            
            await page.keyboard.press("Enter")
            
            # --- PASSO 4: FINALIZAÇÃO ---
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3) # Tempo para os cookies assentarem
            
            cookies = await context.cookies()
            await browser.close()
            print(f"SUCESSO: Sessão capturada para {email}")

            return gerar_html_redirecionamento(cookies)

        except Exception as e:
            print(f"ERRO NO ROBÔ: {str(e)}")
            # Se quiser debugar, o log do Railway vai mostrar o erro exato aqui
            if 'browser' in locals(): await browser.close()
            return {"status": "error", "message": f"Falha na automação: {str(e)}"}

def gerar_html_redirecionamento(cookies):
    js_cookies = ""
    for c in cookies:
        js_cookies += f"document.cookie = '{c['name']}={c['value']}; domain=.paciente360.com.br; path=/; Secure; SameSite=None';\n"
    
    return HTMLResponse(content=f"""
    <html>
        <head><meta charset="UTF-8"><title>Redirecionando...</title></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background: #f4f4f9;">
            <div style="max-width: 400px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: #2d3748;">¡Autenticación Exitosa!</h2>
                <p style="color: #4a5568;">Sincronizando sesión...</p>
                <div style="margin: 20px 0;"><img src="https://i.gifer.com/ZZ5H.gif" width="50"></div>
            </div>
            <script>
                {js_cookies}
                setTimeout(() => {{
                    window.location.href = "https://app.paciente360.com.br/dashboard";
                }}, 2000);
            </script>
        </body>
    </html>
    """)