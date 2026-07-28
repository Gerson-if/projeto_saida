# Sistema de Controle de Saídas de Militares

Sistema web desenvolvido em **Flask**, utilizando **SQLAlchemy**, **MariaDB** e **Bootstrap 5**, com foco na gestão e controle de saídas de militares de forma simples, segura e organizada.

O projeto foi estruturado seguindo boas práticas de desenvolvimento, utilizando arquitetura modular com **Blueprints**, separação entre modelos, rotas e serviços, facilitando a manutenção e futuras expansões.

## Antes de iniciar

Antes de executar a aplicação, é importante realizar corretamente a configuração do ambiente.

A sequência recomendada de instalação é:

1. Clonar o projeto.
2. Criar e ativar o ambiente virtual (`venv`).
3. Instalar as dependências do projeto.
4. Instalar e iniciar o serviço do **MariaDB**.
5. Criar o banco de dados da aplicação conforme informado neste documento.
6. Configurar corretamente o arquivo `.env` com as credenciais de acesso ao banco.
7. Verificar se a conexão com o MariaDB está funcionando e confirmar a porta utilizada pelo servidor (normalmente **3306**).
8. Executar os comandos de inicialização do banco de dados.
9. Iniciar a aplicação.

> **Importante:** O banco de dados deve existir antes da execução dos comandos `flask init-db` ou `flask db upgrade`. Caso contrário, ocorrerá erro de conexão informando que o banco de dados não foi encontrado.


Após concluir essas etapas, siga as instruções de instalação e execução descritas nas próximas seções deste README.


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
## Atualização — Versão 3

Esta versão traz melhorias significativas na organização e usabilidade do sistema, incluindo gerenciamento de **subunidades**, controle de **cancelamento com histórico preservado**, novas regras de **edição e finalização automática das saídas**, além de uma **dashboard mais completa** com gráficos e informações aprimoradas.

Também foram adicionadas melhorias na interface, como **sidebar recolhível**, correções de **favicon**, otimizações para **impressão de relatórios** e ajustes gerais de estabilidade e experiência do usuário.

Além disso, o processo de instalação foi atualizado com orientações para configuração do **MariaDB**, criação do banco de dados e validação da conexão antes da inicialização da aplicação, tornando o ambiente de desenvolvimento mais simples e confiável.


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
python -m pip install -r requirements.txt # executar caso nao encontre Flask
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com suas configurações (SECRET_KEY e DATABASE_URL)linux
```

```bash
copy .env.example .env
# Edite .env com suas configurações (SECRET_KEY e DATABASE_URL)windowns
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
