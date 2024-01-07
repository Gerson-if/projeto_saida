<?php
session_start();

require 'conexao.php';

// Verificar a sessão do administrador
if (!isset($_SESSION['cpf']) || $_SESSION['tipo'] !== 'admin') {
    header("Location: index.php");
    exit();
}

// Verificar se o ID do usuário foi fornecido na URL
if (!isset($_GET['id'])) {
    header("Location: dashboard_admin.php");
    exit();
}

$id_usuario = intval($_GET['id']); // Garante que $id_usuario é um número inteiro válido

// Lógica para obter informações do usuário a ser editado
$query_usuario_editar = "SELECT * FROM usuarios WHERE id = ?";
$stmt_usuario_editar = $conexao->prepare($query_usuario_editar);
$stmt_usuario_editar->bind_param("i", $id_usuario);
$stmt_usuario_editar->execute();
$result_usuario_editar = $stmt_usuario_editar->get_result();

if ($result_usuario_editar->num_rows > 0) {
    $dados_usuario = $result_usuario_editar->fetch_assoc();
} else {
    // Usuário não encontrado
    header("Location: dashboard_admin.php");
    exit();
}

// Lógica para editar usuário
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['editar_usuario'])) {
    $novo_nome = mysqli_real_escape_string($conexao, $_POST['novo_nome']);
    $novo_cpf = mysqli_real_escape_string($conexao, $_POST['novo_cpf']);
    $novo_senha = mysqli_real_escape_string($conexao, $_POST['novo_senha']);
    $novo_tipo = mysqli_real_escape_string($conexao, $_POST['novo_tipo']);

    // Lógica para verificar se o CPF ou nome já existem (exceto para o próprio usuário)
    $verificar_existencia = "SELECT COUNT(*) AS total FROM usuarios WHERE (cpf = '$novo_cpf' OR nome = '$novo_nome') AND id <> $id_usuario";
    $resultado_existencia = $conexao->query($verificar_existencia);
    $row_existencia = $resultado_existencia->fetch_assoc();

    if ($row_existencia['total'] == 0) {
        // O CPF ou nome não existem (exceto para o próprio usuário), podemos realizar a atualização
        $query_atualizar = "UPDATE usuarios SET cpf = '$novo_cpf', nome = '$novo_nome', senha = '$novo_senha', tipo = '$novo_tipo' WHERE id = $id_usuario";
        $result_atualizar = $conexao->query($query_atualizar);

        if ($result_atualizar) {
            $mensagemEdicao = "Usuário atualizado com sucesso!";
        } else {
            $erroEdicao = "Erro ao atualizar usuário: " . $conexao->error;
        }
    } else {
        // O CPF ou nome já existem (exceto para o próprio usuário), exibir mensagem de erro
        $erroEdicao = "Erro ao atualizar usuário: CPF ou nome já cadastrado.";
    }
}
?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Editar Usuário</title>
    <link rel="stylesheet" href="css/style_editar_usuario.css">
</head>
<body>
    <div class="container">
        <h2>Editar Usuário</h2>
        <!-- Formulário para editar usuário -->
        <form method="post" action="" class="form-container">
            <label for="novo_nome">Novo Nome:</label>
            <input type="text" id="novo_nome" name="novo_nome" value="<?php echo $dados_usuario['nome']; ?>" required>
            
            <label for="novo_cpf">Novo CPF:</label>
            <input type="text" id="novo_cpf" name="novo_cpf" value="<?php echo $dados_usuario['cpf']; ?>" required>
            
            <label for="novo_senha">Nova Senha:</label>
            <input type="password" id="novo_senha" name="novo_senha">
            
            <label for="novo_tipo">Novo Tipo:</label>
            <select id="novo_tipo" name="novo_tipo">
                <option value="admin" <?php echo ($dados_usuario['tipo'] === 'admin') ? 'selected' : ''; ?>>Super Admin</option>
                <option value="usuario" <?php echo ($dados_usuario['tipo'] === 'usuario') ? 'selected' : ''; ?>>Usuário Convencional</option>
            </select>
            
            <button type="submit" name="editar_usuario">Salvar Edição</button>
        </form>

        <?php
        if (isset($mensagemEdicao)) {
            echo "<p class='success-message'>$mensagemEdicao</p>";
        } elseif (isset($erroEdicao)) {
            echo "<p class='error-message'>$erroEdicao</p>";
        }
        ?>

        <a href="dashboard_admin.php" class="back-button">Voltar e Continuar</a>
    </div>
</body>
</html>
