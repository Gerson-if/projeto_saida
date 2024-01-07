<?php
// Configurações para suprimir mensagens de aviso
error_reporting(E_ALL & ~E_NOTICE);
ini_set('display_errors', 0);

session_start();

function validarDatas($dataSaida, $dataRetorno) {
    return strtotime($dataRetorno) >= strtotime($dataSaida);
}

function enviarMensagemConsole($mensagem, $tipo = 'error') {
    echo '<script>console.' . $tipo . '("' . $mensagem . '");</script>';
}

function exibirPopUp($mensagem, $tipo = 'error') {
    echo '<script>alert("' . $mensagem . '");</script>';
}

function encerrarPagina($mensagem = null, $tipo = 'error') {
    exibirPopUp($mensagem, $tipo);
    echo '<script>window.location.href = "processar_saida.php";</script>';
    exit();
}

if (!isset($_SESSION['cpf']) || empty($_SESSION['cpf'])) {
    header("Location: index.php");
    exit();
}

$hostname = 'localhost';
$username = 'root';
$password = 'root';
$database = 'sistema_saida';

$conexao = new mysqli($hostname, $username, $password, $database);

if ($conexao->connect_error) {
    die("Conexão falhou: " . $conexao->connect_error);
}

$mensagemErro = '';
$mensagemSucesso = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['id_to_edit'])) {
    $idToEdit = $_POST['id_to_edit'];
    $editLocal = mysqli_real_escape_string($conexao, $_POST['local']);
    $editDataSaida = mysqli_real_escape_string($conexao, $_POST['data_saida']);

    $checkDuplicateQuery = "SELECT id FROM registros WHERE local=? AND data_saida=? AND id <> ?";
    $stmtCheckDuplicate = $conexao->prepare($checkDuplicateQuery);
    $stmtCheckDuplicate->bind_param("ssi", $editLocal, $editDataSaida, $idToEdit);
    $stmtCheckDuplicate->execute();
    $resultCheckDuplicate = $stmtCheckDuplicate->get_result();

    if ($resultCheckDuplicate->num_rows > 0) {
        $mensagemErro = "Já existe um registro com a mesma cidade/estado/país e data de saída.";
        encerrarPagina($mensagemErro);
    } else {
        $editMotivo = mysqli_real_escape_string($conexao, $_POST['motivo']);
        $editDataRetorno = isset($_POST['data_retorno']) ? mysqli_real_escape_string($conexao, $_POST['data_retorno']) : null;
        $editTelefoneContato = mysqli_real_escape_string($conexao, $_POST['telefone_contato']);
        $editEnderecoDestino = mysqli_real_escape_string($conexao, $_POST['endereco_destino']);

        $validacaoDatas = validarDatas($editDataSaida, $editDataRetorno);

        if (!$validacaoDatas) {
            $mensagemErro = "A data de retorno deve ser posterior à data de saída.";
            enviarMensagemConsole($mensagemErro);
        } else {
            $updateSql = "UPDATE registros SET local=?, motivo=?, data_saida=?, data_retorno=?, telefone_contato=?, endereco_destino=? WHERE id=?";
            $stmt = $conexao->prepare($updateSql);
            $stmt->bind_param("ssssssi", $editLocal, $editMotivo, $editDataSaida, $editDataRetorno, $editTelefoneContato, $editEnderecoDestino, $idToEdit);
            $resultUpdate = $stmt->execute();

            if ($resultUpdate) {
                $mensagemSucesso = "Edição realizada com sucesso!";
                encerrarPagina($mensagemSucesso, 'log');
            } else {
                $mensagemErro = "Erro ao editar saída: " . $stmt->error;
                enviarMensagemConsole($mensagemErro);
            }
        }
    }
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['edit'])) {
    $idToEdit = $_POST['edit'];
    $editQuery = "SELECT * FROM registros WHERE id = ?";
    $stmt = $conexao->prepare($editQuery);
    $stmt->bind_param("i", $idToEdit);
    $stmt->execute();
    $resultEdit = $stmt->get_result();

    if ($resultEdit->num_rows > 0) {
        $editData = $resultEdit->fetch_assoc();
        $editLocal = $editData['local'];
        $editMotivo = $editData['motivo'];
        $editDataSaida = $editData['data_saida'];
        $editDataRetorno = $editData['data_retorno'];
        $editTelefoneContato = $editData['telefone_contato'];
        $editEnderecoDestino = $editData['endereco_destino'];
    }
}
?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="css/style_saida.css">
    <title>Formulário de Edição</title>
</head>
<body>
    <form method="post" action="">
        <h2>Formulário de Edição</h2>
        <a href="processar_saida.php" class="back-button">Voltar</a>

        <?php
        if (!empty($mensagemErro)) {
            enviarMensagemConsole($mensagemErro);
        }
        ?>

        <label for="local">Cidade/Estado/País:</label>
        <input type="text" id="local" name="local" value="<?= htmlspecialchars($editLocal) ?>" required>

        <label for="motivo">Motivo:</label>
        <textarea id="motivo" name="motivo" rows="4" required><?= htmlspecialchars($editMotivo) ?></textarea>

        <label for="data_saida">Data de Saída:</label>
        <input type="date" id="data_saida" name="data_saida" value="<?= htmlspecialchars($editDataSaida) ?>" min="<?= date('Y-m-d'); ?>" required>

        <label for="data_retorno">Data de Retorno:</label>
        <input type="date" id="data_retorno" name="data_retorno" value="<?= htmlspecialchars($editDataRetorno) ?>" min="<?= date('Y-m-d'); ?>">

        <label for="telefone_contato">Telefone para Contato:</label>
        <input type="tel" id="telefone_contato" name="telefone_contato" value="<?= htmlspecialchars($editTelefoneContato) ?>">

        <label for="endereco_destino">Endereço de Destino:</label>
        <textarea id="endereco_destino" name="endereco_destino" rows="4"><?= htmlspecialchars($editEnderecoDestino) ?></textarea>

        <input type="hidden" name="id_to_edit" value="<?= $idToEdit ?>">
        <button type="submit">Salvar Edição</button>
    </form>

    <?php
    if (!empty($mensagemSucesso)) {
        enviarMensagemConsole($mensagemSucesso, 'log');
    }
    ?>
</body>
</html>
