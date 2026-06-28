"""
app/uploads.py — Validação e gravação segura de uploads de imagem.

Por que não basta checar a extensão do arquivo
-----------------------------------------------
`secure_filename()` + checar `arquivo.png` no nome NÃO garante que o
conteúdo do arquivo seja realmente uma imagem. Qualquer pessoa pode
renomear um arquivo qualquer (executável, script, HTML com JS, etc.)
para terminar em `.png` e o servidor aceitaria sem perceber.

Este módulo abre o arquivo recebido com a biblioteca Pillow e verifica:
  1. Se o conteúdo é de fato uma imagem decodificável (Pillow.verify()).
  2. Se o formato real do arquivo está na lista de formatos permitidos
     (comparando o formato detectado pela biblioteca, não a extensão).
  3. Se as dimensões (largura x altura) estão dentro de um limite máximo
     razoável, para evitar "bombas de descompressão" (imagens com poucos
     KB mas dimensões gigantescas que consomem memória ao serem abertas).
  4. Se o tamanho do arquivo em bytes está dentro do limite configurado.

Se tudo estiver certo, a imagem é regravada em disco a partir dos dados
decodificados pelo Pillow (re-encode), o que automaticamente descarta
qualquer metadado/payload malicioso que não seja parte da imagem em si,
e padroniza a extensão para o formato real detectado.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Optional

from werkzeug.datastructures import FileStorage

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # Pillow é dependência obrigatória (ver requirements.txt)
    Image = None
    UnidentifiedImageError = Exception


# Formatos aceitos: nome interno do Pillow -> extensão de arquivo a salvar.
FORMATOS_ACEITOS = {
    "PNG": "png",
    "JPEG": "jpg",
    "GIF": "gif",
    "WEBP": "webp",
    "ICO": "ico",
}

# Tamanho máximo de arquivo (bytes) — também reforçado por MAX_CONTENT_LENGTH
# no Flask, mas validado aqui de novo para gerar uma mensagem amigável em vez
# de um erro genérico 413.
TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024  # 5 MB

# Dimensões máximas aceitas (pixels). Evita uploads desproporcionais que
# consumiriam memória/disco/CPU ao processar ou exibir a imagem.
LARGURA_MAXIMA_PX = 4000
ALTURA_MAXIMA_PX = 4000

# Dimensões mínimas (evita arquivos de 1x1 px usados para "passar" a validação).
LARGURA_MINIMA_PX = 8
ALTURA_MINIMA_PX = 8


@dataclass
class ResultadoUpload:
    ok: bool
    nome_arquivo: Optional[str] = None
    erro: Optional[str] = None


def _tamanho_arquivo(file_storage: FileStorage) -> int:
    stream = file_storage.stream
    pos_atual = stream.tell()
    stream.seek(0, os.SEEK_END)
    tamanho = stream.tell()
    stream.seek(pos_atual)
    return tamanho


def validar_e_salvar_imagem(
    file_storage: Optional[FileStorage],
    *,
    destino_dir: str,
    prefixo: str,
    tamanho_maximo_bytes: int = TAMANHO_MAXIMO_BYTES,
    largura_maxima: int = LARGURA_MAXIMA_PX,
    altura_maxima: int = ALTURA_MAXIMA_PX,
) -> ResultadoUpload:
    """
    Valida o conteúdo real de `file_storage` como imagem e, se válido,
    salva em `destino_dir` com um nome de arquivo seguro e único.

    Retorna ResultadoUpload(ok=True, nome_arquivo=...) em caso de sucesso,
    ou ResultadoUpload(ok=False, erro="mensagem amigável") caso contrário.

    Se nenhum arquivo foi enviado (campo vazio), retorna ok=True com
    nome_arquivo=None — isso permite que a rota trate "sem upload" como
    "manter o que já existia", sem confundir com um erro de validação.
    """
    if file_storage is None or not file_storage.filename:
        return ResultadoUpload(ok=True, nome_arquivo=None)

    if Image is None:
        return ResultadoUpload(
            ok=False,
            erro="Não foi possível processar imagens neste servidor (Pillow não instalado).",
        )

    # 1) Tamanho em bytes.
    tamanho = _tamanho_arquivo(file_storage)
    if tamanho <= 0:
        return ResultadoUpload(ok=False, erro="O arquivo enviado está vazio.")
    if tamanho > tamanho_maximo_bytes:
        limite_mb = tamanho_maximo_bytes / (1024 * 1024)
        return ResultadoUpload(
            ok=False,
            erro=f"A imagem excede o tamanho máximo permitido ({limite_mb:.0f} MB).",
        )

    # 2) Conteúdo é realmente uma imagem decodificável?
    try:
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as img:
            img.verify()  # valida integridade sem decodificar pixels
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return ResultadoUpload(
            ok=False,
            erro="O arquivo enviado não é uma imagem válida (PNG, JPG, GIF ou WEBP).",
        )

    # img.verify() invalida o objeto para uso posterior — reabrimos para
    # checar formato e dimensões antes de regravar em disco.
    try:
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as img:
            formato = (img.format or "").upper()
            largura, altura = img.size

            if formato not in FORMATOS_ACEITOS:
                return ResultadoUpload(
                    ok=False,
                    erro="Formato de imagem não suportado. Use PNG, JPG, GIF ou WEBP.",
                )

            if largura < LARGURA_MINIMA_PX or altura < ALTURA_MINIMA_PX:
                return ResultadoUpload(
                    ok=False,
                    erro="A imagem é muito pequena. Envie um arquivo com dimensões maiores.",
                )

            if largura > largura_maxima or altura > altura_maxima:
                return ResultadoUpload(
                    ok=False,
                    erro=(
                        f"A imagem excede as dimensões máximas permitidas "
                        f"({largura_maxima}x{altura_maxima}px). Redimensione e tente novamente."
                    ),
                )

            extensao = FORMATOS_ACEITOS[formato]

            # Normaliza modo de cor problemático antes de salvar (ex.: paletas
            # com transparência em JPEG, que não suporta canal alpha).
            if extensao == "jpg" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            os.makedirs(destino_dir, exist_ok=True)
            nome_final = f"{prefixo}_{uuid.uuid4().hex[:12]}.{extensao}"
            caminho_final = os.path.join(destino_dir, nome_final)

            # Regrava a imagem a partir dos pixels decodificados pelo Pillow:
            # isso descarta qualquer payload extra que não faça parte da
            # imagem (ex.: scripts embutidos em metadados) e garante que o
            # arquivo no disco corresponda exatamente ao formato detectado.
            if extensao == "jpg":
                img.save(caminho_final, format="JPEG", quality=88, optimize=True)
            elif extensao == "png":
                img.save(caminho_final, format="PNG", optimize=True)
            elif extensao == "ico":
                img.save(caminho_final, format="ICO", sizes=[(min(largura, 256), min(altura, 256))])
            else:
                img.save(caminho_final, format=formato)

    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return ResultadoUpload(
            ok=False,
            erro="Não foi possível processar a imagem enviada. Tente outro arquivo.",
        )

    return ResultadoUpload(ok=True, nome_arquivo=nome_final)


def remover_upload_seguro(upload_folder: str, nome_arquivo: Optional[str]) -> None:
    """Remove um arquivo de upload do disco, ignorando erros e tentativas
    de path traversal (nomes contendo '/', '\\' ou '..')."""
    if not nome_arquivo:
        return
    nome_base = os.path.basename(nome_arquivo)
    if nome_base != nome_arquivo or ".." in nome_arquivo:
        return
    try:
        caminho = os.path.join(upload_folder, nome_base)
        if os.path.isfile(caminho):
            os.remove(caminho)
    except OSError:
        pass
