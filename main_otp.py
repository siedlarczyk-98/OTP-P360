from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import redis
import os
import re
import asyncio
from playwright.async_api import async_playwright

app = FastAPI()

# --- CONFIGURAÇÃO REDIS ---
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
        form = await request.form()
        email_html = form.get("html", "")
        email_to_raw = form.get("to", "").lower()
        
        email_match = re.search(r'[\w\.-]+@[\w\.-]+', email_to_raw)
        if not email_match:
            return {"status": "error", "message": "Destinatário inválido"}
            
        email_limpo = email_match.group(0)
        print(f"📩 WEBHOOK: Recebido e-mail para {email_limpo}")

        # Busca o código de 6 dígitos
        match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = match.group(1) if match else None

        if not otp:
            match_fallback = re.search(r'\b\d{6}\b', email_html)
            otp = match_fallback.group(0) if match_fallback else None

        if otp:
            r.set(f"otp:{email_limpo}", str(otp), ex=300)
            print(f"✅ WEBHOOK: OTP {otp} salvo para {email_limpo}")
            return {"status": "success"}
        
        return {"status": "no_otp_found"}
    except Exception as e:
        print(f"🔥 ERRO WEBHOOK: {e}")
        return {"status": "error"}

@app.get("/login-automatizado")
async def login_automatizado(email: str):
    email = email.lower().strip()
    if not email.endswith(DOMINIO_PERMITIDO):
        raise HTTPException(status_code=403, detail="Domínio não autorizado")

    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720},
                locale="pt-BR"
            )
            page = await context.new_page()

           # --- PASSO 1: SOLICITAR E-MAIL ---
            print(f"🤖 BOT: Acessando Paciente 360 para {email}")
            # Tentamos carregar a página e esperar até que não haja mais atividade de rede
            await page.goto("https://auth.paciente360.com.br/login/email", wait_until="domcontentloaded", timeout=60000)
            
            # Pequena pausa para garantir que os scripts de carregamento rodaram
            await asyncio.sleep(5)

            # Seletor ultra-abrangente: busca qualquer input que pareça um campo de texto ou email
            try:
                print("🔍 BOT: Procurando campo de entrada...")
                campo_email = page.locator('input[type="email"], input[name*="email" i], input[placeholder*="email" i], input').first
                await campo_email.wait_for(state="visible", timeout=15000)
                await campo_email.fill(email)
                print("✅ BOT: Campo de e-mail preenchido.")
            except Exception as e:
                # Se falhar, tira um "print" do HTML para o log (ajuda muito a debugar)
                print(f"❌ BOT: Não achei o campo. O que estou vendo: {await page.content()[:500]}...")
                raise Exception("Campo de e-mail não encontrado na página.")
            
            # Clica no botão (geralmente o único botão de destaque na página de login)
            btn_enviar = page.locator('button[type="submit"], button:has-text("Receber"), button:has-text("Continuar"), button:has-text("Enviar")').first
            await btn_enviar.click()
            
            print("⏳ BOT: E-mail solicitado. Aguardando OTP no Redis...")

            # --- PASSO 2: AGUARDAR OTP (POLLING) ---
            otp = None
            for i in range(60): # 60 iterações * 1.5s = 90 segundos de espera
                otp = r.get(f"otp:{email}")
                if otp:
                    print(f"🔑 BOT: OTP {otp} recuperado do Redis no ciclo {i}!")
                    break
                await asyncio.sleep(1.5)
            
            if not otp:
                print(f"⏰ TIMEOUT: OTP não chegou no Redis para {email}")
                await browser.close()
                return {"status": "error", "message": "O código demorou mais de 90s para chegar."}

            # --- PASSO 3: INSERIR OTP E LOGAR ---
            print("🤖 BOT: Localizando campo de OTP na tela...")
            # Esperamos o campo de OTP aparecer após o clique anterior
            await page.wait_for_selector("input", timeout=15000)
            
            # O site costuma focar no primeiro input de código que aparece
            otp_field = page.locator('input[placeholder*="código" i], input[name*="otp" i], input').first
            await otp_field.fill(str(otp))
            await page.keyboard.press("Enter")
            
            # --- PASSO 4: FINALIZAR E COLETAR COOKIES ---
            print("🚀 BOT: Login submetido. Aguardando Dashboard...")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(5) # Delay de segurança para os cookies
            
            cookies = await context.cookies()
            await browser.close()
            print(f"🎉 SUCESSO: Login concluído para {email}")

            return gerar_html_redirecionamento(cookies)

        except Exception as e:
            print(f"❌ ERRO NO BOT: {str(e)}")
            if browser: await browser.close()
            return {"status": "error", "message": str(e)}

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
