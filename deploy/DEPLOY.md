# Deploy em produção — VM Linux (Ubuntu/Debian)

Guia passo a passo para subir o sistema numa VM Linux "do zero", com
Gunicorn + Nginx + MariaDB + HTTPS (Let's Encrypt) + systemd.

Testado mentalmente para Ubuntu 22.04/24.04 e Debian 12. Em CentOS/RHEL/
Rocky troque `apt` por `dnf` e os nomes de alguns pacotes.

---

## 0. Antes de começar

- Uma VM com pelo menos 1 vCPU / 1GB RAM (o app é leve).
- Um domínio (ou subdomínio) apontando o DNS para o IP da VM — necessário
  para o HTTPS com Let's Encrypt.
- Acesso root/sudo via SSH.

---

## 1. Pacotes do sistema

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git \
    nginx mariadb-server mariadb-client libmariadb-dev \
    build-essential pkg-config certbot python3-certbot-nginx ufw
```

## 2. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'   # libera 80 e 443
sudo ufw enable
```
A porta do Gunicorn (8000) **não** é liberada — ela só escuta em
`127.0.0.1`, acessível apenas pelo Nginx na mesma máquina.

## 3. Usuário de sistema dedicado

Rodar a aplicação com um usuário próprio (sem shell de login, sem
privilégios) limita o estrago em caso de falha de segurança.

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin projeto_saida
sudo mkdir -p /opt/projeto_saida
sudo chown projeto_saida:projeto_saida /opt/projeto_saida
```

## 4. Banco de dados (MariaDB)

O `ProductionConfig` (config.py) exige `DATABASE_URL` — SQLite é só para
desenvolvimento. Crie o banco e um usuário dedicado:

```bash
sudo mysql -u root <<'SQL'
CREATE DATABASE projeto_saida CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'projeto_saida'@'localhost' IDENTIFIED BY 'TROQUE-ESTA-SENHA';
GRANT ALL PRIVILEGES ON projeto_saida.* TO 'projeto_saida'@'localhost';
FLUSH PRIVILEGES;
SQL
```

## 5. Código da aplicação

```bash
sudo -u projeto_saida -H bash <<'EOF'
cd /opt/projeto_saida
git clone https://github.com/Gerson-if/projeto_saida.git
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
EOF
```
(Se você não usa git para distribuir o código, envie os arquivos via
`rsync`/`scp` para `/opt/projeto_saida` como o usuário `projeto_saida`.)

## 6. Variáveis de ambiente (`.env`)

```bash
sudo -u projeto_saida cp /opt/projeto_saida/.env.example /opt/projeto_saida/.env
sudo -u projeto_saida nano /opt/projeto_saida/.env
```

Preencha pelo menos:

```dotenv
FLASK_ENV=production

# Gere com: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<chave-gerada-aleatoria>

DATABASE_URL=mysql+pymysql://projeto_saida:TROQUE-ESTA-SENHA@localhost/projeto_saida

# Atrás do Nginx (padrão já é true, mas deixe explícito)
BEHIND_PROXY=true

# Ver seção 9 sobre workers antes de decidir isto:
SCHEDULER_ENABLED=true
```

`ProductionConfig.validate()` recusa subir sem `SECRET_KEY` e
`DATABASE_URL` explícitos — é intencional, evita subir em produção com
configuração incompleta por engano.

## 7. Inicializar o banco

```bash
sudo -u projeto_saida -H bash <<'EOF'
cd /opt/projeto_saida
source venv/bin/activate
export FLASK_ENV=production
export $(grep -v '^#' .env | xargs)   # carrega o .env nesta sessão
flask init-db
flask create-admin "Administrador" admin "SENHA-FORTE-AQUI"
EOF
```

## 8. Gunicorn + systemd

Os arquivos prontos estão em `deploy/`:

```bash
sudo cp deploy/projeto-saida.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now projeto-saida
sudo systemctl status projeto-saida
```

Revise `/etc/systemd/system/projeto-saida.service` se o caminho do
projeto ou o usuário forem diferentes de `/opt/projeto_saida` /
`projeto_saida`.

Logs em tempo real:
```bash
journalctl -u projeto-saida -f
```

## 9. Um worker ou vários? (importante)

O app tem um agendador interno (`APScheduler`) que atualiza o status das
saídas periodicamente. Ele roda **dentro do processo do Gunicorn** — ou
seja, com N workers, o job roda N vezes em paralelo (redundante, mas não
corrompe dados; é apenas ineficiente).

- **VM pequena / poucos usuários simultâneos (caso comum):** deixe
  `WEB_CONCURRENCY=1` (padrão em `deploy/gunicorn_conf.py`, que já usa
  threads para lidar com várias requisições ao mesmo tempo) e
  `SCHEDULER_ENABLED=true`. Não precisa de mais nada.

- **Vai escalar para vários workers/processos:** defina no `.env`
  `WEB_CONCURRENCY=4` (ajuste ao número de vCPUs) e
  `SCHEDULER_ENABLED=false` — e ative o timer systemd que faz o mesmo
  trabalho fora dos workers web:
  ```bash
  sudo cp deploy/projeto-saida-status.service /etc/systemd/system/
  sudo cp deploy/projeto-saida-status.timer   /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now projeto-saida-status.timer
  ```

## 10. Nginx + HTTPS

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/projeto-saida
sudo nano /etc/nginx/sites-available/projeto-saida   # ajuste server_name e caminhos
sudo ln -s /etc/nginx/sites-available/projeto-saida /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

HTTPS gratuito com Let's Encrypt (o Certbot edita o nginx.conf sozinho e
configura renovação automática via timer systemd):
```bash
sudo certbot --nginx -d seu-dominio.com.br
```

Teste a renovação automática (não renova de verdade, só simula):
```bash
sudo certbot renew --dry-run
```

## 11. Checklist final

```bash
sudo -u projeto_saida -H bash -c "cd /opt/projeto_saida && source venv/bin/activate && flask diagnosticar"
```
Esse comando (já existente no projeto) confere `SECRET_KEY`, cookies de
sessão segura e o banco de dados — rode-o sempre depois de qualquer
mudança de configuração.

Confirme também:
- [ ] `https://seu-dominio.com.br` carrega e o cadeado aparece.
- [ ] Login funciona e o cookie de sessão só é enviado via HTTPS
      (`SESSION_COOKIE_SECURE=true`, já é o padrão em `ProductionConfig`).
- [ ] Upload de logo/imagem/vídeo de fundo do login funciona
      (confira permissão de escrita em `app/static/uploads/`).
- [ ] O tema escuro/verde-oliva troca corretamente pelo ícone de paleta
      no topo, sem texto "sumindo".

## 12. Backups

MariaDB — dump diário simples via cron do usuário `projeto_saida`:
```bash
sudo -u projeto_saida crontab -e
```
```cron
0 3 * * * mysqldump -u projeto_saida -p'TROQUE-ESTA-SENHA' projeto_saida | gzip > /opt/projeto_saida/instance/backups/db-$(date +\%F).sql.gz
```
Crie a pasta antes: `sudo -u projeto_saida mkdir -p /opt/projeto_saida/instance/backups`.
Lembre de também copiar `app/static/uploads/` (logos, fotos, fundo do
login) para o backup — não é só o banco que importa.

## 13. Atualizando o sistema (deploy de uma nova versão)

```bash
sudo -u projeto_saida -H bash <<'EOF'
cd /opt/projeto_saida
git pull
source venv/bin/activate
pip install -r requirements.txt
flask db upgrade   # se houver migrações pendentes
EOF
sudo systemctl restart projeto-saida
```

## 14. Logs da aplicação

Além do `journalctl -u projeto-saida`, a aplicação grava seu próprio log
rotativo em `instance/logs/app.log` (configurado em
`app/__init__.py::_init_logging`, já limitado a 5×1MB automaticamente —
não precisa de logrotate extra para esse arquivo específico).

---

### Referência rápida de comandos úteis

| Ação | Comando |
|---|---|
| Ver status do app | `sudo systemctl status projeto-saida` |
| Reiniciar o app | `sudo systemctl restart projeto-saida` |
| Ver logs em tempo real | `journalctl -u projeto-saida -f` |
| Testar config do Nginx | `sudo nginx -t` |
| Forçar atualização de status manual | `flask atualizar-status` |
| Diagnóstico de config/segurança | `flask diagnosticar` |
| Criar novo admin | `flask create-admin "Nome" cpf senha` |
