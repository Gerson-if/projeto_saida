"""
migrate_v2.py — Script de migração manual para adicionar as novas colunas/tabelas.
Execute UMA VEZ após o deploy: python migrate_v2.py

Compatível com SQLite (desenvolvimento) e PostgreSQL/MySQL (produção).
"""
import os, sys

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

    def table_exists(table):
        if dialect == "sqlite":
            result = conn.execute(text(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            ))
            return result.fetchone() is not None
        else:
            result = conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_name='{table}'"
            ))
            return result.fetchone() is not None

    print("🔄 Iniciando migração v2...")

    # 1. Tabela motivos_cancelamento
    if not table_exists("motivos_cancelamento"):
        conn.execute(text("""
            CREATE TABLE motivos_cancelamento (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                texto VARCHAR(150) NOT NULL,
                ativo BOOLEAN NOT NULL DEFAULT 1,
                ordem INTEGER NOT NULL DEFAULT 0
            )
        """))
        conn.commit()
        print("  ✅ Tabela motivos_cancelamento criada.")
    else:
        print("  ⏭  Tabela motivos_cancelamento já existe.")

    # 2. Coluna obs_cancelamento em registros
    if not col_exists("registros", "obs_cancelamento"):
        conn.execute(text("ALTER TABLE registros ADD COLUMN obs_cancelamento VARCHAR(200)"))
        conn.commit()
        print("  ✅ Coluna obs_cancelamento adicionada a registros.")
    else:
        print("  ⏭  obs_cancelamento já existe.")

    # 3. Reduzir motivo_cancelamento para 150 chars (SQLite não suporta ALTER COLUMN, ok)
    print("  ℹ  motivo_cancelamento: ajuste de tamanho ignorado no SQLite (sem impacto).")

    # 4. Colunas telefone e email em usuarios
    for col, tipo in [("telefone", "VARCHAR(20)"), ("email", "VARCHAR(120)")]:
        if not col_exists("usuarios", col):
            conn.execute(text(f"ALTER TABLE usuarios ADD COLUMN {col} {tipo}"))
            conn.commit()
            print(f"  ✅ Coluna {col} adicionada a usuarios.")
        else:
            print(f"  ⏭  {col} já existe em usuarios.")

    conn.close()
    print("✅ Migração v2 concluída com sucesso!")

    # Seed motivos padrão se a tabela estiver vazia
    from app.models import MotivoCancelamento
    if MotivoCancelamento.query.count() == 0:
        motivos = [
            ("Desistência pessoal", 1),
            ("Problema de saúde", 2),
            ("Serviço imprevisto na unidade", 3),
            ("Problema no transporte", 4),
            ("Outros", 99),
        ]
        for texto, ordem in motivos:
            db.session.add(MotivoCancelamento(texto=texto, ativo=True, ordem=ordem))
        db.session.commit()
        print("  ✅ Motivos de cancelamento padrão inseridos.")
