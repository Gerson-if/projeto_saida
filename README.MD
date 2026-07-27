# Sistema de Controle de Saídas — v2

Sistema web para registro e controle de saídas de militares, com atualização automática de status, dashboard analítica e suporte a MariaDB/MySQL ou SQLite.

---

## Funcionalidades

- **Status automático**: o sistema atualiza os status `Agendada → Em Trânsito → Retornado` com base nas datas, sem necessidade de intervenção do administrador.
- **Dashboard analítica**: indicadores de militares presentes, em trânsito, retornados no dia, próximas saídas e gráfico de distribuição de status.
- **Motivos sugeridos**: o formulário de saída oferece opções pré-definidas com campo livre (até 300 caracteres).
- **Identidade visual configurável**: nome do sistema, cores, logo, brasão e favicon configuráveis pelo painel admin.
- **Favicon dinâmico**: favicon exibido na aba do navegador, definido pelo admin.
- **Relatórios PDF**: por período ou data exata.

---

## Requisitos

- Python 3.11+
- MariaDB 10.6+ / MySQL 8+ (produção) **ou** SQLite (desenvolvimento)
- pip

---

## Instalação

### 1. Clone e configure o ambiente

```bash
git clone <repo>
cd sistema_saida
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com suas configurações (SECRET_KEY e DATABASE_URL)
```

**Para MariaDB**, crie o banco antes:
```sql
CREATE DATABASE sistema_saida CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'seu_usuario'@'localhost' IDENTIFIED BY 'sua_senha';
GRANT ALL ON sistema_saida.* TO 'seu_usuario'@'localhost';
```

### 3. Inicialize o banco

```bash
flask init-db
```

### 4. Crie o primeiro administrador

```bash
flask create-admin "Nome Completo" cpf_sem_pontos senha123
```

### 5. Execute

**Desenvolvimento:**
```bash
python run.py
```

**Produção (Gunicorn):**
```bash
pip install gunicorn
gunicorn "run:app" -w 4 -b 0.0.0.0:8000
```

---

## Comandos CLI

| Comando | Descrição |
|---|---|
| `flask init-db` | Cria tabelas e configurações padrão |
| `flask create-admin NOME CPF SENHA` | Cria um administrador |
| `flask seed` | Insere dados de exemplo para testes |
| `flask atualizar-status` | Força atualização manual de todos os status |
| `flask db migrate -m "msg"` | Gera migração após alterar modelos |
| `flask db upgrade` | Aplica migrações pendentes |

---

## Status das Saídas

O fluxo de status é **totalmente automático**:

```
Agendada → Em Trânsito → Retornado
```

- **Agendada**: saída registrada com data futura.
- **Em Trânsito**: data de saída chegou (job roda a cada 10 min).
- **Retornado**: data de retorno expirou (job automático).
- **Cancelado**: cancelado manualmente pelo usuário antes da saída.

O job pode ser configurado via `SCHEDULER_STATUS_INTERVAL_MINUTES` no `.env`.
Para forçar manualmente: `flask atualizar-status`.

---

## Estrutura do Projeto

```
sistema_saida/
├── app/
│   ├── models/         # Modelos SQLAlchemy (Usuario, Registro, ConfigSistema)
│   ├── routes/         # Blueprints: auth, admin, user, reports
│   ├── templates/      # Templates Jinja2 (base.html, admin/, user/, reports/)
│   ├── static/         # CSS, JS, uploads, relatórios
│   ├── context_processors.py
│   ├── commands.py
│   └── __init__.py     # Application factory + scheduler
├── config.py           # Configurações por ambiente
├── run.py              # Ponto de entrada
├── requirements.txt
└── .env.example
```

---

## Solução de Problemas

**Erro de conexão com MariaDB**
- Certifique-se de que `pymysql` e `cryptography` estão instalados.
- Verifique se `DATABASE_URL` usa `mysql+pymysql://`.

**Status não atualiza automaticamente**
- O scheduler APScheduler deve estar instalado (`pip install APScheduler`).
- Para ambientes sem APScheduler, use `flask atualizar-status` via cron.

**Banco SQLite não encontrado**
- Execute `flask init-db` para criar as tabelas.
- O arquivo é criado em `instance/sistema_saida.db`.
