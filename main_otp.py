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
async def rodar_solicitacao_otp(email: str):
    async with async_playwright() as p:
        browser = None
        try:
            print(f"🤖 [ROBÔ] Iniciando para: {email}")
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(user_agent=UA)
            page = await context.new_page()
            r.delete(f"otp:{email}")
            
            await page.goto("https://auth.paciente360.com.br/login/email", wait_until="networkidle", timeout=60000)
            await page.fill('input[type="email"]', email)
            await page.click('button[type="submit"]')
            
            print(f"✅ [ROBÔ] Sucesso para {email}")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"❌ [ROBÔ ERRO] {e}")
        finally:
            if browser: await browser.close()

# --- ROTAS DE AUTENTICAÇÃO ---

@app.get("/", response_class=HTMLResponse)
async def login_page(user_id: str = Cookie(None)):
    if user_id: # Se já estiver logado, vai direto pro dashboard
        return RedirectResponse(url="/dashboard")
    
    return """
    <html>
        <head><title>Login | Hub OTP</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f0f2f5; margin: 0; }
            .card { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); width: 320px; text-align: center; }
            input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; background: #1877f2; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 16px; }
            #msg { color:red; display:none; font-size: 14px; margin-top: 10px; }
        </style></head>
        <body>
            <div class="card">
                <h2>Portal Faculdades</h2>
                <input type="email" id="user" placeholder="E-mail">
                <input type="password" id="pass" placeholder="Senha">
                <button onclick="entrar()">Entrar</button>
                <p id="msg">Credenciais inválidas.</p>
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
            # Salvamos o ID do usuário no Cookie para saber quem está logado
            response.set_cookie(key="user_id", value=res.user.id, httponly=True, max_age=3600 * 12)
            return {"status": "ok"}
    except: pass
    raise HTTPException(status_code=401)

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie("user_id")
    return RedirectResponse(url="/")

# --- DASHBOARD MULTITENANT ---

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(user_id: str = Cookie(None)):
    if not user_id:
        return RedirectResponse(url="/")

    # FILTRO MULTITENANT: Busca apenas contas onde o owner_id é o ID do usuário logado
    contas = supabase.table("contas_paciente").select("*").eq("owner_id", user_id).execute()
    
    cards = ""
    for c in contas.data:
        cards += f"""
        <div class="card-conta">
            <div>
                <strong>{c['nome_amigavel']}</strong><br>
                <span>{c['email_alvo']}</span>
            </div>
            <button onclick="pedir('{c['email_alvo']}')">Solicitar OTP</button>
        </div>
        """

    if not contas.data:
        cards = "<p style='text-align:center; color:#666;'>Nenhuma conta vinculada a esta faculdade.</p>"

    return f"""
    <html>
        <head><title>Meus Acessos | OTP</title>
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
            .card-conta {{ background: white; padding: 20px; border-radius: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            button {{ background: #42b72a; color: white; border: none; padding: 10px 15px; border-radius: 6px; cursor: pointer; font-weight: bold; }}
            .terminal {{ background: #1c1e21; color: #42b72a; padding: 20px; border-radius: 10px; margin-top: 20px; text-align: center; min-height: 100px; }}
            #otp {{ font-size: 48px; color: white; display: block; margin-top: 10px; letter-spacing: 5px; }}
            .logout {{ color: #d93025; text-decoration: none; font-size: 14px; }}
        </style></head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🔐 Suas Contas</h2>
                    <a href="/logout" class="logout">Sair</a>
                </div>
                {cards}
                <div class="terminal">
                    <div id="status">Selecione uma conta acima</div>
                    <div id="otp">------</div>
                </div>
            </div>
            <script>
                let timer;
                async function pedir(email) {{
                    document.getElementById('status').innerText = "🤖 Acionando robô para " + email;
                    document.getElementById('otp').innerText = "......";
                    
                    const res = await fetch('/disparar-robo?email=' + email);
                    if (!res.ok) {{
                        alert("Erro ao disparar robô ou sem permissão.");
                        return;
                    }}
                    
                    if(timer) clearInterval(timer);
                    timer = setInterval(async () => {{
                        const r = await fetch('/get-raw-otp?email=' + email);
                        const d = await r.json();
                        if(d.otp) {{
                            document.getElementById('otp').innerText = d.otp;
                            document.getElementById('status').innerText = "✅ CÓDIGO CAPTURADO!";
                            clearInterval(timer);
                        }}
                    }}, 2000);
                }}
            </script>
        </body></html>
    """

@app.get("/disparar-robo")
async def disparar(email: str, background_tasks: BackgroundTasks, user_id: str = Cookie(None)):
    if not user_id: raise HTTPException(status_code=401)
    
    # SEGURANÇA: Verifica se a conta realmente pertence a quem está pedindo
    check = supabase.table("contas_paciente").select("id").eq("email_alvo", email).eq("owner_id", user_id).execute()
    if not check.data:
        raise HTTPException(status_code=403, detail="Acesso negado a esta conta.")

    background_tasks.add_task(rodar_solicitacao_otp, email)
    return {"status": "started"}

@app.get("/get-raw-otp")
async def get_otp(email: str, user_id: str = Cookie(None)):
    if not user_id: raise HTTPException(status_code=401)
    
    # SEGURANÇA: Só entrega o OTP se for o dono da conta
    check = supabase.table("contas_paciente").select("id").eq("email_alvo", email).eq("owner_id", user_id).execute()
    if check.data:
        return {"otp": r.get(f"otp:{email}")}
    return {"otp": None}

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    form = await request.form()
    email_html = form.get("html", "")
    email_to = form.get("to", "").lower()
    email_match = re.search(r'[\w\.-]+@[\w\.-]+', email_to)
    if email_match:
        target = email_match.group(0)
        otp_match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = otp_match.group(1) if otp_match else None
        if otp:
            r.set(f"otp:{target}", otp, ex=180)
    return {"status": "ok"}
