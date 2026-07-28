#!/usr/bin/env bash
# setup_dev.sh — Bootstrap do ambiente de desenvolvimento
# Uso: bash setup_dev.sh

set -e

echo "🔧  Verificando Python..."
python3 --version

echo "📦  Instalando dependências..."
pip install -r requirements.txt

echo "📄  Criando .env (se não existir)..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   ✅  .env criado a partir de .env.example"
else
    echo "   ⏭   .env já existe, pulando."
fi

echo "🗄   Inicializando banco de dados SQLite..."
export FLASK_ENV=development
flask init-db

echo "🌱  Inserindo dados de exemplo..."
flask seed

echo ""
echo "✅  Pronto! Execute: python run.py"
echo "   Acesso: http://localhost:5000"
echo "   Admin padrão: cpf=admin / senha=admin123"
