<?php
session_start();

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    require 'conexao.php';

    // Usando consultas preparadas para evitar injeção de SQL
    $identidade = $_POST['Identidade'];
    $senha = $_POST['senha'];

    $query = "SELECT * FROM usuarios WHERE cpf = ? AND senha = ?";
    $stmt = $conexao->prepare($query);
    $stmt->bind_param("ss", $identidade, $senha);
    $stmt->execute();
    $result = $stmt->get_result();

    if ($result->num_rows == 1) {
        $usuario = $result->fetch_assoc();
        $_SESSION['cpf'] = $usuario['cpf'];
        $_SESSION['tipo'] = $usuario['tipo'];

        $redirect = ($_SESSION['tipo'] === 'admin') ? 'dashboard_admin.php' : 'formulario_saida.php';
        header("Location: $redirect");
        exit();
    } else {
        $erro = "Oops! Login ou senha incorretos. Tente novamente.";
    }
}

?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login Saida de Guarnição</title>
    <link rel="stylesheet" href="css/style_login.css">
</head>
<body>
    <div class="page">
        <form method="POST" class="formLogin">
            <h1>
                <img src="images/logo.png" alt="Logo1" style="height: 110px;">
            </h1>
            <p>Digite os seus dados de acesso no campo abaixo.</p>
            <label for="Identidade">Login:</label>
            <input type="text" id="Identidade" name="Identidade" placeholder="Digite seu login" required>

            <label for="senha">Senha:</label>
            <input type="password" id="senha" name="senha" placeholder="Digite sua senha" required>

            <?php if (isset($erro)) echo "<p class='error-message'>$erro</p>"; ?>

            <input type="submit" value="Entrar" class="btn">
        </form>
    </div>
</body>
</html>
