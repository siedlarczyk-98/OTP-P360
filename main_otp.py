import os
import re
import asyncio
import redis
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Cookie, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from supabase import create_client, Client
from playwright.async_api import async_playwright

app = FastAPI()

# --- CONFIGURAÇÕES ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class LoginData(BaseModel):
    email: str
    password: str

# --- ROBÔ EM BACKGROUND ---
async def rodar_solicitacao_otp(email_alvo: str):
    async with async_playwright() as p:
        browser = None
        try:
            print(f"🤖 [ROBÔ] Solicitando para: {email_alvo}")
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(user_agent=UA)
            page = await context.new_page()
            
            # Limpa cache do Redis antes de pedir novo código
            r.delete(f"otp:{email_alvo}")
            
            await page.goto("https://auth.paciente360.com.br/login/email", wait_until="networkidle", timeout=60000)
            await page.fill('input[type="email"]', email_alvo)
            await page.click('button[type="submit"]')
            
            print(f"✅ [ROBÔ] Solicitação enviada para {email_alvo}")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"❌ [ROBÔ ERRO] {e}")
        finally:
            if browser: await browser.close()

# --- ROTAS DE AUTENTICAÇÃO ---

@app.get("/", response_class=HTMLResponse)
async def login_page(user_id: str = Cookie(None)):
    if user_id: return RedirectResponse(url="/dashboard")
    return """
    <html>
        <head><title>Login | Hub OTP</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f0f2f5; margin: 0; }
            .card { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); width: 320px; text-align: center; }
            input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; background: #1877f2; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
            #msg { color:red; display:none; font-size: 14px; margin-top: 10px; }
        </style></head>
        <body>
            <div class="card">
                <h2>Portal Faculdades</h2>
                <input type="email" id="user" placeholder="E-mail de acesso">
                <input type="password" id="pass" placeholder="Senha">
                <button onclick="entrar()">Entrar</button>
                <p id="msg">Acesso negado. Verifique os dados.</p>
            </div>
            <script>
                async function entrar() {
                    const email = document.getElementById('user').value;
                    const password = document.getElementById('pass').value;
                    const res = await fetch('/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({email, password})
                    });
                    if(res.ok) window.location.href = '/dashboard';
                    else document.getElementById('msg').style.display = 'block';
                }
            </script>
        </body></html>
    """

@app.post("/auth/login")
async def auth_login(data: LoginData, response: Response):
    try:
        res = supabase.auth.sign_in_with_password({"email": data.email, "password": data.password})
        if res.user:
            response.set_cookie(key="user_id", value=res.user.id, httponly=True, max_age=3600 * 12)
            return {"status": "ok"}
    except: pass
    raise HTTPException(status_code=401)

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie("user_id")
    return RedirectResponse(url="/")

# --- DASHBOARD ---

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(user_id: str = Cookie(None)):
    if not user_id: return RedirectResponse(url="/")

    # Filtra contas pertencentes ao usuário logado
    contas = supabase.table("contas_paciente").select("*").eq("owner_id", user_id).execute()
    
    cards_html = ""
    for c in contas.data:
        nome = c.get('nome_amigavel') or 'Unidade Sem Nome'
        email_conta = c.get('email') or 'E-mail não cadastrado'
        
        cards_html += f'''
        <div class="card-conta">
            <div>
                <strong>{nome}</strong><br>
                <span style="color: #65676b; font-size: 13px;">{email_conta}</span>
            </div>
            <button onclick="pedir('{email_conta}')">Solicitar OTP</button>
        </div>
        '''

    if not contas.data:
        cards_html = "<p style='text-align:center; color:#666;'>Nenhuma conta cadastrada para esta faculdade.</p>"

    return f"""
    <html>
        <head><title>Dashboard | Central OTP</title>
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
            .card-conta {{ background: white; padding: 20px; border-radius: 12px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
            button {{ background: #42b72a; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; }}
            .terminal {{ background: #1c1e21; color: #42b72a; padding: 25px; border-radius: 12px; margin-top: 25px; text-align: center; }}
            #otp {{ font-size: 52px; color: white; display: block; margin-top: 10px; letter-spacing: 8px; font-weight: bold; }}
            .logout {{ color: #d93025; text-decoration: none; font-size: 14px; font-weight: bold; }}
        </style></head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🔑 Gerenciador de Acessos</h2>
                    <a href="/logout" class="logout">Sair</a>
                </div>
                {cards_html}
                <div class="terminal">
                    <div id="status">Selecione uma conta acima</div>
                    <div id="otp">------</div>
                </div>
            </div>
            <script>
                let poll;
                async function pedir(email) {{
                    document.getElementById('status').innerText = "🤖 Robô em ação para " + email;
                    document.getElementById('otp').innerText = "......";
                    
                    const res = await fetch('/disparar-robo?email=' + email);
                    if (!res.ok) {{ alert("Erro na solicitação. Verifique se você é o dono desta conta."); return; }}
                    
                    if(poll) clearInterval(poll);
                    poll = setInterval(async () => {{
                        const r = await fetch('/get-raw-otp?email=' + email);
                        const d = await r.json();
                        if(d.otp) {{
                            document.getElementById('otp').innerText = d.otp;
                            document.getElementById('status').innerText = "✅ CÓDIGO CAPTURADO!";
                            clearInterval(poll);
                        }}
                    }}, 2000);
                }}
            </script>
        </body></html>
    """

# --- OPERAÇÕES ---

@app.get("/disparar-robo")
async def disparar(email: str, background_tasks: BackgroundTasks, user_id: str = Cookie(None)):
    if not user_id: raise HTTPException(status_code=401)
    
    # Valida se o email pertence ao usuário logado
    check = supabase.table("contas_paciente").select("id").eq("email", email).eq("owner_id", user_id).execute()
    if not check.data: raise HTTPException(status_code=403)

    background_tasks.add_task(rodar_solicitacao_otp, email)
    return {"status": "started"}

@app.get("/get-raw-otp")
async def get_otp(email: str, user_id: str = Cookie(None)):
    if not user_id: raise HTTPException(status_code=401)
    
    check = supabase.table("contas_paciente").select("id").eq("email", email).eq("owner_id", user_id).execute()
    if check.data:
        return {"otp": r.get(f"otp:{email}")}
    return {"otp": None}

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    form = await request.form()
    email_html = form.get("html", "")
    email_to = form.get("to", "").lower()
    match_to = re.search(r'[\w\.-]+@[\w\.-]+', email_to)
    
    if match_to:
        alvo = match_to.group(0)
        # Tenta pegar o código entre as tags de cor específicas ou o primeiro bloco de 6 dígitos
        otp_match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = otp_match.group(1) if otp_match else None
        
        if not otp:
            # Fallback para qualquer sequência de 6 dígitos no texto
            clean_text = re.sub('<[^<]+?>', '', email_html)
            fallback = re.search(r'\b\d{6}\b', clean_text)
            otp = fallback.group(0) if fallback else None

        if otp:
            r.set(f"otp:{alvo}", otp, ex=180)
            print(f"📩 Webhook: OTP {otp} salvo para {alvo}")
    return {"status": "ok"}
