import os
import re
import redis
from fastapi import FastAPI, Request, HTTPException, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI()

# --- CONFIGURAÇÕES ---
r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

class LoginData(BaseModel):
    email: str
    password: str

# --- DICIONÁRIO DE TRADUÇÃO ---
TRADUCOES = {
    "pt": {
        "titulo": "Central de Rastreamento OTP",
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
        "login_titulo": "Portal Faculdades",
        "login_erro": "Acesso negado. Verifique os dados."
    },
    "en": {
        "titulo": "OTP Tracking Hub",
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
        "login_titulo": "College Portal",
        "login_erro": "Access denied. Please check your credentials."
    }
}

def get_idioma(request: Request):
    accept_lang = request.headers.get("accept-language", "pt")
    lang = accept_lang.split(",")[0].split("-")[0][:2]
    return lang if lang in TRADUCOES else "pt"

# --- ROTA RAIZ (LOGIN) ---

@app.get("/get-raw-otp")
async def get_otp(email: str, user_id: str = Cookie(None)):
    if not user_id: 
        return {"otp": None}
    
    # 1. Limpeza total do e-mail para evitar erros de maiúsculas/espaços
    email_limpo = email.strip().lower()
    
    # 2. Debug forçado para o log do Railway
    print(f"🔎 [DASHBOARD] Buscando no Redis a chave: otp:{email_limpo}", flush=True)

    # 3. Verifica no banco se este e-mail pertence ao usuário logado
    check = supabase.table("contas_paciente").select("id").eq("email", email_limpo).eq("owner_id", user_id).execute()
    
    if check.data:
        # 4. BUSCA CORRETA: Uma única chave para injetar a variável
        codigo = r.get(f"otp:{email_limpo}")
        print(f"💰 [RESULTADO] Código encontrado no Redis: {codigo}", flush=True)
        return {"otp": codigo}
    
    print(f"🚫 [ERRO] A conta {email_limpo} não pertence ao usuário {user_id}", flush=True)
    return {"otp": None}

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    form = await request.form()
    email_html = form.get("html", "")
    email_to = form.get("to", "").lower()
    
    match_to = re.search(r'[\w\.-]+@[\w\.-]+', email_to)
    if match_to:
        # 1. Limpeza total no salvamento também
        alvo = match_to.group(0).strip().lower()
        
        # Regex do OTP (Paciente 360)
        otp_match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = otp_match.group(1) if otp_match else None
        
        if otp:
            # Salvamos com a mesma estrutura de limpeza
            r.set(f"otp:{alvo}", otp, ex=300) # 5 minutos de validade
            print(f"✅ [WEBHOOK] OTP {otp} salvo para a chave: otp:{alvo}", flush=True)
            
    return {"status": "ok"}

# --- DASHBOARD ---

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user_id: str = Cookie(None)):
    if not user_id: return RedirectResponse("/")

    idioma = get_idioma(request)
    t = TRADUCOES[idioma]

    contas = supabase.table("contas_paciente").select("*").eq("owner_id", user_id).execute()
    
    cards_html = ""
    for c in contas.data:
        nome = c.get('nome_amigavel') or 'Unidade'
        cards_html += f'''
        <div class="card-conta">
            <div>
                <strong>{nome}</strong><br>
                <small>{c['email']}</small>
            </div>
            <button onclick="monitorar('{c['email']}')">{t['btn_rastrear']}</button>
        </div>
        '''

    if not contas.data:
        cards_html = f"<p style='text-align:center; color:#666;'>{t['msg_vazio']}</p>"

    instr_html = "".join([f"<li>{item}</li>" for item in t['instrucoes']])

    return f"""
    <html>
    <head>
        <title>{t['titulo']}</title>
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; color: #333; }}
            .container {{ max-width: 600px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
            .instrucoes {{ background: #fff4e5; border-left: 5px solid #ffa117; padding: 15px; border-radius: 8px; margin-bottom: 25px; }}
            .card-conta {{ background: white; padding: 15px; border-radius: 12px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            button {{ background: #1877f2; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; }}
            .terminal {{ background: #1c1e21; color: #42b72a; padding: 30px; border-radius: 12px; text-align: center; margin-top: 20px; }}
            #otp {{ font-size: 56px; color: white; display: block; margin-top: 10px; letter-spacing: 10px; font-weight: bold; }}
            .logout {{ color: #d93025; text-decoration: none; font-size: 14px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>{t['titulo']}</h2>
                <a href="/logout" class="logout">{t['logout']}</a>
            </div>
            
            <div class="instrucoes">
                <strong>{t['passo_a_passo']}</strong>
                <ol>{instr_html}</ol>
            </div>

            {cards_html}

            <div class="terminal">
                <div id="status">{t['status_inicial']}</div>
                <div id="otp">------</div>
            </div>
        </div>

        <script>
            let poll;
            function monitorar(email) {{
                document.getElementById('status').innerText = "{t['status_lendo']}" + email;
                document.getElementById('otp').innerText = "......";
                
                if(poll) clearInterval(poll);
                poll = setInterval(async () => {{
                    const res = await fetch('/get-raw-otp?email=' + email);
                    const data = await res.json();
                    if(data.otp) {{
                        document.getElementById('otp').innerText = data.otp;
                        document.getElementById('status').innerText = "{t['status_sucesso']}";
                    }}
                }}, 3000);
            }}
        </script>
    </body>
    </html>
    """

@app.get("/get-raw-otp")
async def get_otp(email: str, user_id: str = Cookie(None)):
    if not user_id: return {"otp": None}
    check = supabase.table("contas_paciente").select("id").eq("email", email).eq("owner_id", user_id).execute()
    if check.data:
        return {"otp": r.get(f"otp:{{email}}")} # Nota: use f"otp:{{email}}" para escapar chaves em strings f-string ou r.get(f"otp:{email}")
    return {"otp": None}

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie("user_id")
    return RedirectResponse("/")

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    form = await request.form()
    email_html = form.get("html", "")
    email_to = form.get("to", "").lower()
    match_to = re.search(r'[\w\.-]+@[\w\.-]+', email_to)
    if match_to:
        alvo = match_to.group(0)
        otp_match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = otp_match.group(1) if otp_match else None
        if otp:
            r.set(f"otp:{alvo}", otp, ex=180)
    return {"status": "ok"}
