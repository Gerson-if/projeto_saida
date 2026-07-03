"""
migrate_v3.py — Adiciona as colunas de proteção contra força bruta no login.
Execute UMA VEZ após atualizar o código: python migrate_v3.py

Compatível com SQLite (desenvolvimento) e PostgreSQL/MySQL (produção).
Instalações novas não precisam rodar isso — `flask init-db` já cria as
colunas, pois elas fazem parte do modelo Usuario.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
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

    print("🔄 Iniciando migração v3 (proteção de login)...")

    if not col_exists("usuarios", "tentativas_login"):
        conn.execute(text(
            "ALTER TABLE usuarios ADD COLUMN tentativas_login INTEGER NOT NULL DEFAULT 0"
        ))
        conn.commit()
        print("  ✅ Coluna tentativas_login adicionada a usuarios.")
    else:
        print("  ⏭  tentativas_login já existe.")

    if not col_exists("usuarios", "bloqueado_ate"):
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN bloqueado_ate DATETIME"))
        conn.commit()
        print("  ✅ Coluna bloqueado_ate adicionada a usuarios.")
    else:
        print("  ⏭  bloqueado_ate já existe.")

    conn.close()
    print("✅ Migração v3 concluída com sucesso!")
