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
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
        }

        .notification-bar {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            background: #4caf50;
            color: #fff;
            padding: 15px;
            text-align: center;
            z-index: 1000;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            border-radius: 8px;
            animation: slideIn 0.5s ease-out;
        }

        .notification-bar.show {
            opacity: 1;
        }

        .error-message {
            color: #ff0000;
            margin-top: 10px;
        }

        @keyframes slideIn {
            from {
                transform: translateY(-100%);
            }
            to {
                transform: translateY(0);
            }
        }

        .page {
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }

        form {
            background: #fff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
        }

        label {
            display: block;
            margin-bottom: 8px;
        }

        input {
            width: 100%;
            padding: 10px;
            margin-bottom: 15px;
            box-sizing: border-box;
            border: 1px solid #ccc;
            border-radius: 4px;
        }

        .btn {
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
    <div class="notification-bar" id="notificationBar">
        Seu login e senha são os últimos 10 dígitos do seu CPF, sem o zero inicial.
    </div>

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
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function () {
            var notificationBar = document.getElementById('notificationBar');

            setTimeout(function () {
                showNotification();
                setTimeout(function () {
                    hideNotification();
                }, 5000); // Oculta a notificação após 5 segundos
            }, 1000);

            function showNotification() {
                notificationBar.style.display = 'block';
                setTimeout(function () {
                    notificationBar.classList.add('show');
                }, 10); // Adiciona a classe 'show' após um pequeno atraso
            }

            function hideNotification() {
                notificationBar.classList.remove('show');
                setTimeout(function () {
                    notificationBar.style.display = 'none';
                }, 500); // Oculta a notificação após a transição de fechamento
            }
        });
    </script>
</body>
</html>
