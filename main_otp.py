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
        data = await request.json()
        # O SendGrid pode enviar um evento único ou uma lista
        events = data if isinstance(data, list) else [data]
        
        for event in events:
            # 1. Tenta pegar o email do campo principal ou de dentro do dynamic_template_data
            email = event.get("email") or event.get("to")
            template_data = event.get("dynamic_template_data", {})
            
            if not email and template_data:
                email = template_data.get("email")

            if not email:
                continue
                
            email = email.lower().strip()
            if not email.endswith(DOMINIO_PERMITIDO):
                continue

            # 2. CAPTURA O OTP (Ajustado para o seu JSON)
            # Primeiro tenta 'code_otp' dentro de 'dynamic_template_data'
            otp = template_data.get("code_otp")
            
            # Fallback: Se não achar, tenta o Regex no corpo como garantia
            if not otp:
                body = event.get("body", "")
                match = re.search(r'\b\d{6}\b', str(body))
                otp = match.group(0) if match else None

            if email and otp:
                # Salva no Redis com a chave minúscula
                r.set(f"otp:{email}", str(otp), ex=180)
                print(f"✅ SUCESSO: OTP {otp} capturado via dynamic_template_data para {email}")
            else:
                print(f"⚠️ AVISO: Evento recebido para {email}, mas 'code_otp' não encontrado.")

        return {"status": "received"}
    except Exception as e:
        print(f"ERRO CRÍTICO WEBHOOK: {e}")
        return {"status": "error"}

@app.get("/login-automatizado")
async def login_automatizado(email: str):
    email = email.lower()
    if not email.endswith(DOMINIO_PERMITIDO):
        raise HTTPException(status_code=403, detail="Domínio não autorizado")

    async with async_playwright() as p:
        try:
            # AJUSTE 1: Argumentos de camuflagem nativa para evitar detecção de bot
            browser = await p.chromium.launch(
                headless=True, 
                args=[
                    '--no-sandbox', 
                    '--disable-setuid-sandbox', 
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled' # Oculta o uso de automação
                ]
            )
            
            # AJUSTE 2: Contexto com User Agent moderno e Viewport padrão
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720},
                locale="es-EC"
            )
            page = await context.new_page()

            # AJUSTE 3: Uso da URL direta para o campo de e-mail
            print(f"DEBUG: Acessando URL direta de email para {email}")
            await page.goto("https://auth.paciente360.com.br/login/email", wait_until="networkidle", timeout=60000)

            # Pequena pausa para garantir renderização de scripts internos
            await asyncio.sleep(3)

            # --- PASSO 1: ENCONTRAR E PREENCHER EMAIL ---
            print("DEBUG: Localizando campo de email...")
            # Como estamos na URL direta, buscamos o primeiro input disponível
            await page.wait_for_selector("input", timeout=15000)
            
            # Seletor ultra-robusto: foca no tipo email ou no primeiro input de texto
            campo_email = page.locator('input[type="email"], input[name*="email" i], input').first
            await campo_email.fill(email)
            
            # Clica no botão (geralmente do tipo submit ou com textos específicos)
            btn_enviar = page.locator('button[type="submit"], button:has-text("Receber"), button:has-text("Continuar"), button:has-text("Recibir")').first
            await btn_enviar.click()
            
            print("DEBUG: Email submetido. Aguardando OTP no Redis...")

            # --- PASSO 2: ESPERA OTP (POLLING) ---
            otp = None
            for _ in range(35): # Aumentado para 52 segundos de tolerância
                otp = r.get(f"otp:{email}")
                if otp: break
                await asyncio.sleep(1.5)
            
            if not otp:
                print(f"TIMEOUT: OTP não encontrado para {email}")
                # Captura log do que o robô está vendo antes de fechar (ajuda no debug)
                # print(f"DEBUG HTML: {await page.content()[:500]}")
                await browser.close()
                return {"status": "error", "message": "OTP não recebido a tempo."}

            # --- PASSO 3: PREENCHER OTP ---
            print(f"DEBUG: Inserindo OTP {otp}...")
            await page.wait_for_selector("input", timeout=10000)
            
            # Busca campo de OTP
            otp_field = page.locator('input[placeholder*="código" i], input[placeholder*="code" i], input[name*="otp" i], input').first
            await otp_field.fill(otp)
            await page.keyboard.press("Enter")
            
            # --- PASSO 4: FINALIZAÇÃO ---
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(4) # Tempo extra para segurança dos cookies
            
            cookies = await context.cookies()
            await browser.close()
            print(f"SUCESSO: Sessão capturada para {email}")

            return gerar_html_redirecionamento(cookies)

        except Exception as e:
            print(f"ERRO NO ROBÔ: {str(e)}")
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