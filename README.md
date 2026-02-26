# 📚 Central de Rastreamento OTP (OTP Tracking Hub) - Paciente 360

A **Central de Rastreamento OTP** é uma aplicação web construída em Python (FastAPI) que atua como uma ponte entre alunos de laboratórios virtuais e a plataforma Paciente 360. Foi criado como alternativa para viabilizar a venda no formato de licenças genéricas.

O sistema permite que contas de acesso compartilhado sejam gerenciadas com segurança, interceptando códigos de verificação (OTPs) enviados por e-mail e exibindo-os na tela para o usuário final, ao mesmo tempo em que gerencia "travas de uso" (Locks) para evitar acessos simultâneos indevidos. Esses envios se dão todos para um mesmo domínio, cujo controle permanece na mão da Active Metodologias Ativas de Ensino LTDA.

---

## Telas do Sistema

![Tela de Login](/assets/login.png)
*Tela de login com suporte a múltiplos idiomas. Suporta Português, Espanhol e Inglês*

![Dashboard de Contas](/assets/dashboard.png)
*Painel principal mostrando contas disponíveis e o terminal de rastreamento em tempo real.*

![Tooltip Dinâmico](/assets/tooltip.png)
*Sistema de bloqueio com tooltip inteligente calculando o horário local de liberação.*

---

## 🚀 Tecnologias Utilizadas

* **Backend:** Python 3 + FastAPI 
* **Banco de Dados & Auth:** Supabase (PostgreSQL).
* **Cache & Mensageria:** Redis 
* **Frontend:** HTML5, CSS3 e Vanilla JS 
* **Integração de E-mail:** SendGrid Inbound Parse 

---

##  Funcionalidades Principais

###   Autenticação e Sessão Única (Single-Session)
* Login integrado ao Supabase Auth.
* O sistema utiliza o Redis para garantir apenas **uma sessão válida por usuário**. Logar em outro dispositivo derruba a sessão anterior instantaneamente.

###   Dashboard Dinâmico e Multilíngue
* Detecção automática do idioma do navegador (`pt`, `en`, `es`).
* Detecção automática do fuso horário para cálculo dos horários de liberação das licenças
* Lista apenas as contas de laboratório vinculadas ao usuário logado (Admin/Faculdade).

###   Sistema de Travamento Duplo (Locks)
* **Soft Lock (15 min):** Acionado ao clicar em "Rastrear OTP". Evita que colegas da mesma faculdade solicitem o mesmo laboratório simultaneamente.
* **Hard Lock (2 horas):** Acionado via Webhook quando o aluno inicia o Paciente 360, garantindo tempo hábil para a conclusão dos casos.

###   Tooltips Inteligentes (Timezone Automático)
* Botões bloqueados exibem um tooltip customizado informando o horário exato de liberação.
* O cálculo converte o tempo restante (TTL do Redis) para o **fuso horário local do computador do aluno** via JavaScript, evitando confusões de fuso horário do servidor.

###   Captura Automatizada de OTP
* Webhooks em tempo real do SendGrid varrem o HTML de e-mails recebidos via Expressões Regulares (Regex).
* O código de 6 dígitos é extraído e armazenado no Redis, sendo capturado pelo frontend do aluno via *Long Polling* em poucos segundos.

---

## 🗄️ Estrutura do Banco de Dados (Supabase)

O sistema depende de duas tabelas principais:

1. **`contas_paciente`**: Credenciais dos laboratórios - Cadastradas no admin
   - `id`: PK 
   - `email`: E-mail da conta compartilhada.
   - `nome_amigavel`: Nome de exibição.
   - `owner_id`: FK (Usuário dono da conta) - Gerado pelo admin que dá acesso ao Dashboard

2. **`api_keys`**: Credenciais para o Webhook do Paciente 360.
   - `id`: PK. - Procurar usar o mesmo ID da empresa cadastrados no admin 
   - `client_id`: ID da plataforma parceira.
   - `client_key`: Chave de segurança para autorizar o Hard Lock.

