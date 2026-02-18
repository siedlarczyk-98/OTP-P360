from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import redis
import os
import re
import asyncio

app = FastAPI()

# --- CONFIGURAÇÃO REDIS ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

DOMINIO_PERMITIDO = "@otp-p360.com.br"

@app.get("/")
def home():
    return {"status": "Monitor de OTP Online", "instrucao": "Acesse /ver-otp?email=seuemail@dominio.com"}

@app.post("/webhook-sendgrid")
async def webhook(request: Request):
    try:
        form = await request.form()
        email_html = form.get("html", "")
        email_to_raw = form.get("to", "").lower()
        
        email_match = re.search(r'[\w\.-]+@[\w\.-]+', email_to_raw)
        if not email_match: return {"status": "error"}
            
        email_limpo = email_match.group(0)
        print(f"📩 WEBHOOK: E-mail recebido para {email_limpo}")

        # Busca o código de 6 dígitos no HTML
        match = re.search(r'color:#191847;">(\d{6})</p>', email_html)
        otp = match.group(1) if match else None

        if not otp:
            match_fallback = re.search(r'\b\d{6}\b', email_html)
            otp = match_fallback.group(0) if match_fallback else None

        if otp:
            r.set(f"otp:{email_limpo}", str(otp), ex=120) # Expira em 2 min
            print(f"✅ WEBHOOK: OTP {otp} capturado!")
            return {"status": "success"}
        
        return {"status": "no_otp_found"}
    except Exception as e:
        print(f"🔥 ERRO WEBHOOK: {e}")
        return {"status": "error"}

@app.get("/ver-otp")
async def ver_otp(email: str):
    email = email.lower().strip()
    if not email.endswith(DOMINIO_PERMITIDO):
        return HTMLResponse("<h2>Domínio não autorizado</h2>", status_code=403)

    # Limpamos o código antigo ao abrir a página para garantir que você veja um NOVO
    # Se você quiser que ele mostre o que já está lá, comente a linha abaixo
    # r.delete(f"otp:{email}")

    return HTMLResponse(content=f"""
    <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Monitor de OTP</title>
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f0f2f5; }}
                .card {{ background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); text-align: center; width: 350px; }}
                .email {{ color: #65676b; font-size: 14px; margin-bottom: 20px; }}
                .otp-box {{ font-size: 48px; font-weight: bold; color: #1877f2; letter-spacing: 5px; margin: 20px 0; min-height: 60px; }}
                .status {{ font-size: 14px; color: #f02849; font-weight: bold; }}
                .loader {{ border: 4px solid #f3f3f3; border-top: 4px solid #1877f2; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 0 auto; display: none; }}
                @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
                .btn-copy {{ background: #1877f2; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; display: none; width: 100%; font-weight: bold; }}
                .btn-copy:active {{ background: #145dbf; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2 style="margin-top:0">Monitor OTP</h2>
                <div class="email">{email}</div>
                <div id="loader" class="loader" style="display: block;"></div>
                <div id="otp-display" class="otp-box">------</div>
                <div id="status" class="status">Aguardando e-mail...</div>
                <button id="copy-btn" class="btn-copy" onclick="copyOTP()">COPIAR CÓDIGO</button>
            </div>

            <script>
                async function checkOTP() {{
                    try {{
                        const response = await fetch('/get-raw-otp?email={email}');
                        const data = await response.json();
                        
                        if (data.otp) {{
                            document.getElementById('otp-display').innerText = data.otp;
                            document.getElementById('status').innerText = "CÓDIGO RECEBIDO!";
                            document.getElementById('status').style.color = "#42b72a";
                            document.getElementById('loader').style.display = "none";
                            document.getElementById('copy-btn').style.display = "block";
                        }}
                    }} catch (e) {{ console.log("Erro ao buscar OTP"); }}
                }}

                function copyOTP() {{
                    const otp = document.getElementById('otp-display').innerText;
                    navigator.clipboard.writeText(otp);
                    document.getElementById('copy-btn').innerText = "COPIADO!";
                    setTimeout(() => {{ document.getElementById('copy-btn').innerText = "COPIAR CÓDIGO"; }}, 2000);
                }}

                // Verifica a cada 2 segundos
                setInterval(checkOTP, 2000);
            </script>
        </body>
    </html>
    """)

@app.get("/get-raw-otp")
async def get_raw_otp(email: str):
    otp = r.get(f"otp:{email}")
    return {"otp": otp}
