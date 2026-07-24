# Deploy em produção — VM/VPS Ubuntu

O `deploy/install.sh` é responsável pelo deploy inteiro: pacotes do
sistema, usuário dedicado, firewall, banco de dados, `.env`, systemd,
Nginx, HTTPS (grátis, com ou sem domínio) e backup automático. Não há
nenhum passo manual — nem editar `nginx.conf`, nem os arquivos `.service`,
nem o `.env`. Se em algum momento você precisar editar algo à mão para a
instalação funcionar, é um bug do script, não uma etapa esperada.

**Recomendado apenas para Ubuntu 22.04 LTS ou 24.04 LTS.** Rodando em
outra distro (Debian, CentOS, etc.) o script avisa e pede confirmação
explícita antes de continuar — não é testado nem recomendado nelas.

---

## 1. Instalação — um único comando

Não precisa nem clonar o repositório antes: o próprio script faz isso.
Na VM/VPS nova, como root ou um usuário com sudo:

```bash
curl -fsSL https://raw.githubusercontent.com/Gerson-if/projeto_saida/main/deploy/install.sh -o install.sh
sudo bash install.sh
```

Isso abre um menu interativo. Para a instalação completa, ele pergunta
(com validação de cada resposta, então não dá pra digitar algo inválido
sem o script avisar e pedir de novo):

- Diretório de instalação, usuário de sistema, URL do repositório
  (todos têm um padrão sensato — só apertar Enter já funciona).
- **Como expor o sistema para os usuários** (veja a tabela abaixo).
- Banco de dados: SQLite (padrão, mais simples) ou MariaDB.
- Quantos workers do Gunicorn.
- Nome, CPF (ou identificador) e senha do primeiro administrador.
- Se quer configurar backup automático diário agora.

A partir daí é 100% automático: instala tudo que falta, cria o usuário
de sistema, clona o código, sobe o banco, gera o `.env` com uma
`SECRET_KEY` própria, registra os serviços systemd, configura o Nginx,
emite o certificado e roda um diagnóstico final — conferindo a cada
etapa se o serviço realmente subiu e está respondendo, não só se o
comando "deu certo" na aparência. Se algo falhar no meio, o script para
com uma mensagem clara em vez de seguir em frente com algo quebrado.

Já tem o projeto clonado em algum lugar? Funciona do mesmo jeito:
```bash
cd projeto_saida
sudo bash deploy/install.sh
```

### Pré-requisitos

- Uma VM/VPS Ubuntu com pelo menos 1 vCPU / 1 GB RAM.
- Acesso root ou sudo via SSH.
- Domínio: **opcional** (veja a tabela abaixo).
- **Único item fora do alcance do script:** se a VM estiver atrás de um
  firewall do provedor de nuvem (grupo de segurança AWS/GCP/Azure/
  Oracle/etc.), libere as portas 80 e 443 nele também — isso é
  configuração do provedor, fora da própria VM, e nenhum script rodando
  dentro da VM consegue alterar isso por você.

---

## 2. Domínio, IP ou VPS sem domínio — como decidir o HTTPS

O instalador pergunta isso no menu (ou aceita via `--https-mode` +
`--domain`, para pular a pergunta em automação):

| Situação | Opção no menu | O que acontece |
|---|---|---|
| Tenho um domínio apontando para a VM/VPS | 1 | Certificado real via Let's Encrypt, grátis |
| Não tenho domínio, mas quero HTTPS de verdade | 2 | Usa `SEU-IP.sslip.io` — resolve sozinho para o IP da VM, sem mexer em DNS, e ainda ganha certificado real do Let's Encrypt |
| Quero acessar só pelo IP da VM/VPS mesmo | 3 | Certificado autoassinado, com o SAN (Subject Alternative Name) já correto para IP — o navegador avisa "conexão não é segura" na primeira visita, é só aceitar o aviso uma vez |
| Ambiente de teste, sem HTTPS por enquanto | 4 | Só HTTP — não recomendado para produção |

Mudou de ideia depois? Troca sem reinstalar tudo:
```bash
# Passar a usar HTTPS autoassinado com o IP da VM
sudo bash deploy/install.sh --action ssl --https-mode selfsigned --domain 203.0.113.10

# Passar a usar Let's Encrypt de verdade quando conseguir um domínio
sudo bash deploy/install.sh --action ssl --https-mode letsencrypt --domain saida.exemplo.com.br --email voce@exemplo.com
```

---

## 3. Backup automático

```bash
sudo bash deploy/install.sh --action backup
```
Pergunta a retenção (dias) e o horário, e a partir daí roda sozinho
todo dia via cron do usuário de sistema: dump do MariaDB (ou cópia do
SQLite) + `app/static/uploads/` (logos, fotos, fundo do login)
compactados em `instance/backups/`, com os backups mais antigos que a
retenção escolhida apagados automaticamente. Para testar manualmente:
```bash
sudo -u projeto_saida bash /opt/projeto_saida/deploy/backup.sh
```

---

## 4. Atualizando o sistema — rotina segura, feita para não quebrar produção

```bash
sudo bash deploy/install.sh --action update
# atalho equivalente:
sudo bash deploy/update.sh
```

Esta é a única forma recomendada de atualizar uma instalação em
produção. Nessa ordem, o script:

1. **Trava contra atualização duplicada** — se já houver uma atualização
   em andamento nesta instalação (ex: alguém rodou o comando duas vezes
   sem querer), a segunda chamada para na hora em vez de disputar os
   mesmos arquivos.
