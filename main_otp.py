import os
import re
import redis
import time
import asyncio
import datetime
from fastapi import FastAPI, Request, HTTPException, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI()

# --- CONFIGURAÇÕES ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class LoginData(BaseModel):
    email: str
    password: str

# --- ASSETS DA MARCA ---
LOGO_URL = "https://biabapecceelzvwwunvm.supabase.co/storage/v1/object/public/icons/logo.png"
FAVICON_URL = "https://biabapecceelzvwwunvm.supabase.co/storage/v1/object/public/icons/favicon.ico"

# --- DICIONÁRIO DE TRADUÇÃO ---
TRADUCOES = {
    "pt": {
        "titulo": "Central de Rastreamento OTP",
        "login_titulo": "Acesso Laboratório",
        "login_erro": "Acesso negado. Verifique os dados.",
        "passo_a_passo": "📖 Passo a Passo:",
        "instrucoes": [
            "Vá ao site da <a href='https://auth.paciente360.com.br/login/email' target='_blank'><b>Paciente 360</b></a> e solicite o código.",
            "Volte aqui e clique em <b>'Rastrear OTP'</b> na conta desejada.",
            "Copie o código abaixo e cole no portal oficial."
        ],
        "btn_rastrear": "Rastrear OTP",
        "btn_bloqueado": "Bloqueado",
        "status_inicial": "Aguardando rastreamento...",
        "status_lendo": "🔎 Rastreando e-mail para: ",
        "status_sucesso": "CÓDIGO LOCALIZADO! COPIE ABAIXO:",
        "msg_vazio": "Nenhuma conta cadastrada para esta faculdade.",
        "logout": "Sair",
        "btn_ok": "Entrar",
        "placeholder_email": "E-mail",
        "placeholder_senha": "Senha",
        "status_disponivel": "🟢 Disponível",
        "status_em_uso": "🔴 Em uso",
        "tooltip_bloqueio": "Esta licença está em uso por outro usuário - o uso será liberado às "
    },
    "en": {
        "titulo": "OTP Tracking Hub",
        "login_titulo": "Lab Access",
        "login_erro": "Access denied. Please check your credentials.",
        "passo_a_passo": "📖 Step by Step:",
        "instrucoes": [
            "Go to the <a href='https://auth.paciente360.com.br/login/email' target='_blank'><b>Paciente 360</b></a> website and request the code.",
            "Return here and click <b>'Track OTP'</b> on the desired account.",
            "Copy the code below and paste it into the official portal."
        ],
        "btn_rastrear": "Track OTP",
        "btn_bloqueado": "Locked",
        "status_inicial": "Waiting for tracking...",
        "status_lendo": "🔎 Tracking email for: ",
        "status_sucesso": "CODE LOCATED! COPY BELOW:",
        "msg_vazio": "No accounts registered for this college.",
        "logout": "Logout",
        "btn_ok": "Login",
        "placeholder_email": "Email",
        "placeholder_senha": "Password",
        "status_disponivel": "🟢 Available",
        "status_em_uso": "🔴 In Use",
        "tooltip_bloqueio": "This license is in use by another user - it will be released at "
    },
    "es": {
        "titulo": "Centro de Rastreo OTP",
        "login_titulo": "Acceso Laboratorio",
        "login_erro": "Acceso denegado. Verifique los datos.",
        "passo_a_passo": "📖 Paso a Paso:",
        "instrucoes": [
            "Vaya al sitio web de <a href='https://auth.paciente360.com.br/login/email' target='_blank'><b>Paciente 360</b></a> y solicite el código.",
            "Vuelva aquí y haga clic en <b>'Rastrear OTP'</b> en la cuenta deseada.",
            "Copie el código a continuación y péguelo en el portal oficial."
        ],
        "btn_rastrear": "Rastrear OTP",
        "btn_bloqueado": "Bloqueado",
        "status_inicial": "Esperando rastreo...",
        "status_lendo": "🔎 Rastreando correo para: ",
        "status_sucesso": "¡CÓDIGO LOCALIZADO! COPIE ABAJO:",
        "msg_vazio": "No hay cuentas registradas para esta facultad.",
        "logout": "Salir",
        "btn_ok": "Ingresar",
        "placeholder_email": "Correo electrónico",
        "placeholder_senha": "Contraseña",
        "status_disponivel": "🟢 Disponible",
        "status_em_uso": "🔴 En uso",
        "tooltip_bloqueio": "Esta licencia está en uso por otro usuario - el acceso se liberará a las "
    }
}

def get_idioma(request: Request):
    accept_lang = request.headers.get("accept-language", "pt")
    lang = accept_lang.split(",")[0].split("-")[0][:2]
    return lang if lang in TRADUCOES else "pt"

