"""
app/validators.py — Validação e sanitização centralizada de dados de entrada.

Por que este módulo existe
--------------------------
Os formulários HTML usam `maxlength`, `type="date"`, `type="tel"` etc. como
ajuda visual, mas isso NÃO impede que um usuário malicioso (ou um script)
envie qualquer coisa diretamente via POST — texto gigante, emojis, tags HTML,
bytes nulos, números fora de qualquer faixa razoável, e assim por diante.

Toda validação que realmente importa para a integridade do banco de dados
precisa acontecer no servidor. Este módulo concentra essas regras para que
as rotas (admin.py, user.py, auth.py, reports.py) apenas chamem funções
simples e tratem os erros retornados, em vez de duplicar lógica de
validação (e duplicar bugs) em cada rota.

Convenções
----------
- Toda função `validar_*` devolve uma tupla (valor_limpo, lista_de_erros).
  Se `lista_de_erros` estiver vazia, `valor_limpo` é seguro para persistir.
- Strings são sempre sanitizadas (remoção de caracteres de controle e, por
  padrão, de emojis/símbolos pictográficos) e têm seu tamanho limitado ao
  tamanho da respectiva coluna no banco — mesmo que a validação "passe",
  nunca devolvemos algo maior do que a coluna aceita.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, date
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Sanitização de texto
# ─────────────────────────────────────────────────────────────────────────────

# Remove caracteres de controle (exceto espaço comum), incluindo bytes nulos,
# caracteres de formatação invisível e marcadores de direcionalidade Unicode
# (ex.: \u202E RIGHT-TO-LEFT OVERRIDE, usado em ataques que disfarçam a
# extensão real de um arquivo ou o sentido de leitura de um texto). Nenhum
# desses caracteres tem motivo legítimo para aparecer em nomes, locais,
# motivos etc. Mantém acentuação e pontuação normal do português.
_CONTROL_CHARS_RE = re.compile(
    r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F"
    r"\u200B-\u200F"   # zero-width space/joiner + marcadores LTR/RTL antigos
    r"\u202A-\u202E"   # embedding/override de direcionalidade (LRE/RLE/PDF/LRO/RLO)
    r"\u2060-\u2069"   # word joiner + isolamento direcional (LRI/RLI/FSI/PDI)
    r"\uFEFF"          # BOM / zero-width no-break space
    r"]"
)

# Emojis e outros símbolos pictográficos (não fazem sentido em CPF, telefone,
# nomes formais de documentos militares, cores hex, etc.). Cobre os blocos
# Unicode mais comuns usados por emojis e pictogramas.
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FFFF"  # emojis, símbolos diversos, pictogramas
    "\U00002600-\U000027BF"  # símbolos diversos / dingbats
    "\U0001F1E6-\U0001F1FF"  # bandeiras (pares de letras regionais)
    "\u2190-\u21FF"          # setas
    "\u2300-\u23FF"          # símbolos técnicos diversos (inclui ⏰ etc.)
    "\uFE0F"                  # variation selector (estiliza emoji)
    "]+",
    flags=re.UNICODE,
)


def remover_caracteres_controle(texto: str) -> str:
    """Remove bytes nulos e caracteres de controle invisíveis."""
    if not texto:
        return texto
    return _CONTROL_CHARS_RE.sub("", texto)


def remover_emojis(texto: str) -> str:
    """Remove emojis e pictogramas de uma string."""
    if not texto:
        return texto
    return _EMOJI_RE.sub("", texto)


def sanitizar_texto(
    valor: Optional[str],
    max_len: Optional[int] = None,
    permitir_emoji: bool = False,
    colapsar_espacos: bool = True,
) -> str:
    """
    Limpa uma string recebida via formulário:
      1. Garante string (None -> "").
      2. Normaliza Unicode (NFC) para evitar truques com combinação de acentos.
      3. Remove caracteres de controle / invisíveis.
      4. Remove emojis, a menos que explicitamente permitido.
      5. Colapsa espaços múltiplos e remove espaços nas pontas.
      6. Trunca para `max_len`, se informado (defesa em profundidade: mesmo
         que a validação de tamanho não seja chamada, nunca persistimos
         algo maior do que a coluna do banco suporta).
    """
    if valor is None:
        return ""
    texto = str(valor)
    texto = unicodedata.normalize("NFC", texto)
    texto = remover_caracteres_controle(texto)
    if not permitir_emoji:
        texto = remover_emojis(texto)
    if colapsar_espacos:
        texto = re.sub(r"[ \t]+", " ", texto)
        texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = texto.strip()
    if max_len is not None and len(texto) > max_len:
        texto = texto[:max_len].rstrip()
    return texto


# ─────────────────────────────────────────────────────────────────────────────
# CPF
# ─────────────────────────────────────────────────────────────────────────────

def _apenas_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def cpf_valido(cpf_digitos: str) -> bool:
    """
    Valida o CPF pelo algoritmo oficial dos dígitos verificadores.
    Recebe apenas os 11 dígitos (sem pontuação).
    """
    if len(cpf_digitos) != 11 or not cpf_digitos.isdigit():
        return False
    # CPFs com todos os dígitos iguais (00000000000, 11111111111, ...)
    # são matematicamente "válidos" pelo algoritmo mas nunca são reais.
    if cpf_digitos == cpf_digitos[0] * 11:
        return False

    def _digito_verificador(parcial: str, peso_inicial: int) -> int:
        soma = sum(int(d) * peso for d, peso in zip(parcial, range(peso_inicial, 1, -1)))
        resto = (soma * 10) % 11
        return 0 if resto == 10 else resto

    d1 = _digito_verificador(cpf_digitos[:9], 10)
    d2 = _digito_verificador(cpf_digitos[:9] + str(d1), 11)
    return cpf_digitos[-2:] == f"{d1}{d2}"


def validar_cpf_ou_identificacao(
    valor: str, *, exigir_cpf_real: bool = False
) -> tuple[str, list[str]]:
    """
    Valida o campo de CPF/login.

    O sistema usa o CPF como identificador, mas o próprio README/seed admite
    um valor não numérico como login do super-admin (ex: "admin"). Por isso,
    por padrão, aceitamos:
      - Um CPF numericamente válido (11 dígitos + dígitos verificadores OK),
        OU
      - Um identificador alfanumérico simples (letras, números, ponto,
        hífen e underscore), pensado para contas especiais como "admin".

    Quando `exigir_cpf_real=True`, apenas CPFs com 11 dígitos válidos pelo
    algoritmo oficial são aceitos (recomendado ao cadastrar militares).

    Em qualquer caso: nunca aceitamos emojis, espaços, ou símbolos soltos.
    """
    erros: list[str] = []
    bruto = sanitizar_texto(valor, max_len=14)

    if not bruto:
        erros.append("O CPF é obrigatório.")
        return "", erros

    # Removendo a pontuação típica de CPF (pontos, hífen, espaços), se o que
    # restar for só dígitos, o valor SÓ pode ser interpretado como CPF — nunca
    # como "identificador alternativo". Isso evita aceitar algo como "123"
    # ou "00000000000" apenas porque tem menos de 11 dígitos.
    sem_pontuacao_cpf = re.sub(r"[.\-\s]", "", bruto)
    parece_cpf = bool(sem_pontuacao_cpf) and sem_pontuacao_cpf.isdigit()

    if parece_cpf:
        so_digitos = sem_pontuacao_cpf
        if len(so_digitos) != 11 or not cpf_valido(so_digitos):
            erros.append("CPF inválido. Verifique os 11 números digitados.")
            return bruto[:14], erros
        return so_digitos, erros

    if exigir_cpf_real:
        erros.append("Informe um CPF válido com 11 números.")
        return bruto[:14], erros

    # Identificador alternativo (ex.: "admin"): letras/números/.-_ apenas,
    # precisa conter ao menos uma letra (caso puramente numérico já tratado acima).
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,14}", bruto) or not re.search(r"[A-Za-z]", bruto):
        erros.append(
            "CPF inválido. Use apenas números (11 dígitos) ou um identificador "
            "simples sem espaços, emojis ou símbolos especiais."
        )
        return bruto[:14], erros

    return bruto, erros


# ─────────────────────────────────────────────────────────────────────────────
# Nome
# ─────────────────────────────────────────────────────────────────────────────

_NOME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' .\-]+$")


def validar_nome(valor: str, *, campo: str = "nome", min_len: int = 2, max_len: int = 100) -> tuple[str, list[str]]:
    """Valida nomes de pessoas/organizações: letras, acentos, espaço, ponto, hífen e apóstrofo."""
    erros: list[str] = []
    nome = sanitizar_texto(valor, max_len=max_len)

    if not nome:
        erros.append(f"O {campo} é obrigatório.")
        return nome, erros

    if len(nome) < min_len:
        erros.append(f"O {campo} deve ter ao menos {min_len} caracteres.")

    if not _NOME_RE.match(nome):
        erros.append(
            f"O {campo} deve conter apenas letras, espaços e os símbolos . ' -  "
            "(sem números, emojis ou outros caracteres especiais)."
        )

    return nome, erros


# ─────────────────────────────────────────────────────────────────────────────
# Telefone
# ─────────────────────────────────────────────────────────────────────────────

def validar_telefone(valor: str, *, obrigatorio: bool = False) -> tuple[str, list[str]]:
    """
    Aceita telefones brasileiros (fixo ou celular), com ou sem DDD/código de país,
    formatados livremente pelo usuário ((67) 99999-9999, 67999999999, etc.).
    Armazenamos como o usuário digitou (até 20 caracteres), mas só aceitamos
    se houver uma quantidade plausível de dígitos.
    """
    erros: list[str] = []
    bruto = (valor or "").strip()
    texto = sanitizar_texto(valor, max_len=20)

    if not texto:
        if obrigatorio:
            erros.append("O telefone de contato é obrigatório.")
        return "", erros

    # Verifica o formato ANTES de qualquer remoção de emoji/caractere especial:
    # um telefone com emoji, letra ou símbolo embutido deve ser rejeitado, não
    # silenciosamente "limpo" e aceito.
    if not re.fullmatch(r"[0-9()+\-.\s]{8,20}", bruto):
        erros.append("Telefone inválido: use apenas números e os símbolos ( ) + -.")
        return texto, erros

    digitos = _apenas_digitos(texto)
    if len(digitos) < 10 or len(digitos) > 13:
        erros.append(
            "Telefone inválido. Informe um número com DDD, ex: (67) 99999-9999."
        )
        return texto, erros

    return texto, erros


# ─────────────────────────────────────────────────────────────────────────────
# Datas
# ─────────────────────────────────────────────────────────────────────────────

ANO_MIN = 1900
ANO_MAX = 2100


def validar_data(
    valor: str, *, campo: str = "data", obrigatoria: bool = False
) -> tuple[Optional[datetime], list[str]]:
    """
    Converte e valida uma data vinda de <input type="date"> (formato YYYY-MM-DD).
    Rejeita datas malformadas e datas com anos absurdos (ex: ano 0001 ou 9999
    digitados manualmente via POST, contornando o seletor nativo do browser).
    """
    erros: list[str] = []
    texto = (valor or "").strip()

    if not texto:
        if obrigatoria:
            erros.append(f"A {campo} é obrigatória.")
        return None, erros

    # input type="date" sempre manda YYYY-MM-DD; qualquer outra coisa é uma
    # tentativa de payload malformado/manual.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        erros.append(f"Formato de {campo} inválido.")
        return None, erros

    try:
        dt = datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        erros.append(f"{campo.capitalize()} inválida.")
        return None, erros

    if not (ANO_MIN <= dt.year <= ANO_MAX):
        erros.append(f"{campo.capitalize()} fora de um intervalo razoável de anos.")
        return None, erros

    return dt, erros


# ─────────────────────────────────────────────────────────────────────────────
# Texto livre genérico (local, motivo, endereço, sigla, textos de config...)
# ─────────────────────────────────────────────────────────────────────────────

def validar_texto_livre(
    valor: str,
    *,
    campo: str,
    max_len: int,
    min_len: int = 0,
    obrigatorio: bool = False,
    permitir_emoji: bool = False,
) -> tuple[str, list[str]]:
    """
    Valida campos de texto livre (local, motivo, endereço, observações).
    Garante tamanho máximo real (igual ao da coluna do banco) e remove
    emojis/caracteres de controle por padrão.
    """
    erros: list[str] = []
    bruto_original = valor or ""
    texto = sanitizar_texto(valor, max_len=max_len, permitir_emoji=permitir_emoji)

    if not texto:
        if obrigatorio:
            erros.append(f"O campo {campo} é obrigatório.")
        return texto, erros

    if len(texto) < min_len:
        erros.append(f"O campo {campo} deve ter ao menos {min_len} caracteres.")

    # Se o texto sanitizado encolheu muito em relação ao original, é sinal de
    # que o conteúdo era majoritariamente emoji/controle/excesso de tamanho —
    # avisamos para não surpreender o usuário com um valor diferente do digitado.
    if obrigatorio and not texto and bruto_original.strip():
        erros.append(
            f"O campo {campo} contém apenas caracteres não permitidos (emojis/símbolos)."
        )

    return texto, erros


# ─────────────────────────────────────────────────────────────────────────────
# Cor hexadecimal (usada em ConfigSistema: cor_primaria / cor_secundaria)
# ─────────────────────────────────────────────────────────────────────────────

def validar_cor_hex(valor: str, *, default: str = "#1a3a5c") -> tuple[str, list[str]]:
    erros: list[str] = []
    texto = sanitizar_texto(valor, max_len=7)
    if not texto:
        return default, erros
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", texto):
        erros.append("Cor inválida. Use o seletor de cores ou um valor hexadecimal (#RRGGBB).")
        return default, erros
    return texto, erros


# ─────────────────────────────────────────────────────────────────────────────
# Inteiro seguro (ids vindos de formulário/query string)
# ─────────────────────────────────────────────────────────────────────────────

def parse_int_seguro(valor, *, minimo: Optional[int] = None, maximo: Optional[int] = None) -> Optional[int]:
    """
    Converte valores de formulário/query string em int, sem nunca lançar
    exceção. Retorna None se o valor não for um inteiro válido ou estiver
    fora dos limites informados.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto or not re.fullmatch(r"-?\d+", texto):
        return None
    try:
        numero = int(texto)
    except (ValueError, OverflowError):
        return None
    if minimo is not None and numero < minimo:
        return None
    if maximo is not None and numero > maximo:
        return None
    return numero
