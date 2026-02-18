from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import redis
import os
import re
import asyncio
from playwright.async_api import async_playwright

app = FastAPI()

# --- CONFIGURAÇÃO REDIS ---
# No Railway, a variável REDIS_URL é injetada automaticamente
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

# --- CONFIGURAÇÕES DE NEGÓCIO ---
DOMINIO_PERMITIDO = "@otp-p360.com.br"

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
        # Importante: O FastAPI exige python-multipart instalado para rodar o .form()
        form = await request.form()
        
        email_html = form.get("html", "")
        email_to_raw = form.get("to", "").lower()
        
        # Extrai apenas o e-mail limpo (remove nomes ou caracteres < >)
        email_match = re.search(r'[\w\.-]+@[\w\.-]+', email_to_raw)
        if not email_match:
            print(f"⚠️ AVISO: E-mail de destino inválido: {email_to_raw}")
            return {"status": "error", "message": "Destinatário inválido"}
            
        email_limpo = email_match.group(0)
        print(f"📩 DEBUG: Processando e-mail para {email_limpo}")

        # Busca o código de 6 dígitos no HTML
        # Tentativa 1: Regex específico do template
        match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = match.group(1) if match else None

        # Tentativa 2: Fallback para qualquer sequência de 6 dígitos
        if not otp:
            match_fallback = re.search(r'\b\d{6}\b', email_html)
            otp = match_fallback.group(0) if match_fallback else None

        if otp:
            # Salva no Redis com prefixo para organização
            r.set(f"otp:{email_limpo}", str(otp), ex=300)
            print(f"✅ SUCESSO: OTP {otp} capturado para {email_limpo}")
            return {"status": "success"}
        
        print(f"❌ Erro: OTP não encontrado no HTML para {email_limpo}")
        return {"status": "no_otp_found"}

    except Exception as e:
        print(f"🔥 ERRO CRÍTICO NO WEBHOOK: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/login-automatizado")
async def login_automatizado(email: str):
    email = email.lower().strip()
    
    # Validação de segurança do domínio
    if not email.endswith(DOMINIO_PERMITIDO):
        raise HTTPException(status_code=403, detail="Domínio não autorizado")

    async with async_playwright() as p:
        browser = None
        try:
            # Lançamento do browser com argumentos anti-bot
            browser = await p.chromium.launch(
                headless=True, 
                args=[
                    '--no-sandbox', 
                    '--disable-setuid-sandbox', 
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720},
                locale="es-EC"
            )
            page = await context.new_page()

            print(f"🤖 BOT: Acessando tela de login para {email}")
            await page.goto("https://auth.paciente360.com.br/login/email", wait_until="networkidle", timeout=60000)

            await asyncio.sleep(3)

            # --- PASSO 1: PREENCHER EMAIL ---
            await page.wait_for_selector("input", timeout=15000)
            campo_email = page.locator('input[type="email"], input[name*="email" i], input').first
            await campo_email.fill(email)
            
            btn_enviar = page.locator('button[type="submit"], button:has-text("Receber"), button:has-text("Continuar"), button:has-text("Recibir")').first
            await btn_enviar.click()
            
            print("⏳ BOT: Email enviado. Aguardando OTP no Redis...")

            # --- PASSO 2: POLLING DO REDIS ---
            otp = None
            for _ in range(40): # ~60 segundos de espera total
                otp = r.get(f"otp:{email}")
                if otp: break
                await asyncio.sleep(1.5)
            
            if not otp:
                print(f"⏰ TIMEOUT: OTP não chegou para {email}")
                await browser.close()
                return {"status": "error", "message": "OTP não recebido a tempo."}

            # --- PASSO 3: INSERIR OTP ---
            print(f"🔑 BOT: Inserindo OTP {otp}...")
            await page.wait_for_selector("input", timeout=10000)
            
            # Localiza o campo de código e preenche
            otp_field = page.locator('input[placeholder*="código" i], input[placeholder*="code" i], input[name*="otp" i], input').first
            await otp_field.fill(otp)
            await page.keyboard.press("Enter")
            
            # --- PASSO 4: CAPTURAR SESSÃO ---
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(5) # Tempo para os cookies de sessão estabilizarem
            
            cookies = await context.cookies()
            await browser.close()
            print(f"🎉 SUCESSO: Sessão capturada para {email}")

            return gerar_html_redirecionamento(cookies)

        except Exception as e:
            print(f"❌ ERRO NO ROBÔ: {str(e)}")
            if browser: await browser.close()
            return {"status": "error", "message": f"Falha na automação: {str(e)}"}

def gerar_html_redirecionamento(cookies):
    # Converte os cookies para o formato document.cookie do navegador
    js_cookies = ""
    for c in cookies:
        # Importante: domain=.paciente360.com.br permite que o cookie funcione no app. e auth.
        js_cookies += f"document.cookie = '{c['name']}={c['value']}; domain=.paciente360.com.br; path=/; Secure; SameSite=None';\n"
    
    return HTMLResponse(content=f"""
    <html>
        <head><meta charset="UTF-8"><title>Redirecionando...</title></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background: #f4f4f9;">
            <div style="max-width: 400px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: #2d3748;">¡Autenticación Exitosa!</h2>
                <p style="color: #4a5568;">Sincronizando sesión segura...</p>
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