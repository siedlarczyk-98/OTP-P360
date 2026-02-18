from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import redis
import os
import re
import asyncio
import json
from playwright.async_api import async_playwright

app = FastAPI()

# --- CONFIGURAÇÃO REDIS ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

# --- CONFIGURAÇÕES DE NEGÓCIO ---
DOMINIO_PERMITIDO = "@otp-p360.com.br"
MY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

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
                args=[
                    '--no-sandbox', 
                    '--disable-setuid-sandbox', 
                    '--disable-dev-shm-usage', 
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            
            context = await browser.new_context(
                user_agent=MY_USER_AGENT,
                viewport={'width': 1366, 'height': 768},
                locale="pt-BR",
                timezone_id="America/Sao_Paulo"
            )
            
            page = await context.new_page()
            # Camuflagem extra contra detecção de bot
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # --- PASSO 1: SOLICITAR E-MAIL ---
            print(f"🤖 BOT: Acessando Paciente 360 para {email}")
            await page.goto("https://auth.paciente360.com.br/login/email", wait_until="networkidle", timeout=60000)
            
            await asyncio.sleep(4)

            try:
                print("🔍 BOT: Localizando campo de e-mail...")
                campo_email = page.locator('input[type="email"], input[name*="email" i], input').first
                await campo_email.fill(email)
                
                r.delete(f"otp:{email}") 
                print(f"🧹 BOT: Cache de OTP limpo para {email}")
                
            except Exception as e:
                print(f"❌ BOT: Erro no preenchimento: {str(e)}")
                raise Exception("Campo de e-mail não encontrado.")
            
            btn_enviar = page.locator('button[type="submit"], button:has-text("Receber"), button:has-text("Continuar")').first
            await btn_enviar.click()
            
            print("⏳ BOT: E-mail solicitado. Aguardando OTP fresco no Redis...")

            # --- PASSO 2: AGUARDAR OTP (POLLING) ---
            otp = None
            for i in range(60): 
                otp = r.get(f"otp:{email}")
                if otp:
                    print(f"🔑 BOT: OTP {otp} recuperado do Redis no ciclo {i}!")
                    break
                await asyncio.sleep(1.5)
            
            if not otp:
                print(f"⏰ TIMEOUT: OTP não chegou no Redis para {email}")
                await browser.close()
                return {"status": "error", "message": "O código demorou mais de 90s."}

            # --- PASSO 3: INSERIR OTP E LOGAR ---
            print("🤖 BOT: Inserindo OTP no formulário...")
            await page.wait_for_selector("input", timeout=15000)
            otp_field = page.locator('input').first
            await otp_field.fill(str(otp))
            await page.keyboard.press("Enter")
            
            # --- PASSO 4: CAPTURAR PERSISTÊNCIA COMPLETA ---
            print("🚀 BOT: Aguardando estabilização do Dashboard...")
            # Espera carregar a URL de destino ou estabilizar a rede
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(8) 
            
            # Captura cookies e o estado dos storages (localStorage e sessionStorage)
            storage_data = await page.evaluate("""() => {
                return {
                    local: JSON.stringify(localStorage),
                    session: JSON.stringify(sessionStorage)
                };
            }""")
            
            cookies = await context.cookies()
            await browser.close()
            print(f"🎉 SUCESSO: Sessão completa capturada para {email}")

            return gerar_html_redirecionamento(cookies, storage_data)

        except Exception as e:
            print(f"❌ ERRO NO BOT: {str(e)}")
            if browser: await browser.close()
            return {"status": "error", "message": str(e)}

def gerar_html_redirecionamento(cookies, storage):
    js_cookies = ""
    for c in cookies:
        js_cookies += f"document.cookie = '{c['name']}={c['value']}; domain=.paciente360.com.br; path=/; Max-Age=3600; Secure; SameSite=None';\n"
    
    # Escapa as strings do storage para o JS
    local_json = storage['local']
    session_json = storage['session']

    return HTMLResponse(content=f"""
    <html>
        <head><meta charset="UTF-8"><title>Sincronizando Sessão...</title></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background: #f4f4f9;">
            <div style="max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <h2 style="color: #2d3748;">Autenticação Concluída</h2>
                <p style="color: #4a5568;">Sincronizando chaves de segurança e redirecionando...</p>
                <div style="margin: 20px 0;"><img src="https://i.gifer.com/ZZ5H.gif" width="40"></div>
            </div>
            <script>
                try {{
                    // 1. Limpeza profunda de cookies antigos
                    const cookiesAntigos = document.cookie.split(";");
                    for (let i = 0; i < cookiesAntigos.length; i++) {{
                        const name = cookiesAntigos[i].split("=")[0].trim();
                        document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT; domain=.paciente360.com.br; path=/";
                    }}

                    // 2. Injeção de Storages (Crucial para SPAs modernos)
                    const localData = JSON.parse({json.dumps(local_json)});
                    const sessionData = JSON.parse({json.dumps(session_json)});
                    
                    const localObj = JSON.parse(localData);
                    const sessionObj = JSON.parse(sessionData);

                    for (let k in localObj) localStorage.setItem(k, localObj[k]);
                    for (let k in sessionObj) sessionStorage.setItem(k, sessionObj[k]);

                    // 3. Injeção de Cookies
                    {js_cookies}

                    console.log("Sessão sincronizada.");

                    setTimeout(() => {{
                        window.location.href = "https://app.paciente360.com.br/dashboard";
                    }}, 2000);
                }} catch (e) {{
                    console.error("Erro na sincronização:", e);
                    window.location.href = "https://app.paciente360.com.br/dashboard";
                }}
            </script>
        </body>
    </html>
    """)
