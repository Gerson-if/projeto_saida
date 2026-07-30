/**
 * upload-validacao.js — Aviso imediato quando o arquivo escolhido não é do
 * tipo esperado (ex.: uma foto selecionada no campo de vídeo, um vídeo no
 * campo de foto, ou qualquer arquivo só renomeado com a extensão errada).
 *
 * Por que isso não é só o atributo `accept` do <input>: `accept` é apenas
 * uma dica para o seletor de arquivos do sistema operacional — o usuário
 * pode escolher "Todos os arquivos" e selecionar qualquer coisa mesmo
 * assim, e o navegador não avisa nada nesse caso. Este arquivo lê os
 * primeiros bytes do conteúdo real do arquivo (a "assinatura binária",
 * os mesmos bytes já verificados no servidor em app/uploads.py) e mostra
 * um aviso claro, escrito pelo próprio sistema, assim que um arquivo do
 * tipo errado é escolhido — sem esperar o formulário ser enviado.
 *
 * IMPORTANTE: isso é só uma conveniência para dar feedback rápido. A
 * validação que realmente protege o servidor continua sendo a do backend
 * (Pillow para imagem, ffprobe/assinatura para vídeo) — ela roda de novo
 * em todo envio, mesmo que este arquivo não seja carregado por algum
 * motivo (JS desabilitado, navegador antigo, etc.).
 */
(function () {
    "use strict";

    function bytesIniciaisCombinam(bytes, assinatura) {
        if (bytes.length < assinatura.length) return false;
        for (let i = 0; i < assinatura.length; i++) {
            if (bytes[i] !== assinatura[i]) return false;
        }
        return true;
    }

    const ASSINATURAS_IMAGEM = [
        { nome: "PNG", bytes: [0x89, 0x50, 0x4e, 0x47] },
        { nome: "JPEG", bytes: [0xff, 0xd8, 0xff] },
        { nome: "GIF", bytes: [0x47, 0x49, 0x46, 0x38] },
    ];

    function detectarTipoImagem(bytes) {
        for (const assinatura of ASSINATURAS_IMAGEM) {
            if (bytesIniciaisCombinam(bytes, assinatura.bytes)) return assinatura.nome;
        }
        // WEBP: 'RIFF' + 4 bytes de tamanho + 'WEBP'
        if (
            bytes.length >= 12 &&
            bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 &&
            bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 && bytes[11] === 0x50
        ) {
            return "WEBP";
        }
        // ICO
        if (bytes.length >= 4 && bytes[0] === 0x00 && bytes[1] === 0x00 && bytes[2] === 0x01 && bytes[3] === 0x00) {
            return "ICO";
        }
        return null;
    }

    function detectarTipoVideo(bytes) {
        // WebM/Matroska (cabeçalho EBML)
        if (bytesIniciaisCombinam(bytes, [0x1a, 0x45, 0xdf, 0xa3])) return "WEBM";
        // Ogg
        if (bytesIniciaisCombinam(bytes, [0x4f, 0x67, 0x67, 0x53])) return "OGG";
        // Família MP4/MOV (ISO-BMFF): caixa "ftyp" a partir do byte 4
        if (bytes.length >= 12 && bytes[4] === 0x66 && bytes[5] === 0x74 && bytes[6] === 0x79 && bytes[7] === 0x70) {
            // Várias marcas (brand) dessa MESMA família de contêiner são na
            // verdade formatos de IMAGEM (HEIC/HEIF/AVIF, padrão em fotos
            // de iPhone) — sem checar a marca, uma foto HEIC passaria como
            // se fosse um vídeo MP4 válido.
            const marca = String.fromCharCode(bytes[8], bytes[9], bytes[10], bytes[11])
                .trim()
                .toLowerCase();
            const marcasNaoVideo = ["heic", "heix", "heim", "heis", "hevc", "hevx", "mif1", "msf1", "avif", "avis", "crx"];
            if (marcasNaoVideo.indexOf(marca) !== -1) return null;
            return "MP4";
        }
        return null;
    }

    /**
     * Lê os primeiros bytes de `file` e chama `callback(tipoDetectado)`.
     * `tipoDetectado` é uma string (ex: "PNG", "MP4"), `null` se o
     * conteúdo não bateu com nenhum formato esperado, ou `undefined` se
     * não foi possível ler o arquivo (nesse caso, deixa o servidor decidir).
     */
    function detectarTipoArquivo(file, modo, callback) {
        if (typeof FileReader === "undefined") {
            callback(undefined);
            return;
        }
        const reader = new FileReader();
        reader.onload = function (e) {
            try {
                const bytes = new Uint8Array(e.target.result);
                callback(modo === "video" ? detectarTipoVideo(bytes) : detectarTipoImagem(bytes));
            } catch (err) {
                callback(undefined);
            }
        };
        reader.onerror = function () {
            callback(undefined);
        };
        reader.readAsArrayBuffer(file.slice(0, 32));
    }

    /**
     * Valida `input` (um <input type="file">) contra o `modo` esperado
     * ("imagem" ou "video"). Se o conteúdo não combinar, mostra um aviso
     * claro — escrito pela própria aplicação, não uma mensagem genérica
     * do navegador — e limpa a seleção. Sempre chama `aoValidar(ok)` no
     * final (mesmo quando não há arquivo selecionado, ou quando a
     * checagem não pôde ser feita).
     */
    window.validarTipoArquivo = function (input, modo, aoValidar) {
        const file = input.files && input.files[0];
        if (!file) {
            if (aoValidar) aoValidar(true);
            return;
        }
        detectarTipoArquivo(file, modo, function (tipo) {
            if (tipo === undefined) {
                // Não deu para checar no navegador — o servidor sempre
                // valida de novo, então deixamos passar por aqui.
                if (aoValidar) aoValidar(true);
                return;
            }
            if (tipo === null) {
                const esperado = modo === "video"
                    ? "um vídeo (MP4, WEBM ou OGG)"
                    : "uma imagem (PNG, JPG, GIF ou WEBP)";
                const mensagem =
                    'O arquivo selecionado ("' + file.name + '") não parece ser ' + esperado + ". " +
                    "Confira se o arquivo certo foi escolhido (por exemplo, uma foto selecionada onde " +
                    "era esperado um vídeo, ou vice-versa) e tente novamente.";
                // Aviso mostrado PELO SISTEMA (não um alert() nativo do navegador)
                // — usa avisoSistema() quando disponível (páginas com base.html);
                // cai para alert() só como último recurso (ex.: página sem esse
                // helper carregado), para nunca deixar o usuário sem feedback.
                if (typeof window.avisoSistema === "function") {
                    window.avisoSistema(mensagem, "erro");
                } else {
                    window.alert(mensagem);
                }
                input.value = "";
                if (aoValidar) aoValidar(false);
                return;
            }
            if (aoValidar) aoValidar(true);
        });
    };
})();
