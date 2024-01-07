<?php
session_start();

// Redireciona se o usuário não estiver logado
if (!isset($_SESSION['cpf']) || empty($_SESSION['cpf'])) {
    header("Location: index.php");
    exit();
}

// Configurações do banco de dados
$hostname = 'localhost';
$username = 'root';
$password = 'root';
$database = 'sistema_saida';

// Cria conexão
$conexao = new mysqli($hostname, $username, $password, $database);

// Verifica a conexão
if ($conexao->connect_error) {
    die("Conexão falhou: " . $conexao->connect_error);
}

// Função para obter saídas do banco de dados usando Prepared Statement
function obterSaidas($conexao) {
    $cpf_usuario = $_SESSION['cpf'];
    $query = "SELECT * FROM registros WHERE cpf_usuario = ?";
    
    $stmt = $conexao->prepare($query);
    $stmt->bind_param("s", $cpf_usuario);
    $stmt->execute();
    
    $result = $stmt->get_result();
    
    $saidas = $result->fetch_all(MYSQLI_ASSOC);

    return $saidas;
}

// Lógica para excluir saída
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['delete'])) {
    $idToDelete = $_POST['delete'];
    $deleteSql = "DELETE FROM registros WHERE id = ?";
    
    $stmt = $conexao->prepare($deleteSql);
    $stmt->bind_param("i", $idToDelete);
    $stmt->execute();
    
    // Redireciona após a exclusão para evitar reenvio do formulário ao atualizar a página
    header("Location: processar_saida.php");
    exit();
}

// Lógica para editar saída
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['edit'])) {
    $idToEdit = $_POST['edit'];

    // Obtem os detalhes do registro para preencher o formulário de edição
    $editQuery = "SELECT * FROM registros WHERE id = ?";
    $stmt = $conexao->prepare($editQuery);
    $stmt->bind_param("i", $idToEdit);
    $stmt->execute();
    $resultEdit = $stmt->get_result();

    if ($resultEdit->num_rows > 0) {
        $editData = $resultEdit->fetch_assoc();
        // Preencha as variáveis necessárias para preenchimento do formulário de edição
        $editLocal = $editData['local'];
        $editMotivo = $editData['motivo'];
        $editDataSaida = $editData['data_saida'];
        $editDataRetorno = $editData['data_retorno'];
        $editTelefoneContato = $editData['telefone_contato'];
        $editEnderecoDestino = $editData['endereco_destino'];

        // Adicione o formulário de edição no HTML
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
        </body>
        </html>
        <?php
        exit();
    }
}

// Lógica para salvar a edição
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['id_to_edit'])) {
    $idToEdit = $_POST['id_to_edit'];
    $editLocal = mysqli_real_escape_string($conexao, $_POST['local']);
    $editMotivo = mysqli_real_escape_string($conexao, $_POST['motivo']);
    $editDataSaida = mysqli_real_escape_string($conexao, $_POST['data_saida']);
    $editDataRetorno = isset($_POST['data_retorno']) ? mysqli_real_escape_string($conexao, $_POST['data_retorno']) : null;
    $editTelefoneContato = mysqli_real_escape_string($conexao, $_POST['telefone_contato']);
    $editEnderecoDestino = mysqli_real_escape_string($conexao, $_POST['endereco_destino']);

    // Validar datas (se necessário)

    // Atualizar o registro no banco de dados
    $updateSql = "UPDATE registros SET local=?, motivo=?, data_saida=?, data_retorno=?, telefone_contato=?, endereco_destino=? WHERE id=?";
    $stmt = $conexao->prepare($updateSql);
    $stmt->bind_param("ssssssi", $editLocal, $editMotivo, $editDataSaida, $editDataRetorno, $editTelefoneContato, $editEnderecoDestino, $idToEdit);
    $resultUpdate = $stmt->execute();

    if ($resultUpdate) {
        $mensagemSucesso = "Edição realizada com sucesso!";
    } else {
        $mensagemErro = "Erro ao editar saída: " . $stmt->error;
    }
}

