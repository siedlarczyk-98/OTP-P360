import os
import re
import asyncio
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from supabase import create_client, Client
import redis
from playwright.async_api import async_playwright

app = FastAPI()

# --- CONFIGURAÇÕES ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

MY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

# --- LOGICA DO ROBÔ (EXECUTA EM BACKGROUND) ---
async def tarefa_solicitar_otp(email: str):
    async with async_playwright() as p:
        browser = None
        try:
            print(f"🤖 ROBÔ: Iniciando solicitação para {email}")
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(user_agent=MY_USER_AGENT)
            page = await context.new_page()
            
            # Limpa cache antigo do Redis antes de pedir o novo
            r.delete(f"otp:{email}")
            
            await page.goto("https://auth.paciente360.com.br/login/email", wait_until="networkidle", timeout=60000)
            
            campo_email = page.locator('input[type="email"], input[name*="email" i]').first
            await campo_email.fill(email)
            
            btn_enviar = page.locator('button[type="submit"], button:has-text("Receber"), button:has-text("Continuar")').first
            await btn_enviar.click()
            
            print(f"✅ ROBÔ: Solicitação enviada com sucesso para {email}")
            await asyncio.sleep(5) # Aguarda confirmação visual do site
        except Exception as e:
            print(f"❌ ROBÔ ERRO: {str(e)}")
        finally:
            if browser: await browser.close()

# --- ROTAS DA API ---

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    form = await request.form()
    email_html = form.get("html", "")
    email_to = form.get("to", "").lower()
    
    email_match = re.search(r'[\w\.-]+@[\w\.-]+', email_to)
    if email_match:
        email_limpo = email_match.group(0)
        # Regex para o formato específico do e-mail da Paciente 360
        match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = match.group(1) if match else re.search(r'\b\d{6}\b', email_html).group(0) if re.search(r'\b\d{6}\b', email_html) else None
        
        if otp:
            r.set(f"otp:{email_limpo}", str(otp), ex=180)
            print(f"📩 WEBHOOK: OTP {otp} capturado para {email_limpo}")
    return {"status": "ok"}

@app.get("/disparar-robo")
async def disparar_robo(email: str, background_tasks: BackgroundTasks):
    # Adiciona a tarefa do robô para rodar sem travar a resposta da API
    background_tasks.add_task(tarefa_solicitar_otp, email)
    return {"status": "🤖 Robô em movimento!"}

@app.get("/get-raw-otp")
async def get_raw_otp(email: str):
    otp = r.get(f"otp:{email}")
    return {"otp": otp}

# --- DASHBOARD UI ---

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    contas = supabase.table("contas_paciente").select("*").execute()
    
    lista_html = ""
    for c in contas.data:
        lista_html += f"""
        <div class="card">
            <div>
                <div class="nome">{c['nome_amigavel'] or 'Conta'}</div>
                <div class="email">{c['email_alvo']}</div>
            </div>
            <button onclick="solicitar('{c['email_alvo']}')">Solicitar OTP</button>
        </div>
        """

    return f"""
    <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Hub OTP Admin</title>
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; display: flex; justify-content: center; }}
                .container {{ background: white; width: 100%; max-width: 500px; padding: 25px; border-radius: 15px; box-shadow: 0 8px 30px rgba(0,0,0,0.1); }}
                h2 {{ color: #1c1e21; text-align: center; margin-bottom: 30px; }}
                .card {{ display: flex; justify-content: space-between; align-items: center; padding: 15px; border-radius: 10px; border: 1px solid #e4e6eb; margin-bottom: 10px; transition: 0.3s; }}
                .card:hover {{ background: #f9f9f9; }}
                .nome {{ font-weight: bold; color: #1c1e21; }}
                .email {{ font-size: 13px; color: #65676b; }}
                button {{ background: #1877f2; color: white; border: none; padding: 10px 15px; border-radius: 8px; cursor: pointer; font-weight: 600; }}
                button:active {{ transform: scale(0.98); }}
                .monitor {{ margin-top: 30px; padding: 20px; background: #1c1e21; color: #42b72a; border-radius: 12px; text-align: center; }}
                #otp-box {{ font-size: 40px; font-weight: bold; margin: 10px 0; letter-spacing: 5px; color: white; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>🔑 Central de Acessos</h2>
                {lista_html}
                <div class="monitor">
                    <div id="status">Selecione uma conta</div>
                    <div id="otp-box">------</div>
                </div>
            </div>
            <script>
                let pollInterval;
                async function solicitar(email) {{
                    document.getElementById('status').innerText = "🤖 Robô trabalhando...";
                    document.getElementById('otp-box').innerText = "......";
                    
                    fetch('/disparar-robo?email=' + email);
                    
                    if(pollInterval) clearInterval(pollInterval);
                    pollInterval = setInterval(async () => {{
                        const res = await fetch('/get-raw-otp?email=' + email);
                        const data = await res.json();
                        if(data.otp) {{
                            document.getElementById('otp-box').innerText = data.otp;
                            document.getElementById('status').innerText = "✅ CÓDIGO RECEBIDO!";
                            clearInterval(pollInterval);
                        }}
                    }}, 2000);
                }}
            </script>
        </body>
    </html>
    """