# --- ROTA RAIZ (LOGIN) ---
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request, user_id: str = Cookie(None)):
    if user_id: return RedirectResponse(url="/dashboard")
    lang = get_idioma(request)
    t = TRADUCOES[lang]
    return f"""
    <html>
        <head>
            <title>Login | {t['titulo']}</title>
            <link rel="icon" href="{FAVICON_URL}" type="image/x-icon">
            <style>
                :root {{ --cor-laranja: #fd5e11; --cor-laranja-hover: #ff8502; --cor-azul-escuro: #1e3a5f; }}
                body {{ font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f0f2f5; margin: 0; }}
                .card {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 10px 25px rgba(30,58,95,0.1); width: 320px; text-align: center; border-top: 5px solid var(--cor-laranja); }}
                h2 {{ color: var(--cor-azul-escuro); font-size: 16px; margin-bottom: 25px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }}
                input {{ width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; outline-color: var(--cor-laranja); }}
                button {{ width: 100%; padding: 12px; background: var(--cor-laranja); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 16px; transition: background 0.3s; }}
                button:hover {{ background: var(--cor-laranja-hover); }}
                #msg {{ color: #d93025; display: none; font-size: 14px; margin-top: 15px; font-weight: 500; }}
            </style>
        </head>
        <body>
            <div class="card">
                <img src="{LOGO_URL}" alt="Logo" style="max-height: 60px; margin-bottom: 15px;">
                <h2>{t['login_titulo']}</h2>
                <input type="email" id="user" placeholder="{t['placeholder_email']}">
                <input type="password" id="pass" placeholder="{t['placeholder_senha']}">
                <button onclick="entrar()">{t['btn_ok']}</button>
                <p id="msg">{t['login_erro']}</p>
            </div>
            <script>
                async function entrar() {{
                    const email = document.getElementById('user').value;
                    const password = document.getElementById('pass').value;
                    const res = await fetch('/auth/login', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{email, password}})
                    }});
                    if(res.ok) window.location.href = '/dashboard';
                    else document.getElementById('msg').style.display = 'block';
                }}
            </script>
        </body>
    </html>
    """

@app.post("/auth/login")
async def auth_login(data: LoginData, response: Response):
    try:
        res = supabase.auth.sign_in_with_password({"email": data.email, "password": data.password})
        if res.user:
            uid = res.user.id
            token = str(time.time())
            r.set(f"active_session:{uid}", token, ex=86400)
            response.set_cookie(key="user_id", value=uid, httponly=True, max_age=86400)
            response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400)
            return {"status": "ok"}
    except: pass
    raise HTTPException(status_code=401)

# --- DASHBOARD ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user_id: str = Cookie(None), session_token: str = Cookie(None)):
    if not user_id or r.get(f"active_session:{user_id}") != session_token:
        res = RedirectResponse("/")
        res.delete_cookie("user_id")
        res.delete_cookie("session_token")
        return res

    r.set(f"last_activity:{user_id}", int(time.time()), ex=86400)
    lang = get_idioma(request)
    t = TRADUCOES[lang]
    contas = supabase.table("contas_paciente").select("*").eq("owner_id", user_id).execute()
    
    cards_html = ""
    for c in contas.data:
        nome = c.get('nome_amigavel') or 'Unidade'
        email_conta = c.get('email')
        ttl = r.ttl(f"lock:{email_conta}")
        
        if ttl > 0:
            status_txt = t['status_em_uso']
            status_cor = "#d93025"
            
            # Cálculo de horário de liberação para o Tooltip
            liberacao_dt = datetime.datetime.now() + datetime.timedelta(seconds=ttl)
            horario_liberacao = liberacao_dt.strftime("%H:%M")
            tooltip_msg = f"{t['tooltip_bloqueio']}{horario_liberacao}"
            
            btn_html = f"<button style='background:#ccc; cursor:help;' disabled title='{tooltip_msg}'>{t['btn_bloqueado']} ({ttl//60}m)</button>"
        else:
            status_txt = t['status_disponivel']
            status_cor = "#1e7e34"
            btn_html = f"<button onclick=\"monitorar('{email_conta}')\">{t['btn_rastrear']}</button>"

        cards_html += f'''
        <div class="card-conta">
            <div class="info-conta">
                <strong>{nome}</strong><br>
                <small style="color: #666;">{email_conta}</small>
            </div>
            <div class="status-badge" style="color: {status_cor};">
                {status_txt}
            </div>
            <div class="acao-conta">
                {btn_html}
            </div>
        </div>
        '''
        
    if not contas.data: cards_html = f"<p style='text-align:center; color:#666;'>{t['msg_vazio']}</p>"
    instr_html = "".join([f"<li>{item}</li>" for item in t['instrucoes']])

    return f"""
    <html>
    <head>
        <title>{t['titulo']}</title>
        <link rel="icon" href="{FAVICON_URL}" type="image/x-icon">
        <style>
            :root {{ --cor-laranja: #fd5e11; --cor-laranja-hover: #ff8502; --cor-azul-escuro: #1e3a5f; --cor-verde-menta: #00e9a9; }}
            body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; color: #333; }}
            .container {{ max-width: 600px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; background: white; padding: 15px 20px; border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            .instrucoes {{ background: white; border-left: 5px solid var(--cor-laranja); padding: 20px; border-radius: 8px; margin-bottom: 25px; line-height: 1.6; }}
            .instrucoes a {{ color: var(--cor-laranja); font-weight: bold; text-decoration: underline; }}
            .card-conta {{ background: white; padding: 15px 20px; border-radius: 12px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 2px 8px rgba(30,58,95,0.08); border-left: 4px solid var(--cor-laranja); }}
            .info-conta {{ flex: 1.5; text-align: left; }}
            .status-badge {{ flex: 1; text-align: center; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; }}
            .acao-conta {{ flex: 1.2; text-align: right; }}
            button {{ min-width: 140px; background: var(--cor-laranja); color: white; border: none; padding: 10px 15px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: all 0.2s; }}
            button:not(:disabled):hover {{ background: var(--cor-laranja-hover); }}
            .terminal {{ background: var(--cor-azul-escuro); color: white; padding: 35px 20px; border-radius: 12px; text-align: center; margin-top: 25px; border-bottom: 5px solid var(--cor-laranja); }}
            #status {{ font-size: 14px; opacity: 0.9; text-transform: uppercase; letter-spacing: 1px; }}
            #otp {{ font-size: 64px; display: block; margin-top: 15px; letter-spacing: 12px; font-weight: 900; transition: color 0.3s; }}
            .logout {{ color: var(--cor-azul-escuro); text-decoration: none; font-weight: bold; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; }}
            .lendo {{ animation: pulsar 1.5s infinite ease-in-out; }}
            @keyframes pulsar {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} 100% {{ opacity: 1; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="{LOGO_URL}" alt="Logo" style="max-height: 45px;">
                <a href="/logout" class="logout">{t['logout']}</a>
            </div>
            <div class="instrucoes">
                <strong style="color: var(--cor-azul-escuro);">{t['passo_a_passo']}</strong>
                <ol style="margin-top: 10px;">{instr_html}</ol>
            </div>
            {cards_html}
            <div class="terminal">
                <div id="status">{t['status_inicial']}</div>
                <div id="otp">------</div>
            </div>
        </div>
        <script>
            let poll;
            async function monitorar(email) {{
                await fetch('/soft-lock?email=' + encodeURIComponent(email));
                const terminal = document.querySelector('.terminal');
                terminal.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                document.getElementById('status').innerText = "{t['status_lendo']}" + email;
                const otpElem = document.getElementById('otp');
                otpElem.innerText = "......";
                otpElem.classList.add('lendo');
                if(poll) clearInterval(poll);
                poll = setInterval(async () => {{
                    const res = await fetch('/get-raw-otp?email=' + encodeURIComponent(email));
                    const data = await res.json();
                    if(data && data.otp) {{
                        otpElem.classList.remove('lendo');
                        otpElem.innerText = data.otp;
                        otpElem.style.color = "var(--cor-verde-menta)";
                        document.getElementById('status').innerText = "{t['status_sucesso']}";
                        clearInterval(poll);
                        setTimeout(() => location.reload(), 5000); 
                    }}
                }}, 3000);
            }}
        </script>
    </body>
    </html>
    """

