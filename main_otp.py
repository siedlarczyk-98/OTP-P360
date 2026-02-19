import os
import re
import redis
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

# --- ASSETS DA MARCA (SUPABASE STORAGE) ---
LOGO_URL = "https://biabapecceelzvwwunvm.supabase.co/storage/v1/object/public/icons/logo.png"
FAVICON_URL = "https://biabapecceelzvwwunvm.supabase.co/storage/v1/object/public/icons/favicon.ico"

# --- DICIONÁRIO DE TRADUÇÃO COMPLETO ---
TRADUCOES = {
    "pt": {
        "titulo": "Central de Rastreamento OTP",
        "login_titulo": "Acesso Restrito",
        "login_erro": "Acesso negado. Verifique os dados.",
        "passo_a_passo": "📖 Passo a Passo:",
        "instrucoes": [
            "Vá ao site da <b>Paciente 360</b> e solicite o código de acesso.",
            "Volte aqui e clique em <b>'Rastrear OTP'</b> na conta desejada.",
            "Copie o código abaixo e cole no portal oficial."
        ],
        "btn_rastrear": "Rastrear OTP",
        "status_inicial": "Aguardando rastreamento...",
        "status_lendo": "🔎 Rastreando e-mail para: ",
        "status_sucesso": "✅ CÓDIGO LOCALIZADO! COPIE ABAIXO:",
        "msg_vazio": "Nenhuma conta cadastrada para esta faculdade.",
        "logout": "Sair",
        "btn_ok": "Entrar",
        "placeholder_email": "E-mail",
        "placeholder_senha": "Senha"
    },
    "en": {
        "titulo": "OTP Tracking Hub",
        "login_titulo": "Restricted Access",
        "login_erro": "Access denied. Please check your credentials.",
        "passo_a_passo": "📖 Step by Step:",
        "instrucoes": [
            "Go to the <b>Paciente 360</b> website and request your access code.",
            "Return here and click <b>'Track OTP'</b> on the desired account.",
            "Copy the code below and paste it into the official portal."
        ],
        "btn_rastrear": "Track OTP",
        "status_inicial": "Waiting for tracking...",
        "status_lendo": "🔎 Tracking email for: ",
        "status_sucesso": "✅ CODE LOCATED! COPY BELOW:",
        "msg_vazio": "No accounts registered for this college.",
        "logout": "Logout",
        "btn_ok": "Login",
        "placeholder_email": "Email",
        "placeholder_senha": "Password"
    },
    "es": {
        "titulo": "Centro de Rastreo OTP",
        "login_titulo": "Acceso Restringido",
        "login_erro": "Acceso denegado. Verifique los datos.",
        "passo_a_passo": "📖 Paso a Paso:",
        "instrucoes": [
            "Vaya al sitio web de <b>Paciente 360</b> y solicite el código de acceso.",
            "Vuelva aquí y haga clic en <b>'Rastrear OTP'</b> en la cuenta deseada.",
            "Copie el código a continuación y péguelo en el portal oficial."
        ],
        "btn_rastrear": "Rastrear OTP",
        "status_inicial": "Esperando rastreo...",
        "status_lendo": "🔎 Rastreando correo para: ",
        "status_sucesso": "✅ ¡CÓDIGO LOCALIZADO! COPIE ABAJO:",
        "msg_vazio": "No hay cuentas registradas para esta facultad.",
        "logout": "Salir",
        "btn_ok": "Ingresar",
        "placeholder_email": "Correo electrónico",
        "placeholder_senha": "Contraseña"
    }
}

def get_idioma(request: Request):
    accept_lang = request.headers.get("accept-language", "pt")
    lang = accept_lang.split(",")[0].split("-")[0][:2]
    return lang if lang in TRADUCOES else "pt"