2. **Confere a saúde atual antes de tocar em qualquer coisa.** Se o
   serviço já não estiver respondendo antes de começar, avisa que
   reverter não vai ajudar (o problema já existe) e pergunta se quer
   mesmo assim continuar, ou parar para investigar primeiro
   (`--action diagnostico`).
3. Confere se há alterações locais não commitadas na instalação (não
   deveria haver em produção) e pergunta antes de seguir se encontrar.
4. Roda `git fetch` e compara com a versão local — se já estiver
   atualizado, avisa e para por aí, sem mexer em nada.
5. **Faz backup do banco e do `.env` antes de qualquer mudança**, em
   `instance/backups/pre-update-<data_hora>/`.
6. Atualiza o código só por fast-forward (`git merge --ff-only`) — se
   houver divergência (alguém mexeu no checkout manualmente), para sem
   alterar nada em vez de criar um merge inesperado em produção.
7. Reinstala as dependências Python e aplica migrações de banco
   pendentes (`flask db upgrade`).
8. Reinicia o serviço e confere se ele **realmente** voltou a responder
   (não só se o processo systemd subiu, mas se `http://127.0.0.1:8000/`
   responde de verdade).
9. **Se qualquer passo de 6 a 8 falhar, reverte tudo sozinho:** código
   de volta ao commit anterior, banco restaurado do backup do passo 5,
   dependências da versão antiga reinstaladas, serviço reiniciado — e
   confere de novo se voltou a responder antes de avisar que a reversão
   deu certo. Só nesse ponto (reversão que também falhou) é que pede
   intervenção manual, com o comando exato para começar a investigar.

Em resumo: uma atualização só "vale" se, no fim, o sistema estiver
respondendo — caso contrário o script desfaz sozinho e devolve o estado
anterior, sem deixar produção no ar quebrada.

---

## 5. Comandos do dia a dia

| Ação | Comando |
|---|---|
| Instalação completa / menu | `sudo bash deploy/install.sh` |
| Atualizar com segurança | `sudo bash deploy/install.sh --action update` |
| Emitir/trocar HTTPS | `sudo bash deploy/install.sh --action ssl` |
| Configurar backup automático | `sudo bash deploy/install.sh --action backup` |
| Diagnóstico de saúde | `sudo bash deploy/install.sh --action diagnostico` |
| Ver status do serviço | `sudo systemctl status projeto-saida` |
| Reiniciar o serviço | `sudo systemctl restart projeto-saida` |
| Ver logs em tempo real | `journalctl -u projeto-saida -f` |
| Log da aplicação | `instance/logs/app.log` (rotativo, 5×1MB automático) |
| Criar outro admin | `flask create-admin "Nome" cpf senha` (dentro do venv, com `.env` carregado) |

Rodar qualquer ação de novo é seguro — o script detecta o que já existe
e não sobrescreve/duplica nada às cegas.

---

## Apêndice — como o script monta cada peça (referência, não é um passo a passo)

Esta seção é só para quem quer entender o que acontece por baixo dos
panos, adaptar algo mais avançado, ou comparar com uma instalação feita
à mão em outro projeto. **Não é necessário ler ou executar nada daqui
para colocar o sistema no ar** — é isso que a seção 1 já faz.

- **Pacotes do sistema:** Python 3, venv, Nginx, Certbot, ufw, cron, e
  (se você escolher MariaDB) `mariadb-server`/`mariadb-client`. Inclui
  também `libssl-dev`, `libffi-dev`, `python3-dev`, `zlib1g-dev`,
  `libjpeg-dev` — só usadas se o `pip` precisar compilar
  `cryptography`/`Pillow` por falta de uma wheel pronta para a
  arquitetura da VM.
- **Firewall (ufw):** libera só OpenSSH e Nginx Full (80/443). A porta
  do Gunicorn (8000) nunca é exposta — escuta só em `127.0.0.1`.
- **Usuário de sistema dedicado** (`projeto_saida` por padrão): sem
  shell de login, roda a aplicação com privilégios mínimos.
- **Banco de dados:** SQLite em `instance/` (dev/uso pequeno) ou
  MariaDB com banco e usuário dedicados criados na hora
  (`CREATE DATABASE` / `CREATE USER` com senha gerada aleatoriamente).
- **`.env` de produção:** gerado com `SECRET_KEY` própria da instalação
  (nunca a string de exemplo do repositório), `DATABASE_URL`,
  `BEHIND_PROXY=true` e a config de workers/agendador coerente com o
  número de workers escolhido — `ProductionConfig.validate()`
  (`config.py`) recusa subir sem esses valores explícitos, de propósito.
- **systemd:** `deploy/projeto-saida.service` (Gunicorn) sempre; com
  mais de 1 worker, também `deploy/projeto-saida-status.service` +
  `.timer` (job de atualização de status fora dos workers web, evitando
  rodar duplicado — ver comentários em `app/__init__.py::_init_scheduler`).
- **Nginx:** `deploy/nginx.conf` como template, com `server_name` e
  caminhos substituídos para o domínio/diretório escolhidos.
- **HTTPS:** Certbot (Let's Encrypt) ou certificado autoassinado com SAN
  correto (IP ou domínio), conforme a seção 2.
- **Backup:** `deploy/backup.sh` gerado sob medida (MariaDB ou SQLite) +
  cron do usuário de sistema, conforme a seção 3.

Se mesmo assim você quiser montar tudo isso manualmente (por exemplo,
para adaptar a um provedor com particularidades bem específicas), o
próprio `deploy/install.sh` é a documentação mais precisa: é um script
bash comum, comentado, sem mágica — dá pra ler de cima a baixo e copiar
só os trechos relevantes.
