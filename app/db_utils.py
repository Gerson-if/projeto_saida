"""
app/db_utils.py — Robustez de banco de dados sob acesso simultâneo.

Contexto do problema
---------------------
O SQLite permite apenas UM escritor por vez no arquivo inteiro do banco.
Nesta aplicação, além dos usuários usando o sistema ao mesmo tempo, também
existe um job em background (APScheduler, veja app/__init__.py) que grava no
mesmo banco periodicamente. Sem nenhum ajuste, o comportamento padrão do
SQLite é: se dois "escritores" tentam gravar ao mesmo tempo, o segundo
recebe imediatamente o erro `OperationalError: database is locked` — mesmo
que a espera necessária fosse de poucos milissegundos.

Isso é a causa mais provável dos "erros em acessos simultâneos" relatados:
dois usuários salvando formulários ao mesmo tempo, ou um usuário salvando
exatamente quando o scheduler atualiza status, faz a segunda operação falhar
sem necessidade — e como as rotas usavam `except Exception: ... rollback()`
sem log nenhum, o erro real nunca aparecia em lugar nenhum, só o flash
genérico "não foi possível salvar".

Este módulo resolve isso em duas frentes:

1. `configurar_sqlite(app, db)` — liga o modo WAL (Write-Ahead Logging), que
   permite leituras concorrentes enquanto uma escrita acontece, e define um
   `busy_timeout`, que faz o SQLite ESPERAR (em vez de falhar na hora)
   quando encontra um lock — a fila se resolve sozinha na grande maioria
   dos casos.

2. `commit_seguro(...)` — substitui os vários blocos repetidos de
   `try/except Exception: db.session.rollback()` espalhados pelas rotas.
   Ele:
   - Faz retry automático (com pequeno backoff) especificamente para erros
     transitórios de lock, que ainda podem ocorrer mesmo com busy_timeout
     sob carga muito alta.
   - **Sempre loga a exceção real** via `current_app.logger.exception(...)`
     antes de fazer rollback, para que o erro fique visível nos logs em vez
     de desaparecer silenciosamente.
   - Continua devolvendo uma mensagem amigável para o usuário.
"""

from __future__ import annotations

import time
from typing import Callable

from flask import current_app
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError


def configurar_sqlite(app, db) -> None:
    """
    Ativa WAL + busy_timeout em toda nova conexão SQLite aberta pela engine.
    Não tem efeito (e não causa erro) em bancos que não sejam SQLite, como
    MariaDB/MySQL em produção — o listener simplesmente checa o dialeto.
    """

    @event.listens_for(db.engine, "connect")
    def _ajustar_pragmas_sqlite(dbapi_connection, connection_record):  # noqa: ANN001
        if db.engine.dialect.name != "sqlite":
            return
        timeout_ms = app.config.get("SQLITE_BUSY_TIMEOUT_MS", 8000)
        cursor = dbapi_connection.cursor()
        try:
            # WAL: leitores não bloqueiam escritor e vice-versa.
            cursor.execute("PRAGMA journal_mode=WAL;")
            # Espera até N ms por um lock antes de levantar "database is
            # locked", em vez de falhar instantaneamente.
            cursor.execute(f"PRAGMA busy_timeout={int(timeout_ms)};")
            # Garante que FKs (ON DELETE CASCADE/SET NULL) sejam respeitadas
            # — o SQLite não aplica isso por padrão em cada conexão.
            cursor.execute("PRAGMA foreign_keys=ON;")
        finally:
            cursor.close()


def _e_erro_de_lock(exc: Exception) -> bool:
    msg = str(exc).lower()
    return isinstance(exc, OperationalError) and (
        "locked" in msg or "busy" in msg
    )


def commit_seguro(
    db,
    *,
    mensagem_erro: str = "Não foi possível salvar as alterações. Tente novamente.",
    mensagem_duplicado: str | None = None,
    max_tentativas: int | None = None,
    on_erro: Callable[[Exception], None] | None = None,
) -> tuple[bool, str | None]:
    """
    Faz `db.session.commit()` com retry para locks transitórios e log real
    de qualquer falha. Retorna (sucesso, mensagem_para_o_usuario).

    Uso típico nas rotas (substitui o try/except manual):

        ok, erro = commit_seguro(db, mensagem_erro="Não foi possível cadastrar.")
        if not ok:
            flash(erro, "danger")
            return render_template(...)
        flash("Cadastrado com sucesso!", "success")
        return redirect(...)
    """
    tentativas = max_tentativas or current_app.config.get("DB_COMMIT_MAX_TENTATIVAS", 3)
    espera = 0.1  # segundos; cresce a cada nova tentativa (backoff simples)

    for tentativa in range(1, tentativas + 1):
        try:
            db.session.commit()
            return True, None
        except IntegrityError as exc:
            # Violação de UNIQUE/FK — não adianta repetir, os dados que
            # colidem continuam colidindo. Comum em corrida "checar depois
            # inserir": dois requests passam pela checagem antes de qualquer
            # um commitar, e o segundo commit esbarra na constraint do banco
            # (que é a garantia definitiva contra duplicidade).
            db.session.rollback()
            current_app.logger.warning(
                "IntegrityError ao commitar (provável condição de corrida "
                "ou dado duplicado): %s", exc,
            )
            if on_erro:
                on_erro(exc)
            return False, mensagem_duplicado or (
                "Este registro já existe ou conflita com outro. "
                "Atualize a página e tente novamente."
            )
        except OperationalError as exc:
            db.session.rollback()
            if _e_erro_de_lock(exc) and tentativa < tentativas:
                current_app.logger.warning(
                    "Banco ocupado (tentativa %s/%s) — tentando novamente: %s",
                    tentativa, tentativas, exc,
                )
                time.sleep(espera)
                espera *= 2
                continue
            current_app.logger.exception(
                "Falha de banco de dados ao commitar (esgotadas as tentativas "
                "de retry)."
            )
            if on_erro:
                on_erro(exc)
            return False, (
                "O sistema está com muitos acessos simultâneos agora. "
                "Tente novamente em alguns segundos."
                if _e_erro_de_lock(exc) else mensagem_erro
            )
        except Exception as exc:  # noqa: BLE001 — última linha de defesa
            db.session.rollback()
            current_app.logger.exception("Erro inesperado ao commitar no banco.")
            if on_erro:
                on_erro(exc)
            return False, mensagem_erro

    return False, mensagem_erro