@app.get("/soft-lock")
async def soft_lock(email: str):
    r.set(f"lock:{email.lower()}", "pendente", ex=900)
    return {"status": "ok"}

@app.post("/webhook-sistema")
async def webhook_sistema(request: Request):
    client_id = request.query_params.get("client_id")
    client_key = request.query_params.get("client_key")
    data = await request.json()
    if not client_id:
        client_id = request.headers.get("x-client-id") or data.get("client_id")
    if not client_key:
        client_key = request.headers.get("x-client-key") or data.get("client_key")
    if not client_id or not client_key:
        raise HTTPException(status_code=401, detail="Credenciais ausentes.")
    check_auth = supabase.table("api_keys").select("id").eq("client_id", client_id).eq("client_key", client_key).execute()
    if not check_auth.data:
        raise HTTPException(status_code=403, detail="Acesso Negado.")
    email = data.get("user", {}).get("email", "").lower().strip()
    progresso = data.get("progresso", 0)
    if email and progresso > 0:
        r.set(f"lock:{email}", "sucesso", ex=7200) # 2h Hard Lock
        print(f"🔒 [LOCK] Conta {email} travada por 2h.")
        return {"status": "locked", "message": "Sucesso"}
    return {"status": "ignored"}

@app.get("/get-raw-otp")
async def get_otp(email: str, user_id: str = Cookie(None)):
    if not user_id: return {"otp": None}
    email_limpo = email.strip().lower()
    check = supabase.table("contas_paciente").select("id").eq("email", email_limpo).eq("owner_id", user_id).execute()
    if check.data:
        return {"otp": r.get(f"otp:{email_limpo}")}
    return {"otp": None}

@app.post("/webhook-sendgrid")
async def webhook_sendgrid(request: Request):
    form = await request.form()
    email_html, email_to = form.get("html", ""), form.get("to", "").lower()
    match_to = re.search(r'[\w\.-]+@[\w\.-]+', email_to)
    if match_to:
        alvo = match_to.group(0).strip().lower()
        otp_match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = otp_match.group(1) if otp_match else None
        if otp: r.set(f"otp:{alvo}", otp, ex=300)
    return {"status": "ok"}

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie("user_id")
    response.delete_cookie("session_token")
    return RedirectResponse("/")