# --- ROTA RAIZ (LOGIN) ---

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request, user_id: str = Cookie(None)):
    if user_id: 
        return RedirectResponse(url="/dashboard")
    
    lang = get_idioma(request)
    t = TRADUCOES[lang]
    
    titulo = t['titulo']
    login_titulo = t['login_titulo']
    login_erro = t['login_erro']
    btn_ok = t['btn_ok']
    p_email = t['placeholder_email']
    p_senha = t['placeholder_senha']
    
    return f"""
    <html>
        <head>
            <title>Login | {titulo}</title>
            <link rel="icon" href="{FAVICON_URL}" type="image/x-icon">
            <style>
                :root {{
                    --cor-laranja: #fd5e11;
                    --cor-laranja-hover: #ff8502;
                    --cor-azul-escuro: #1e3a5f;
                }}
                body {{ font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f0f2f5; margin: 0; }}
                .card {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 10px 25px rgba(30,58,95,0.1); width: 320px; text-align: center; border-top: 5px solid var(--cor-laranja); }}
                h2 {{ color: var(--cor-azul-escuro); font-size: 16px; margin-top: 0; margin-bottom: 25px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }}
                input {{ width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; outline-color: var(--cor-laranja); }}
                button {{ width: 100%; padding: 12px; background: var(--cor-laranja); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 16px; transition: background 0.3s; margin-top: 10px; }}
                button:hover {{ background: var(--cor-laranja-hover); }}
                #msg {{ color: #d93025; display: none; font-size: 14px; margin-top: 15px; font-weight: 500; }}
            </style>
        </head>
        <body>
            <div class="card">
                <img src="{LOGO_URL}" alt="Logo" style="max-height: 60px; margin-bottom: 15px;">
                <h2>{login_titulo}</h2>
                <input type="email" id="user" placeholder="{p_email}">
                <input type="password" id="pass" placeholder="{p_senha}">
                <button onclick="entrar()">{btn_ok}</button>
                <p id="msg">{login_erro}</p>
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
            response.set_cookie(key="user_id", value=res.user.id, httponly=True, max_age=3600 * 12)
            return {"status": "ok"}
    except:
        pass
    raise HTTPException(status_code=401)

# --- DASHBOARD MULTI-IDIOMA ---

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user_id: str = Cookie(None)):
    if not user_id: return RedirectResponse("/")

    lang = get_idioma(request)
    t = TRADUCOES[lang]

    contas = supabase.table("contas_paciente").select("*").eq("owner_id", user_id).execute()
    
    btn_rastrear = t['btn_rastrear']
    cards_html = ""
    for c in contas.data:
        nome = c.get('nome_amigavel') or 'Unidade'
        email_conta = c.get('email')
        cards_html += f'''
        <div class="card-conta">
            <div>
                <strong>{nome}</strong><br>
                <small style="color: #666;">{email_conta}</small>
            </div>
            <button onclick="monitorar('{email_conta}')">{btn_rastrear}</button>
        </div>
        '''

    if not contas.data:
        cards_html = f"<p style='text-align:center; color:#666;'>{t['msg_vazio']}</p>"

    instr_html = "".join([f"<li>{item}</li>" for item in t['instrucoes']])
    
    titulo = t['titulo']
    logout_txt = t['logout']
    passo_a_passo = t['passo_a_passo']
    status_inicial = t['status_inicial']
    status_lendo = t['status_lendo']
    status_sucesso = t['status_sucesso']

    return f"""
    <html>
    <head>
        <title>{titulo}</title>
        <link rel="icon" href="{FAVICON_URL}" type="image/x-icon">
        <style>
            :root {{
                --cor-laranja: #fd5e11;
                --cor-laranja-hover: #ff8502;
                --cor-azul-escuro: #1e3a5f;
                --cor-verde-menta: #00e9a9;
            }}
            body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; color: #333; }}
            .container {{ max-width: 600px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; background: white; padding: 15px 20px; border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            .instrucoes {{ background: white; border-left: 5px solid var(--cor-laranja); padding: 20px; border-radius: 8px; margin-bottom: 25px; line-height: 1.6; box-shadow: 0 2px 5px rgba(30,58,95,0.05); }}
            .card-conta {{ background: white; padding: 15px 20px; border-radius: 12px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 8px rgba(30,58,95,0.08); border: 1px solid #eef2f6; border-left: 4px solid var(--cor-laranja); }}
            button {{ background: var(--cor-laranja); color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: background 0.2s; }}
            button:hover {{ background: var(--cor-laranja-hover); }}
            
            /* Terminal Customizado */
            .terminal {{ background: var(--cor-azul-escuro); color: white; padding: 35px 20px; border-radius: 12px; text-align: center; margin-top: 25px; box-shadow: 0 10px 20px rgba(30,58,95,0.2); border-bottom: 5px solid var(--cor-laranja); }}
            #status {{ font-size: 14px; opacity: 0.9; text-transform: uppercase; letter-spacing: 1px; }}
            #otp {{ font-size: 64px; display: block; margin-top: 15px; letter-spacing: 12px; font-weight: 900; transition: color 0.3s; }}
            
            .logout {{ color: var(--cor-azul-escuro); text-decoration: none; font-size: 14px; font-weight: bold; padding: 8px 12px; border-radius: 6px; border: 1px solid #ddd; transition: background 0.2s; }}
            .logout:hover {{ background: #eef2f6; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="{LOGO_URL}" alt="Logo" style="max-height: 45px;">
                <a href="/logout" class="logout">{logout_txt}</a>
            </div>
            
            <div class="instrucoes">
                <strong style="color: var(--cor-azul-escuro); font-size: 16px;">{passo_a_passo}</strong>
                <ol style="margin-bottom: 0;">{instr_html}</ol>
            </div>

            {cards_html}

            <div class="terminal">
                <div id="status">{status_inicial}</div>
                <div id="otp">------</div>
            </div>
        </div>

        <script>
            const txtLendo = "{status_lendo}";
            const txtSucesso = "{status_sucesso}";
            
            let poll;
            function monitorar(email) {{
                document.getElementById('status').innerText = txtLendo + email;
                document.getElementById('otp').innerText = "......";
                document.getElementById('otp').style.color = "white"; // Reset cor
                document.getElementById('otp').style.textShadow = "none";
                
                if(poll) clearInterval(poll);
                poll = setInterval(async () => {{
                    try {{
                        const res = await fetch('/get-raw-otp?email=' + encodeURIComponent(email));
                        const data = await res.json();
                        if(data && data.otp) {{
                            document.getElementById('otp').innerText = data.otp;
                            document.getElementById('otp').style.color = "var(--cor-verde-menta)"; // Brilha verde ao achar
                            document.getElementById('otp').style.textShadow = "0 0 15px rgba(0, 233, 169, 0.4)";
                            document.getElementById('status').innerText = txtSucesso;
                            clearInterval(poll); // Para de buscar quando acha
                        }}
                    }} catch (e) {{
                        console.error("Erro ao buscar OTP:", e);
                    }}
                }}, 3000);
            }}
        </script>
    </body>
    </html>
    """

# --- OPERAÇÕES ---

@app.get("/get-raw-otp")
async def get_otp(email: str, user_id: str = Cookie(None)):
    if not user_id: return {"otp": None}
    
    email_limpo = email.strip().lower()
    check = supabase.table("contas_paciente").select("id").eq("email", email_limpo).eq("owner_id", user_id).execute()
    
    if check.data:
        codigo = r.get(f"otp:{email_limpo}")
        print(f"🔎 [DASHBOARD] Buscando chave otp:{email_limpo} -> Resultado: {codigo}", flush=True)
        return {"otp": codigo}
    return {"otp": None}

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    form = await request.form()
    email_html = form.get("html", "")
    email_to = form.get("to", "").lower()
    match_to = re.search(r'[\w\.-]+@[\w\.-]+', email_to)
    
    if match_to:
        alvo = match_to.group(0).strip().lower()
        otp_match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = otp_match.group(1) if otp_match else None
        
        if otp:
            r.set(f"otp:{alvo}", otp, ex=300)
            print(f"✅ [WEBHOOK] OTP {otp} salvo para: otp:{alvo}", flush=True)
    return {"status": "ok"}

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie("user_id")
    return RedirectResponse("/")
