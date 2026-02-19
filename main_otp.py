import os
import asyncio
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from supabase import create_client, Client
import redis

app = FastAPI()

# --- CONFIGURAÇÕES ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") # Use a SERVICE_ROLE para o backend ter poder de Admin
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- DASHBOARD PRINCIPAL ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # 1. Busca as contas autorizadas no Supabase
    # Aqui o backend usa a service_role para listar o que está cadastrado
    contas = supabase.table("contas_paciente").select("*").execute()
    
    lista_html = ""
    for conta in contas.data:
        lista_html += f"""
        <div class="card">
            <div>
                <strong>{conta['nome_amigavel'] or 'Sem Nome'}</strong><br>
                <small>{conta['email_alvo']}</small>
            </div>
            <button onclick="solicitarOTP('{conta['email_alvo']}')">Solicitar Código</button>
        </div>
        """

    return f"""
    <html>
        <head>
            <title>Painel OTP Admin</title>
            <style>
                body {{ font-family: sans-serif; background: #f4f7f6; padding: 40px; }}
                .container {{ max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }}
                .card {{ display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #eee; }}
                button {{ background: #1877f2; color: white; border: none; padding: 8px 15px; border-radius: 6px; cursor: pointer; }}
                button:disabled {{ background: #ccc; }}
                .monitor-area {{ margin-top: 30px; padding: 20px; background: #282c34; color: #61dafb; border-radius: 8px; font-family: monospace; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>🔐 Gerenciador de Acessos</h2>
                <div id="lista-contas">{lista_html}</div>
                
                <div class="monitor-area">
                    <div id="status">Selecione uma conta acima</div>
                    <div id="otp-display" style="font-size: 32px; margin: 10px 0;">-- -- --</div>
                </div>
            </div>

            <script>
                async function solicitarOTP(email) {{
                    document.getElementById('status').innerText = "🤖 Robô disparado para " + email;
                    document.getElementById('otp-display').innerText = "Aguardando...";
                    
                    // Chama a rota que dispara o Playwright em background
                    fetch('/disparar-robo?email=' + email);
                    
                    // Inicia o monitoramento do Redis para esse email
                    iniciarMonitor(email);
                }}

                let interval;
                function iniciarMonitor(email) {{
                    if(interval) clearInterval(interval);
                    interval = setInterval(async () => {{
                        const res = await fetch('/get-raw-otp?email=' + email);
                        const data = await res.json();
                        if(data.otp) {{
                            document.getElementById('otp-display').innerText = data.otp;
                            document.getElementById('status').innerText = "✅ CÓDIGO CAPTURADO!";
                            clearInterval(interval);
                        }}
                    }}, 2000);
                }}
            </script>
        </body>
    </html>
    """
