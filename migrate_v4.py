"""
migrate_v4.py — Adiciona o recurso de Posto/Graduação (hierarquia militar).
Execute UMA VEZ após atualizar o código: python migrate_v4.py

Compatível com SQLite (desenvolvimento) e PostgreSQL/MySQL (produção).
Instalações novas não precisam rodar isso — `flask init-db` já cria tudo,
pois faz parte dos modelos declarados em app/models.

O que este script faz:
  1. Cria a tabela `postos_graduacoes` (se não existir).
  2. Cria a tabela `solicitacoes_posto_graduacao` (se não existir).
  3. Adiciona a coluna `posto_graduacao_id` em `usuarios` (se não existir).
  4. Garante a configuração `postos_habilitados` (padrão "0" — desligado),
     para que o recurso não apareça em nenhum formulário até o
     super-usuário decidir ativá-lo em Configurações.

Nada disso quebra instalações existentes: a coluna é nullable e o recurso
começa desativado.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models import ConfigSistema
from sqlalchemy import text

app = create_app()

with app.app_context():
    conn = db.engine.connect()
    dialect = db.engine.dialect.name  # sqlite | postgresql | mysql

    def col_exists(table, column):
        if dialect == "sqlite":
            result = conn.execute(text(f"PRAGMA table_info({table})"))
            return any(row[1] == column for row in result)
        else:
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name='{table}' AND column_name='{column}'"
            ))
            return result.fetchone() is not None

    print("🔄 Iniciando migração v4 (Posto/Graduação)...")

    # 1 e 2 — tabelas novas: cria só as que faltam (não mexe nas existentes).
    from app.models import PostoGraduacao, SolicitacaoPostoGraduacao
    PostoGraduacao.__table__.create(bind=db.engine, checkfirst=True)
    SolicitacaoPostoGraduacao.__table__.create(bind=db.engine, checkfirst=True)
    print("  ✅ Tabelas postos_graduacoes / solicitacoes_posto_graduacao ok.")

    # 3 — coluna em usuarios
    if not col_exists("usuarios", "posto_graduacao_id"):
        conn.execute(text(
            "ALTER TABLE usuarios ADD COLUMN posto_graduacao_id INTEGER"
        ))
        conn.commit()
        print("  ✅ Coluna posto_graduacao_id adicionada a usuarios.")
    else:
        print("  ⏭  posto_graduacao_id já existe.")

    conn.close()

    # 4 — configuração padrão (desligada)
    if not ConfigSistema.query.filter_by(chave="postos_habilitados").first():
        db.session.add(ConfigSistema(
            chave="postos_habilitados",
            valor="0",
            descricao="Exibe o campo Posto/Graduação no cadastro de usuários (0=desligado, 1=ligado)",
        ))
        db.session.commit()
        print("  ✅ Configuração postos_habilitados criada (desligada por padrão).")
    else:
        print("  ⏭  Configuração postos_habilitados já existe.")

    print("✅ Migração v4 concluída com sucesso!")
    print("   O recurso está DESLIGADO por padrão. Ative-o em Configurações → Hierarquia.")
