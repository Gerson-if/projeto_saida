"""
migrate_v5.py — Corrige a constraint de chave estrangeira registros.cpf_usuario
para incluir ON UPDATE CASCADE. Execute UMA VEZ após atualizar o código:
python migrate_v5.py

Contexto do bug corrigido
--------------------------
A tabela `registros` referencia `usuarios.cpf` como chave estrangeira com
`ON DELETE CASCADE`, mas sem `ON UPDATE CASCADE`. Isso significa que sempre
que um administrador tentava corrigir o CPF de um usuário que já possuía
pelo menos uma saída registrada, o banco recusava a alteração com um erro
de violação de chave estrangeira — na prática, tornando impossível editar o
CPF de praticamente qualquer usuário já em uso no sistema.

A rota app/routes/admin.py (editar_usuario) já contorna esse problema em
tempo de execução (usando PRAGMA defer_foreign_keys=ON no SQLite), então
rodar esta migração NÃO é obrigatório para o sistema voltar a funcionar.
Ainda assim, é recomendado rodá-la: ela recria a tabela `registros` já com
a cláusula `ON UPDATE CASCADE` no banco, deixando o schema fisicamente
consistente com o modelo (app/models/__init__.py) e mais robusto para o
futuro (inclusive fora desta rota, ex.: scripts administrativos diretos).

Compatível apenas com SQLite (banco padrão deste projeto — veja
config.py). Em PostgreSQL/MySQL, a constraint já é criada corretamente
com ON UPDATE CASCADE nativo a partir do modelo atual em instalações novas;
bancos de produção já existentes nesses SGBDs podem precisar de um ALTER
TABLE manual (DROP CONSTRAINT / ADD CONSTRAINT ... ON UPDATE CASCADE),
fora do escopo deste script.

O que este script faz (SQLite):
  1. Verifica se a constraint já tem ON UPDATE CASCADE (idempotente — se
     já estiver correta, não faz nada).
  2. Recria a tabela `registros` com o schema atual do modelo (que já
     inclui ON UPDATE CASCADE), preservando todas as colunas e dados.
  3. Recria os índices esperados pelo modelo.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text

from app import create_app, db
from app.models import Registro

app = create_app()

with app.app_context():
    dialect = db.engine.dialect.name  # sqlite | postgresql | mysql

    if dialect != "sqlite":
        print(
            "⏭  Este script só migra automaticamente bancos SQLite. Para "
            f"'{dialect}', verifique manualmente se a constraint de "
            "registros.cpf_usuario já possui ON UPDATE CASCADE (o modelo "
            "atual já a declara corretamente para instalações novas)."
        )
        sys.exit(0)

    conn = db.engine.connect()

    def _fk_ja_tem_on_update_cascade() -> bool:
        result = conn.execute(text("PRAGMA foreign_key_list(registros)"))
        for row in result:
            # row: (id, seq, table, from, to, on_update, on_delete, match)
            if row[2] == "usuarios" and row[3] == "cpf_usuario":
                return (row[5] or "").upper() == "CASCADE"
        return False

    print("🔄 Iniciando migração v5 (ON UPDATE CASCADE em registros.cpf_usuario)...")

    if _fk_ja_tem_on_update_cascade():
        print("  ⏭  A constraint já possui ON UPDATE CASCADE. Nada a fazer.")
        conn.close()
        sys.exit(0)

    trans = conn.begin()
    try:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("ALTER TABLE registros RENAME TO registros_old_v5"))

        # Recria a tabela usando o schema atual do modelo (já com
        # ON UPDATE CASCADE declarado em app/models/__init__.py).
        Registro.__table__.create(bind=conn)

        colunas = [c.name for c in Registro.__table__.columns]
        colunas_sql = ", ".join(colunas)
        conn.execute(text(
            f"INSERT INTO registros ({colunas_sql}) "
            f"SELECT {colunas_sql} FROM registros_old_v5"
        ))

        conn.execute(text("DROP TABLE registros_old_v5"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        trans.commit()
        print("  ✅ Tabela registros recriada com ON UPDATE CASCADE.")
    except Exception:
        trans.rollback()
        print("  ❌ Falha na migração — nenhuma alteração foi aplicada (rollback).")
        raise
    finally:
        conn.close()

    print("✅ Migração v5 concluída com sucesso!")
