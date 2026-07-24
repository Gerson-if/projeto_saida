# Sistema de Controle de Saídas de Militares

Sistema web desenvolvido em **Flask**, utilizando **SQLAlchemy**, **MariaDB** e **Bootstrap 5**, com foco na gestão e controle de saídas de militares de forma simples, segura e organizada.

O projeto foi estruturado seguindo boas práticas de desenvolvimento, utilizando arquitetura modular com **Blueprints**, separação entre modelos, rotas e serviços, facilitando a manutenção e futuras expansões.

Sistema web para registro e controle de saídas de militares, com atualização automática de status, dashboard analítica e suporte a MariaDB/MySQL ou SQLite.

**Como colocar para rodar:**
- **Só para testar/desenvolver na sua máquina?** Veja [Desenvolvimento local](#desenvolvimento-local) — `bash setup_dev.sh` cuida de tudo (venv, dependências, assets estáticos, banco SQLite, dados de exemplo).
- **Vai colocar em produção numa VM/VPS?** Veja [Deploy em produção](#deploy-em-produção) — `sudo bash deploy/install.sh` cuida de tudo (pacotes do sistema, banco, HTTPS grátis, backup automático, systemd/Nginx).

Nenhum dos dois caminhos exige editar arquivo de configuração na mão. O
restante deste README documenta o funcionamento do sistema; os detalhes de
cada script estão comentados nos próprios arquivos e em `deploy/DEPLOY.md`.

---

## Funcionalidades

- **Status automático**: o sistema atualiza os status `Agendada → Em Trânsito → Retornado` com base nas datas, sem necessidade de intervenção do administrador.
- **Dashboard analítica**: indicadores de militares presentes, em trânsito, retornados no dia, próximas saídas e gráfico de distribuição de status.
- **Motivos sugeridos**: o formulário de saída oferece opções pré-definidas com campo livre (até 300 caracteres).
- **Identidade visual configurável**: nome do sistema, cores, logo, brasão e favicon configuráveis pelo painel admin.
- **Favicon dinâmico**: favicon exibido na aba do navegador, definido pelo admin.
- **Relatórios PDF**: por período ou data exata.
- **Assets estáticos locais**: Bootstrap, ícones, Chart.js e a fonte Inter
  são compilados localmente em `app/static/vendor/` (por
  `scripts/build_static_assets.sh`, chamado automaticamente por
  `setup_dev.sh` e por `deploy/install.sh`) — a aplicação não depende de
  nenhum CDN externo para carregar, o que deixa o carregamento das
  páginas mais rápido e continua funcionando mesmo sem internet depois de
  instalada.

---
## Atualização — Versão 3

Esta versão traz melhorias significativas na organização e usabilidade do sistema, incluindo gerenciamento de **subunidades**, controle de **cancelamento com histórico preservado**, novas regras de **edição e finalização automática das saídas**, além de uma **dashboard mais completa** com gráficos e informações aprimoradas.

Também foram adicionadas melhorias na interface, como **sidebar recolhível**, correções de **favicon**, otimizações para **impressão de relatórios** e ajustes gerais de estabilidade e experiência do usuário.

Além disso, o processo de instalação foi atualizado com orientações para configuração do **MariaDB**, criação do banco de dados e validação da conexão antes da inicialização da aplicação, tornando o ambiente de desenvolvimento mais simples e confiável.


## Requisitos

- Python 3.11+
- SQLite (padrão, já incluso no Python — ótimo para dev e para instalações pequenas) **ou** MariaDB 10.6+ / MySQL 8+ (recomendado se esperar mais carga/usuários simultâneos, em dev ou produção)
- pip

---

## Desenvolvimento local

```bash
git clone https://github.com/Gerson-if/projeto_saida.git
cd projeto_saida
python3 -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

bash setup_dev.sh
```

O `setup_dev.sh` faz tudo: instala as dependências, compila os assets
estáticos localmente (Bootstrap, ícones, Chart.js, fonte Inter — veja
[Funcionalidades](#funcionalidades)), cria o `.env` a partir do
`.env.example`, inicializa o banco SQLite e popula com dados de exemplo.
Ao final, execute:

```bash
python run.py
```

Acesse em `http://localhost:5000` — admin padrão: `cpf=admin` / `senha=admin123`.

<details>
<summary>Passo a passo manual, se preferir não usar o setup_dev.sh</summary>

```bash
pip install -r requirements.txt
bash scripts/build_static_assets.sh   # baixa Bootstrap/ícones/Chart.js/Inter localmente
cp .env.example .env                  # edite se quiser mudar algo além do padrão (SQLite)
flask init-db
flask create-admin "Nome Completo" cpf_sem_pontos senha123
python run.py
```

**Para usar MariaDB em vez de SQLite em dev:** crie o banco antes e
aponte `DATABASE_URL` no `.env`:
```sql
CREATE DATABASE sistema_saida CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'seu_usuario'@'localhost' IDENTIFIED BY 'sua_senha';
GRANT ALL ON sistema_saida.* TO 'seu_usuario'@'localhost';
```
```dotenv
DATABASE_URL=mysql+pymysql://seu_usuario:sua_senha@localhost/sistema_saida
```
</details>

---

## Deploy em produção

Um único comando, numa VM/VPS Ubuntu — não precisa nem clonar o repositório
antes, o próprio script cuida disso:

```bash
curl -fsSL https://raw.githubusercontent.com/Gerson-if/projeto_saida/main/deploy/install.sh -o install.sh
sudo bash install.sh
```

Abre um menu guiado que cuida da instalação inteira: pacotes do sistema,
usuário dedicado, firewall, banco de dados (SQLite ou MariaDB), Gunicorn +
systemd, Nginx, **HTTPS grátis** (com domínio próprio via Let's Encrypt, sem
domínio via `SEU-IP.sslip.io`, ou autoassinado usando o IP da VM
diretamente) e **backup automático diário**. Também compila os assets
estáticos localmente, então a aplicação não depende de nenhum CDN externo
depois de instalada. Para atualizar depois, com backup e reversão
automáticos se algo falhar:

```bash
sudo bash deploy/install.sh --action update
```

Detalhes completos, todas as opções e o que cada etapa faz por baixo dos
panos: **[deploy/DEPLOY.md](deploy/DEPLOY.md)**.

---

## Comandos CLI

| Comando | Descrição |
|---|---|
| `flask init-db` | Cria tabelas e configurações padrão |
| `flask create-admin NOME CPF SENHA` | Cria um administrador |
| `flask seed` | Insere dados de exemplo para testes |
| `flask atualizar-status` | Força atualização manual de todos os status |
| `flask diagnosticar` | Verifica config. de sessão/segurança e do banco (debug) |
| `flask db migrate -m "msg"` | Gera migração após alterar modelos |
| `flask db upgrade` | Aplica migrações pendentes |
| `bash scripts/build_static_assets.sh` | (Re)compila os assets estáticos locais (Bootstrap, ícones, Chart.js, Inter) |

Em produção (instalação feita por `deploy/install.sh`), some comandos de
manutenção são chamados pelo próprio instalador:

| Comando | Descrição |
|---|---|
| `sudo bash deploy/install.sh --action update` | Atualização segura, com backup e reversão automáticos |
| `sudo bash deploy/install.sh --action ssl` | Emite/troca o certificado HTTPS |
| `sudo bash deploy/install.sh --action backup` | Configura backup automático diário |
| `sudo bash deploy/install.sh --action diagnostico` | Diagnóstico de saúde da instalação |

---

## Atualização — Segurança, sessão e concorrência

Principais mudanças:

- **SECRET_KEY própria por instalação**: se `SECRET_KEY` não estiver no
  `.env`, o sistema gera uma chave aleatória e a guarda em
  `instance/secret_key` (nunca versionada). Antes, o projeto usava uma
  string fixa no código-fonte como padrão — qualquer pessoa que lesse o
  repositório conhecia essa chave e poderia, teoricamente, forjar um cookie
  de sessão válido para qualquer usuário sem fazer login. Em produção, a
  `SECRET_KEY` continua sendo obrigatória via variável de ambiente.
- **Cookies de sessão explicitamente protegidos** (`HttpOnly`, `SameSite=Lax`,
  `Secure` em produção, nome de cookie próprio, expiração configurável) e
  `session_protection = "strong"` no Flask-Login, que invalida a sessão se o
  IP/navegador mudar no meio do caminho.
  Toda página autenticada agora responde com `Cache-Control: no-store`, para
  que nenhum proxy/navegador guarde em cache uma página com dados de sessão.
- **Bloqueio por tentativas de login** (`LOGIN_MAX_TENTATIVAS`,
  `LOGIN_BLOQUEIO_MINUTOS` no `.env`), com contador atômico no banco — não
  perde incrementos mesmo com tentativas simultâneas.
- **SQLite em modo WAL + busy_timeout**: reduz drasticamente os erros de
  "database is locked" quando vários usuários (ou o job automático de
  status) gravam no banco ao mesmo tempo.
- **`commit_seguro()`** (`app/db_utils.py`): substitui os antigos
  `try/except Exception: db.session.rollback()` espalhados pelas rotas.
  Agora, qualquer falha real ao salvar é **logada** em
  `instance/logs/app.log` (antes era descartada silenciosamente), erros de
  lock transitório são reexecutados automaticamente, e conflitos de dados
  duplicados mostram uma mensagem específica.

---

## Atualização — Deploy automatizado, HTTPS flexível e assets locais

O processo de instalação/deploy e a interface deixaram de depender de
configuração manual ou de serviços externos:

- **Instalador guiado (`deploy/install.sh`)**: um único comando cuida da
  instalação de produção inteira numa VM/VPS Ubuntu — pacotes do sistema,
  usuário dedicado, firewall, banco de dados, systemd, Nginx, HTTPS e
  backup, com um menu interativo, validação de cada resposta digitada e
  checagens automáticas (rede, disco, portas, serviço realmente
  respondendo) antes e depois de cada etapa. Veja
  [Deploy em produção](#deploy-em-produção) e `deploy/DEPLOY.md`.
- **HTTPS sem exigir domínio**: além de domínio próprio (Let's Encrypt),
  agora dá pra expor o sistema só pelo IP da VM/VPS — com certificado
  autoassinado (SAN correto, não só CN) ou, sem abrir mão de um
  certificado real, usando `SEU-IP.sslip.io`.
- **Atualização segura**: `deploy/install.sh --action update` faz backup
  do banco antes de qualquer mudança, atualiza só por fast-forward, e
  **reverte tudo sozinho** (código, banco, dependências) se a migração,
  a instalação de dependências ou o health-check pós-restart falharem —
  pensado para nunca deixar a produção parada num estado quebrado.
- **Backup automático diário**: `deploy/install.sh --action backup`
  configura dump do banco + `app/static/uploads/` via cron, com retenção
  configurável.
- **Assets estáticos locais**: Bootstrap, Bootstrap Icons, Chart.js e a
  fonte Inter deixaram de ser carregados de CDN externo
  (`cdn.jsdelivr.net`, `fonts.googleapis.com`) e passaram a ser
  compilados localmente em `app/static/vendor/` por
  `scripts/build_static_assets.sh` — chamado automaticamente por
  `setup_dev.sh` e por `deploy/install.sh`. Páginas carregam mais rápido
  (sem handshake TLS extra para outros domínios) e a aplicação continua
  funcionando mesmo se a VM perder acesso à internet depois de instalada.

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
│   ├── static/         # CSS, JS, uploads, relatórios, vendor/ (gerado, não versionado)
│   ├── context_processors.py
│   ├── commands.py
│   └── __init__.py     # Application factory + scheduler
├── scripts/
│   └── build_static_assets.sh  # Compila Bootstrap/ícones/Chart.js/Inter localmente
├── deploy/              # Instalador guiado, systemd, Nginx (veja deploy/DEPLOY.md)
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

**Página sem estilo / ícones não aparecem / erro 404 em `/static/vendor/...`**
- Os assets estáticos (Bootstrap, ícones, Chart.js, fonte Inter) precisam
  ser compilados uma vez antes de rodar a aplicação: `bash
  scripts/build_static_assets.sh` (já é feito automaticamente por
  `setup_dev.sh` e por `deploy/install.sh` — só costuma faltar se você
  rodou a aplicação pulando esses scripts). Precisa de acesso a
  `registry.npmjs.org` na hora de compilar; depois disso, a aplicação
  não depende mais de internet para servir sua própria interface.

**Instalação em produção com problema**
- Rode `sudo bash deploy/install.sh --action diagnostico` — confere
  configuração da aplicação, serviço systemd, Nginx, certificados e
  espaço em disco de uma vez. Veja também `deploy/DEPLOY.md`.