---

## 🔌 Documentação dos Endpoints (API)

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/` | Página de login. Redireciona para `/dashboard` se autenticado. |
| `POST` | `/auth/login` | Autentica, gera Token no Redis e define cookies HTTPOnly. |
| `GET` | `/dashboard` | Renderiza o painel principal e lê os locks do Redis. |
| `GET` | `/soft-lock` | Inicia a trava de segurança de 15 minutos. |
| `GET` | `/get-raw-otp` | Faz polling no Redis buscando o OTP da conta selecionada. |
| `POST` | `/webhook-sendgrid` | Recebe e-mail bruto, faz o parse (Regex) e salva no Redis. |
| `POST` | `/webhook-sistema` | Valida API Keys e aplica o Hard Lock (2h) em contas em uso. |
| `GET` | `/logout` | Destrói a sessão e cookies. |

---

## 🔄 Fluxos de Operação

### 1. Rastreamento pelo Aluno
1. O aluno acessa o painel e clica em **"Rastrear OTP"**.
2. O endpoint `/soft-lock` bloqueia a conta por 15 min.
3. O painel começa a monitorar o Redis a cada 3 segundos (`/get-raw-otp`).
4. O SendGrid recebe o e-mail oficial e avisa o `/webhook-sendgrid`.
5. O código é filtrado, salvo no Redis e aparece na tela do aluno imediatamente.

### 2. Bloqueio Definitivo (Paciente 360)
1. O aluno entra na aula do laboratório.
2. A plataforma envia um Webhook contendo `client_id`, `client_key`, `email` e `progresso`.
3. O FastAPI valida as chaves no banco.
4. O Soft Lock é substituído pelo Hard Lock de 2 horas.
5. O botão no painel de todos os alunos daquela faculdade fica cinza, mostrando o horário exato de liberação.

## 🏗️ Arquitetura do Sistema

O diagrama abaixo ilustra como os diferentes serviços (FastAPI, Redis, Supabase, SendGrid e a Plataforma EAD) se comunicam para garantir que o código OTP seja entregue com segurança e que os acessos não entrem em conflito.

```mermaid
graph TD
    %% Definição de Estilos
    classDef frontend fill:#1e3a5f,stroke:#fff,stroke-width:2px,color:#fff;
    classDef backend fill:#fd5e11,stroke:#fff,stroke-width:2px,color:#fff;
    classDef database fill:#00e9a9,stroke:#fff,stroke-width:2px,color:#1e3a5f;
    classDef external fill:#555,stroke:#fff,stroke-width:2px,color:#fff;

    %% Componentes
    User(( Aluno / Frontend)):::frontend
    Paciente 360 [Plataforma]:::external
    SendGrid[ SendGrid]:::external
    
    FastAPI{Servidor FastAPI}:::backend
    
    Supabase[(Supabase<br>Auth & BD)]:::database
    Redis[(Redis<br>Cache & Locks)]:::database

    %% Fluxo de Login e Dashboard
    User -- "1. Login / Acessa Dashboard" --> FastAPI
    FastAPI -- "2. Autentica e busca Contas" --> Supabase
    FastAPI -- "3. Salva Sessão" --> Redis

    %% Fluxo do OTP
    User -- "4. Clica em 'Rastrear' (Soft Lock)" --> FastAPI
    FastAPI -- "Registra Lock de 15 min" --> Redis
    P360 -- "5. Dispara E-mail com OTP" --> SendGrid
    SendGrid -- "6. Webhook (E-mail bruto)" --> FastAPI
    FastAPI -- "7. Filtra OTP e salva" --> Redis
    User -. "8. Polling a cada 3s" .-> FastAPI
    FastAPI -- "Lê OTP" --> Redis

    %% Fluxo de Bloqueio Definitivo
    EAD -- "9. Webhook de Progresso" --> FastAPI
    FastAPI -- "10. Valida API Keys" --> Supabase
    FastAPI -- "11. Aplica Hard Lock (2h)" --> Redis
