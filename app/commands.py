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
from app.models import ConfigSistema, Registro, StatusSaida, Subunidade, TipoUsuario, Usuario


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
            ("dicas_viagem",  "Verifique documentos e comunicação antes de sair.\nMantenha contato com a unidade durante a viagem.\nRespeite os horários de retorno estabelecidos.\nEm caso de imprevisto, comunique imediatamente a unidade.", "Dicas de viagem segura"),
        ]
        for chave, valor, desc in defaults:
            if not ConfigSistema.query.filter_by(chave=chave).first():
                db.session.add(ConfigSistema(chave=chave, valor=valor, descricao=desc))

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
        if Usuario.query.filter_by(cpf=cpf).first():
            click.echo(f"❌ Já existe um usuário com CPF {cpf}.")
            return
        admin = Usuario(nome=nome, cpf=cpf, tipo=TipoUsuario.ADMIN, ativo=True)
        admin.set_senha(senha)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"✅ Admin '{nome}' criado com sucesso! CPF: {cpf}")

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
