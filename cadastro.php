<?php
if ($_SERVER["REQUEST_METHOD"] == "POST") {
    require 'conexao.php';

    $cpf = $_POST['cpf'];
    $senha = $_POST['senha'];
    $tipo = $_POST['tipo'];

    $query = "INSERT INTO usuarios (cpf, senha, tipo) VALUES ('$cpf', '$senha', '$tipo')";
    $result = $conexao->query($query);

    if ($result) {
        echo "Usuário cadastrado com sucesso!";
    } else {
        echo "Erro ao cadastrar usuário: " . $conexao->error;
    }
}
?>
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <title>Cadastro</title>
</head>
<body>
    <h2>Cadastro</h2>
    <form method="post" action="">
        CPF: <input type="text" name="cpf" required><br>
        Senha: <input type="password" name="senha" required><br>
        Tipo: 
        <select name="tipo">
            <option value="admin">Super Admin</option>
            <option value="usuario">Usuário Convencional</option>
        </select><br>
        <input type="submit" value="Cadastrar">
    </form>
</body>
</html>
