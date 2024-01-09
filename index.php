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
        $erro = "Oops! Login ou senha incorretos. Verifique se o CPF está correto e tente novamente.";
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
    <style>
        /* Adicione isso ao seu arquivo de estilo (style_login.css) ou crie um novo arquivo CSS */
        .popup-container {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            justify-content: center;
            align-items: center;
            z-index: 999;
        }

        .popup-content {
            background: #fff;
            padding: 20px;
            border-radius: 5px;
            text-align: center;
            max-width: 400px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.2);
        }

        .error-message {
            color: #ff0000;
            margin-top: 10px;
        }

        .btn-popup {
            background-color: #4caf50;
            color: #fff;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="page">
        <form method="POST" class="formLogin">
            <h1>
                <img src="images/logo.png" alt="Logo1" style="height: 110px;">
            </h1>
            <p>Digite os seus dados de acesso abaixo.</p>
            <label for="Identidade">CPF (sem o zero inicial):</label>
            <input type="text" id="Identidade" name="Identidade" placeholder="Digite seu CPF" required>

            <label for="senha">Senha:</label>
            <input type="password" id="senha" name="senha" placeholder="Digite sua senha" required>

            <?php if (isset($erro)) echo "<p class='error-message'>$erro</p>"; ?>

            <input type="submit" value="Entrar" class="btn">
        </form>

        <div class="popup-container" id="popupContainer">
            <div class="popup-content">
                <span class="close-popup" onclick="closePopup()">&times;</span>
                <p>Seu login e senha são os últimos 10 dígitos do seu CPF, sem o zero inicial.</p>
                <button class="btn-popup" onclick="closePopup()">OK</button>
            </div>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function () {
            var popupContainer = document.getElementById('popupContainer');

            setTimeout(function () {
                showPopup();
            }, 1000);

            function showPopup() {
                popupContainer.style.display = 'flex';
            }

            window.closePopup = function () {
                popupContainer.style.display = 'none';
            };
        });
    </script>
</body>
</html>