// Obter saídas do banco de dados
$saidasCadastradas = obterSaidas($conexao);

// Obter o nome do usuário
$nomeUsuario = "";
if (isset($_SESSION['cpf'])) {
    $cpf_usuario = $_SESSION['cpf'];
    $queryNome = "SELECT nome FROM usuarios WHERE cpf = ?";
    
    $stmt = $conexao->prepare($queryNome);
    $stmt->bind_param("s", $cpf_usuario);
    $stmt->execute();
    
    $resultNome = $stmt->get_result();

    if ($resultNome->num_rows > 0) {
        $row = $resultNome->fetch_assoc();
        $nomeUsuario = $row['nome'];
    }
}
?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="css/style_saida.css">
    <title>Formulário de Saída</title>
</head>
<body>
    <form method="post" action="">
        <h2>Formulário de Saída</h2>
        <p class="welcome-msg">Bem-vindo, <?php echo $nomeUsuario; ?>! <a href="logout.php">Sair</a></p>

        <?php
        if (isset($mensagemErro)) {
            echo '<p class="error-msg">' . $mensagemErro . '</p>';
        } elseif (isset($mensagemSucesso)) {
            echo '<p class="success-msg">' . $mensagemSucesso . '</p>';
        }
        ?>

        <label for="local">Cidade/Estado/País:</label>
        <input type="text" id="local" name="local" placeholder="Informe a cidade, estado ou país" required>

        <label for="motivo">Motivo:</label>
        <textarea id="motivo" name="motivo" rows="4" placeholder="Descreva o motivo da saída" required></textarea>

        <label for="data_saida">Data de Saída:</label>
        <input type="date" id="data_saida" name="data_saida" min="<?php echo date('Y-m-d'); ?>" required>

        <label for="data_retorno">Data de Retorno:</label>
        <input type="date" id="data_retorno" name="data_retorno" min="<?php echo date('Y-m-d'); ?>">

        <label for="telefone_contato">Telefone para Contato:</label>
        <input type="tel" id="telefone_contato" name="telefone_contato" placeholder="Informe o telefone para contato">

        <label for="endereco_destino">Endereço de Destino:</label>
        <textarea id="endereco_destino" name="endereco_destino" rows="4" placeholder="Informe o endereço de destino"></textarea>

        <button type="submit">Registrar Saída</button>
    </form>

    <!-- Exibição de saídas cadastradas -->
    <h2>Saídas Cadastradas</h2>
    <table>
        <tr>
            <th>Local</th>
            <th>Motivo</th>
            <th>Data de Saída</th>
            <th>Data de Retorno</th>
            <th>Telefone para Contato</th>
            <th>Endereço de Destino</th>
            <th>Data de Registro</th>
            <th>Ação</th>
        </tr>
        <?php foreach ($saidasCadastradas as $saida): ?>
            <tr>
                <td><?php echo $saida['local']; ?></td>
                <td><?php echo $saida['motivo']; ?></td>
                <td><?php echo $saida['data_saida']; ?></td>
                <td><?php echo $saida['data_retorno']; ?></td>
                <td><?php echo $saida['telefone_contato']; ?></td>
                <td><?php echo $saida['endereco_destino']; ?></td>
                <td><?php echo $saida['data_registro']; ?></td>

                <td class="action-buttons">
                    <form method="post" action="editar_saida.php">
                        <input type="hidden" name="edit" value="<?php echo $saida['id']; ?>">
                        <button type="submit" class="edit-btn">Editar</button>
                    </form>
                    <form method="post">
                        <input type="hidden" name="delete" value="<?php echo $saida['id']; ?>">
                        <button type="submit" class="delete-btn" onclick="return confirm('Tem certeza que deseja excluir a saída?')">Excluir</button>
                    </form>
                </td>
            </tr>
        <?php endforeach; ?>
    </table>
</body>
</html>
