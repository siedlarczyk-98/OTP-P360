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

# --- DICIONÁRIO DE TRADUÇÃO COMPLETO ---
TRADUCOES = {
    "pt": {
        "titulo": "Central de Rastreamento OTP",
        "login_titulo": "Portal Faculdades",
        "login_erro": "Acesso negado. Verifique os dados.",
        "passo_a_passo": "📖 Passo a Passo:",
        "instrucoes": [
            "Vá ao site da <b>Paciente 360</b> e solicite o código de acesso.",
            "Volte aqui e clique em <b>'Rastrear OTP'</b> na conta desejada.",
            "Copie o código abaixo e cole no site da Paciente 360."
        ],
        "btn_rastrear": "Rastrear OTP",
        "status_inicial": "Aguardando rastreamento...",
        "status_lendo": "🔎 Rastreando e-mail para: ",
        "status_sucesso": "✅ CÓDIGO LOCALIZADO! COPIE ABAIXO:",
        "msg_vazio": "Nenhuma conta cadastrada para esta faculdade.",
        "logout": "Sair",
        "btn_ok": "OK",
        "placeholder_email": "E-mail",
        "placeholder_senha": "Senha"
    },
    "en": {
        "titulo": "OTP Tracking Hub",
        "login_titulo": "College Portal",
        "login_erro": "Access denied. Please check your credentials.",
        "passo_a_passo": "📖 Step by Step:",
        "instrucoes": [
            "Go to the <b>Paciente 360</b> website and request your access code.",
            "Return here and click <b>'Track OTP'</b> on the desired account.",
            "Copy the code below and paste it into the Paciente 360 website."
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
    
    # Extração das variáveis para evitar problemas na f-string
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
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f0f2f5; margin: 0; }}
                .card {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); width: 320px; text-align: center; }}
                input {{ width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; }}
                button {{ width: 100%; padding: 12px; background: #1877f2; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 16px; transition: background 0.3s; }}
                button:hover {{ background: #166fe5; }}
                #msg {{ color: #d93025; display: none; font-size: 14px; margin-top: 15px; font-weight: 500; }}
            </style>
        </head>
        <body>
            <div class="card">
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
                <small>{email_conta}</small>
            </div>
            <button onclick="monitorar('{email_conta}')">{btn_rastrear}</button>
        </div>
        '''

    if not contas.data:
        cards_html = f"<p style='text-align:center; color:#666;'>{t['msg_vazio']}</p>"

    instr_html = "".join([f"<li>{item}</li>" for item in t['instrucoes']])
    
    # Extração para uso seguro no JS e HTML
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
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; color: #333; }}
            .container {{ max-width: 600px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
            .instrucoes {{ background: #fff4e5; border-left: 5px solid #ffa117; padding: 15px; border-radius: 8px; margin-bottom: 25px; line-height: 1.5; }}
            .card-conta {{ background: white; padding: 15px; border-radius: 12px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            button {{ background: #1877f2; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: background 0.2s; }}
            button:hover {{ background: #166fe5; }}
            .terminal {{ background: #1c1e21; color: #42b72a; padding: 30px; border-radius: 12px; text-align: center; margin-top: 20px; box-shadow: inset 0 2px 10px rgba(0,0,0,0.5); }}
            #otp {{ font-size: 56px; color: white; display: block; margin-top: 10px; letter-spacing: 10px; font-weight: bold; }}
            .logout {{ color: #d93025; text-decoration: none; font-size: 14px; font-weight: bold; padding: 8px 12px; border-radius: 6px; }}
            .logout:hover {{ background: #fce8e6; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>{titulo}</h2>
                <a href="/logout" class="logout">{logout_txt}</a>
            </div>
            
            <div class="instrucoes">
                <strong>{passo_a_passo}</strong>
                <ol>{instr_html}</ol>
            </div>

            {cards_html}

            <div class="terminal">
                <div id="status">{status_inicial}</div>
                <div id="otp">------</div>
            </div>
        </div>

        <script>
            // Passando as traduções para o JS de forma segura
            const txtLendo = "{status_lendo}";
            const txtSucesso = "{status_sucesso}";
            
            let poll;
            function monitorar(email) {{
                document.getElementById('status').innerText = txtLendo + email;
                document.getElementById('otp').innerText = "......";
                
                if(poll) clearInterval(poll);
                poll = setInterval(async () => {{
                    try {{
                        const res = await fetch('/get-raw-otp?email=' + encodeURIComponent(email));
                        const data = await res.json();
                        if(data && data.otp) {{
                            document.getElementById('otp').innerText = data.otp;
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
