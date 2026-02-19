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
        "logout": "Sair"
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
        "logout": "Logout"
    }
}

def get_idioma(request: Request):
    accept_lang = request.headers.get("accept-language", "pt")
    # Pega o primeiro idioma da lista do navegador
    lang = accept_lang.split(",")[0].split("-")[0][:2]
    return lang if lang in TRADUCOES else "pt"

# --- ROTAS ---

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
        return {"otp": r.get(f"otp:{email}")}
    return {"otp": None}

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie("user_id")
    return RedirectResponse("/")
