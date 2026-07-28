"""
run.py — Ponto de entrada da aplicação.

Desenvolvimento:
    python run.py

Produção (recomendado via Gunicorn):
    gunicorn "run:app" -w 4 -b 0.0.0.0:8000
"""

import os

from app import create_app, db
from app.models import ConfigSistema, Registro, Subunidade, Usuario

app = create_app(os.environ.get("FLASK_ENV", "development"))


@app.shell_context_processor
def make_shell_context() -> dict:
    """Expõe modelos no shell Flask: flask shell"""
    return {
        "db": db,
        "Usuario": Usuario,
        "Registro": Registro,
        "Subunidade": Subunidade,
        "ConfigSistema": ConfigSistema,
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=app.config.get("DEBUG", False))
