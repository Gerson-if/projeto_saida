"""
commands.py — Comandos CLI Flask para setup e manutenção.

Comandos disponíveis:
  flask init-db          Cria tabelas e insere configurações padrão
  flask create-admin     Cria um usuário administrador
  flask seed             Popula o banco com dados de exemplo
  flask atualizar-status Força atualização manual de status (útil para debug)
"""

import random
from datetime import datetime, timedelta

import click
from flask.cli import with_appcontext

from app import db
from app.models import (
    ConfigSistema, MotivoCancelamento, PostoGraduacao, Registro,
    StatusSaida, Subunidade, TipoUsuario, Usuario,
)


def register_commands(app) -> None:

    # ── init-db ────────────────────────────────────────────────────────────

    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        """Cria as tabelas e popula configurações padrão."""
        db.create_all()

        defaults = [
            ("nome_sistema",  "Sistema de Controle de Saídas",                  "Nome exibido no sistema"),
            ("subtitulo",     "Use os últimos 10 dígitos do CPF como login",    "Dica no login"),
            ("organizacao",   "Organização Militar",                             "Nome da organização"),
            ("rodape",        "© Sistema de Controle de Saídas — Gerado automaticamente", "Rodapé PDF"),
            ("cor_primaria",  "#1a3a5c",                                         "Cor primária"),
            ("cor_secundaria","#2980b9",                                         "Cor de destaque"),
            ("dica_1", "Verifique documentos e comunicação antes de sair.", "Dica de viagem segura 1"),
            ("dica_2", "Mantenha contato com a unidade durante a viagem.", "Dica de viagem segura 2"),
            ("dica_3", "Respeite os horários de retorno estabelecidos.", "Dica de viagem segura 3"),
            ("dica_4", "Em caso de imprevisto, comunique imediatamente a unidade.", "Dica de viagem segura 4"),
            ("postos_habilitados", "0", "Exibe o campo Posto/Graduação no cadastro de usuários (0=desligado, 1=ligado)"),
        ]
        for chave, valor, desc in defaults:
            if not ConfigSistema.query.filter_by(chave=chave).first():
                db.session.add(ConfigSistema(chave=chave, valor=valor, descricao=desc))

        # Motivos de cancelamento padrão
        motivos_padrao = [
            ("Desistência pessoal", 1),
            ("Problema de saúde", 2),
            ("Serviço imprevisto na unidade", 3),
            ("Problema no transporte", 4),
            ("Outros", 99),
        ]
        for texto, ordem in motivos_padrao:
            if not MotivoCancelamento.query.filter_by(texto=texto).first():
                db.session.add(MotivoCancelamento(texto=texto, ativo=True, ordem=ordem))

        db.session.commit()
        click.echo("✅ Banco de dados inicializado com configurações padrão.")

    # ── create-admin ───────────────────────────────────────────────────────

    @app.cli.command("create-admin")
    @click.argument("nome")
    @click.argument("cpf")
    @click.argument("senha")
    @with_appcontext
    def create_admin(nome, cpf, senha):
        """Cria um usuário administrador.\n\nUso: flask create-admin NOME CPF SENHA"""
        from app.validators import validar_nome, validar_cpf_ou_identificacao

        nome_limpo, erros_nome = validar_nome(nome, campo="nome")
        cpf_limpo, erros_cpf = validar_cpf_ou_identificacao(cpf)
        erros = [*erros_nome, *erros_cpf]

        if not senha or len(senha) < 4:
            erros.append("A senha deve ter no mínimo 4 caracteres.")
        if len(senha) > 72:
            erros.append("A senha deve ter no máximo 72 caracteres.")

        if erros:
            for e in erros:
                click.echo(f"❌ {e}")
            return

        if Usuario.query.filter_by(cpf=cpf_limpo).first():
            click.echo(f"❌ Já existe um usuário com CPF {cpf_limpo}.")
            return
        admin = Usuario(nome=nome_limpo, cpf=cpf_limpo, tipo=TipoUsuario.ADMIN, ativo=True)
        admin.set_senha(senha)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"✅ Admin '{nome_limpo}' criado com sucesso! CPF: {cpf_limpo}")

    # ── seed ───────────────────────────────────────────────────────────────

    @app.cli.command("seed")
    @with_appcontext
    def seed():
        """Popula o banco com dados de exemplo para testes."""
        # Admin padrão
        if not Usuario.query.filter_by(cpf="admin").first():
            admin = Usuario(nome="Super Admin", cpf="admin", tipo=TipoUsuario.ADMIN, ativo=True)
            admin.set_senha("admin123")
            db.session.add(admin)
            click.echo("  → Admin padrão criado (cpf: admin / senha: admin123)")

        # Usuários de teste
        usuarios_teste = [
            ("João Silva",      "12345678901"),
            ("Maria Oliveira",  "98765432100"),
            ("Carlos Souza",    "11122233344"),
            ("Ana Ferreira",    "55566677788"),
        ]
        usuarios_criados = []
        for nome, cpf in usuarios_teste:
            if not Usuario.query.filter_by(cpf=cpf).first():
                u = Usuario(nome=nome, cpf=cpf, tipo=TipoUsuario.USUARIO, ativo=True)
                u.set_senha("123456")
                db.session.add(u)
                usuarios_criados.append((cpf,))

        db.session.flush()

        locais = [
            "Campo Grande/MS", "São Paulo/SP", "Brasília/DF",
            "Rio de Janeiro/RJ", "Cuiabá/MT",
        ]
        motivos = [
            "Férias anuais", "Licença médica / Tratamento de saúde",
            "Visita familiar", "Curso de capacitação", "Missão oficial",
        ]

        for (cpf,) in usuarios_criados:
            for _ in range(random.randint(2, 4)):
                dias_offset = random.randint(-15, 20)
                data_saida  = datetime.now() + timedelta(days=dias_offset)
                data_retorno = data_saida + timedelta(days=random.randint(2, 15))

                # Determina status realista com base nas datas
                hoje = datetime.now().date()
                if data_saida.date() > hoje:
                    status = StatusSaida.AGENDADA
                elif data_retorno.date() < hoje:
                    status = StatusSaida.RETORNADO
                else:
                    status = StatusSaida.EM_TRANSITO

                registro = Registro(
                    cpf_usuario=cpf,
                    local=random.choice(locais),
                    motivo=random.choice(motivos),
                    data_saida=data_saida,
                    data_retorno=data_retorno,
                    telefone_contato=f"(67) 9{random.randint(1000,9999)}-{random.randint(1000,9999)}",
                    endereco_destino="Rua Exemplo, 123",
                    status=status,
                    status_atualizado_em=datetime.utcnow(),
                )
                db.session.add(registro)

        # Subunidades padrão
        subunidades_padrao = [
            ("1º Batalhão de Obras", "1ºBO"),
            ("2ª Bateria de Artilharia", "2ªBIA"),
            ("Batalhão de Comando", "BC"),
            ("Companhia de Saúde", "CSau"),
        ]
        for nome, sigla in subunidades_padrao:
            if not Subunidade.query.filter_by(nome=nome).first():
                db.session.add(Subunidade(nome=nome, sigla=sigla))
        db.session.flush()

        # Vincular usuários às subunidades
        subs = Subunidade.query.all()
        for i, u in enumerate(Usuario.query.filter_by(tipo=TipoUsuario.USUARIO).all()):
            u.subunidade_id = subs[i % len(subs)].id if subs else None

        # Postos/Graduações padrão (nível maior = mais alto na hierarquia)
        postos_padrao = [
            ("Soldado", "SD", 1),
            ("Cabo", "CB", 2),
            ("3º Sargento", "3ºSGT", 3),
            ("2º Sargento", "2ºSGT", 4),
            ("1º Sargento", "1ºSGT", 5),
            ("Subtenente", "ST", 6),
            ("2º Tenente", "2ºTEN", 7),
            ("1º Tenente", "1ºTEN", 8),
            ("Capitão", "CAP", 9),
        ]
        for nome, sigla, nivel in postos_padrao:
            if not PostoGraduacao.query.filter_by(nome=nome).first():
                db.session.add(PostoGraduacao(nome=nome, sigla=sigla, nivel=nivel))
        db.session.flush()

        # Vincular usuários de teste aos postos/graduações
        postos = PostoGraduacao.query.order_by(PostoGraduacao.nivel).all()
        for i, u in enumerate(Usuario.query.filter_by(tipo=TipoUsuario.USUARIO).all()):
            u.posto_graduacao_id = postos[i % len(postos)].id if postos else None

        db.session.commit()
        click.echo("✅ Dados de exemplo inseridos com sucesso!")

    # ── atualizar-status ───────────────────────────────────────────────────

    @app.cli.command("atualizar-status")
    @with_appcontext
    def atualizar_status_cmd():
        """Força a atualização automática de status de todas as saídas pendentes."""
        pendentes = Registro.query.filter(
            Registro.status.in_([StatusSaida.AGENDADA, StatusSaida.EM_TRANSITO])
        ).all()

        atualizados = sum(1 for r in pendentes if r.atualizar_status_automatico())
        db.session.commit()
        click.echo(f"✅ {atualizados} registro(s) atualizado(s) de {len(pendentes)} pendentes.")

    # ── diagnosticar ───────────────────────────────────────────────────────

    @app.cli.command("diagnosticar")
    @with_appcontext
    def diagnosticar():
        """
        Verifica configurações de sessão/segurança e do banco de dados —
        útil para investigar sintomas como "sessão aparecendo logada
        indevidamente" ou "erro ao salvar com vários usuários ao mesmo
        tempo".
        """
        import os as _os
        from config import INSTANCE_DIR

        click.echo("── Diagnóstico do sistema ──────────────────────────────")

        # SECRET_KEY
        origem = "variável de ambiente" if _os.environ.get("SECRET_KEY") and \
            _os.environ.get("SECRET_KEY") != "troque-esta-chave-em-producao-use-uma-muito-longa" \
            else f"arquivo autogerado ({_os.path.join(INSTANCE_DIR, 'secret_key')})"
        click.echo(f"SECRET_KEY: definida via {origem}.")
        if app.config.get("DEBUG") is False and "autogerado" in origem:
            click.echo(
                "  ⚠️  Em produção, defina SECRET_KEY explicitamente no ambiente "
                "(uma chave autogerada por réplica pode invalidar sessões entre "
                "instâncias diferentes atrás de um load balancer)."
            )

        # Cookies de sessão
        click.echo(
            f"Cookie de sessão: nome={app.config.get('SESSION_COOKIE_NAME')} "
            f"httponly={app.config.get('SESSION_COOKIE_HTTPONLY')} "
            f"samesite={app.config.get('SESSION_COOKIE_SAMESITE')} "
            f"secure={app.config.get('SESSION_COOKIE_SECURE')} "
            f"duração={app.config.get('PERMANENT_SESSION_LIFETIME')}"
        )
        if app.config.get("DEBUG") is False and not app.config.get("SESSION_COOKIE_SECURE"):
            click.echo("  ⚠️  SESSION_COOKIE_SECURE está desligado em produção — verifique se há HTTPS.")

        # session_protection
        from app import login_manager
        click.echo(f"Flask-Login session_protection: {login_manager.session_protection}")

        # Banco de dados
        dialeto = db.engine.dialect.name
        click.echo(f"Banco de dados: {dialeto} — URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
        if dialeto == "sqlite":
            with db.engine.connect() as conn:
                modo = conn.exec_driver_sql("PRAGMA journal_mode;").scalar()
                timeout = conn.exec_driver_sql("PRAGMA busy_timeout;").scalar()
            click.echo(f"  journal_mode={modo} busy_timeout={timeout}ms")
            if str(modo).lower() != "wal":
                click.echo("  ⚠️  journal_mode não está em WAL — acessos simultâneos têm mais chance de dar 'database is locked'.")

        # Otimização de mídia (imagens/vídeos de upload)
        import shutil as _shutil
        try:
            import PIL  # noqa: F401
            click.echo("Pillow (otimização de imagens): instalado.")
        except ImportError:
            click.echo("⚠️  Pillow não encontrado — uploads de imagem vão falhar. Reinstale as dependências (pip install -r requirements.txt).")

        if _shutil.which("ffmpeg"):
            click.echo("ffmpeg (otimização de vídeo): instalado — vídeos de fundo do login são recomprimidos automaticamente.")
        else:
            click.echo(
                "⚠️  ffmpeg não encontrado — uploads de vídeo continuam funcionando, mas SEM "
                "otimização automática (o vídeo é salvo do jeito que foi enviado). "
                "Para instalar: sudo apt-get install -y ffmpeg"
            )

        # Limite de upload do Nginx vs do Flask — best-effort: só faz
        # sentido em produção, atrás de um Nginx configurado por
        # deploy/install.sh. Sem isso, um Nginx desatualizado (ex: uma
        # instalação antiga que nunca rodou a sincronização automática do
        # `--action update`) rejeitaria uploads ANTES de chegarem ao Flask,
        # e o usuário veria isso como um erro genérico do Nginx em vez da
        # mensagem amigável por campo do próprio sistema.
        import re as _re
        nginx_conf_path = "/etc/nginx/sites-available/projeto-saida"
        try:
            with open(nginx_conf_path, "r", encoding="utf-8") as f:
                conteudo_nginx = f.read()
            m = _re.search(r"client_max_body_size\s+([0-9]+)\s*([kKmMgG]?)\s*;", conteudo_nginx)
            if m:
                unidade = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[m.group(2).lower()]
                nginx_bytes = int(m.group(1)) * unidade
                flask_bytes = app.config.get("MAX_CONTENT_LENGTH", 0)
                if nginx_bytes < flask_bytes:
                    click.echo(
                        f"⚠️  client_max_body_size do Nginx ({nginx_bytes // (1024*1024)}MB) é MENOR que "
                        f"MAX_CONTENT_LENGTH do Flask ({flask_bytes // (1024*1024)}MB) — uploads dentro do "
                        "limite do sistema podem ser rejeitados pelo Nginx antes mesmo de chegar na "
                        "aplicação, com uma página de erro genérica em vez da mensagem amigável. "
                        "Rode 'sudo bash deploy/install.sh --action update' para sincronizar automaticamente."
                    )
                else:
                    click.echo(
                        f"Limite de upload: Nginx={nginx_bytes // (1024*1024)}MB, "
                        f"Flask={flask_bytes // (1024*1024)}MB — OK (Nginx com margem confortável)."
                    )
            else:
                click.echo("Não encontrei 'client_max_body_size' na config do Nginx — verifique manualmente.")
        except FileNotFoundError:
            pass  # Ambiente de desenvolvimento, sem Nginx — nada a checar aqui.
        except OSError:
            click.echo("Não consegui ler a config do Nginx para conferir o limite de upload (permissão?).")

        click.echo("─────────────────────────────────────────────────────────")
        click.echo("✅ Diagnóstico concluído.")
