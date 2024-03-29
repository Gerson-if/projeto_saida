<?php
session_start();

require 'conexao.php';

// Verificar a sessão do administrador
if (!isset($_SESSION['cpf']) || $_SESSION['tipo'] !== 'admin') {
    header("Location: index.php");
    exit();
}

// Verificar se o formulário de logout foi submetido
if (isset($_POST['logout'])) {
    // Faz logout e destrói a sessão
    session_unset();
    session_destroy();

    // Força a expiração do cookie da sessão
    setcookie(session_name(), '', time() - 3600, '/');

    // Redireciona para a página de login após o logout
    header("Location: index.php");
    exit();
}

// Lógica para cadastrar usuário
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['cpf_cadastro'], $_POST['senha_cadastro'], $_POST['tipo_cadastro'], $_POST['nome_cadastro'])) {
    $cpf_cadastro = mysqli_real_escape_string($conexao, $_POST['cpf_cadastro']);
    $senha_cadastro = mysqli_real_escape_string($conexao, $_POST['senha_cadastro']);
    $tipo_cadastro = mysqli_real_escape_string($conexao, $_POST['tipo_cadastro']);
    $nome_cadastro = mysqli_real_escape_string($conexao, $_POST['nome_cadastro']);

    // Verificar se o CPF ou nome já existem
    $verificar_existencia = "SELECT COUNT(*) AS total FROM usuarios WHERE cpf = '$cpf_cadastro' OR nome = '$nome_cadastro'";
    $resultado_existencia = $conexao->query($verificar_existencia);
    $row_existencia = $resultado_existencia->fetch_assoc();

    if ($row_existencia['total'] == 0) {
        // O CPF ou nome não existem, podemos realizar a inserção
        $query_cadastro = "INSERT INTO usuarios (cpf, senha, tipo, nome) VALUES ('$cpf_cadastro', '$senha_cadastro', '$tipo_cadastro', '$nome_cadastro')";
        $result_cadastro = $conexao->query($query_cadastro);

        if ($result_cadastro) {
            $mensagemCadastro = "Usuário cadastrado com sucesso!";
        } else {
            $erroCadastro = "Erro ao cadastrar usuário: " . $conexao->error;
        }
    } else {
        // O CPF ou nome já existem, exibir mensagem de erro
        $erroCadastro = "Erro ao cadastrar usuário: CPF ou nome já cadastrado.";
    }
}

// Lógica para obter usuários
$query_usuarios = "SELECT * FROM usuarios";
$result_usuarios = $conexao->query($query_usuarios);

// Lógica para excluir usuário
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['delete_usuario'])) {
    $idToDelete = $_POST['delete_usuario'];
    $deleteSql = "DELETE FROM usuarios WHERE id = ?";
    $stmt = $conexao->prepare($deleteSql);
    $stmt->bind_param("i", $idToDelete);
    $stmt->execute();

    // Atualiza o array de usuários
    $result_usuarios = $conexao->query($query_usuarios);
}

?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel de Administração</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link rel="stylesheet" href="css/style_admin.css">
</head>
<body>

    <div class="container">
        <h2>Cadastrar Usuário</h2>
        <form method="post" action="" class="form-container">
            <input type="text" name="nome_cadastro" placeholder="Nome" required>
            <input type="text" name="cpf_cadastro" placeholder="CPF" required>
            <input type="password" name="senha_cadastro" placeholder="Senha" required>
            <select name="tipo_cadastro">
                <option value="admin">Super Admin</option>
                <option value="usuario">Usuário Convencional</option>
            </select>
            <br><br>
            <button type="submit" class="btn-cadastrar">Cadastrar Usuário</button>
        </form>
        <hr>

        <?php
        if (isset($mensagemCadastro)) {
            echo "<p class='success-message'>$mensagemCadastro</p>";
        } elseif (isset($erroCadastro)) {
            echo "<p class='error-message'>$erroCadastro</p>";
        }
        ?>

        <h2>Relatório de Saídas Por Periodo</h2>

         <!-- Botão para gerar PDF -->
        <a href="gerar_pdf.php" target="_self">
            <button>Gerar PDF ou Planilha Por Periodo</button>
        </a>

        <br>
        <br>
        <hr>
        
        <h2>Relatório de Saída Por Data Exata</h2>

         <!-- Botão para gerar PDF -->
        <a href="busca_exata.php" target="_self">
            <button>Gerar PDF ou Planilha Data Exata</button>
        </a>
        <br>
        <br>
        <hr>
        <h2>Excluir e Editar Usuário</h2>
        <!-- Lista de usuários com opção para excluir -->
        <div class="search-bar">
            <input type="text" id="searchUserInputLive" placeholder="Buscar por Nome ou CPF">
            <button onclick="searchUsersLive()">Buscar</button>
       </div>
            <!-- Adicione este script abaixo da sua barra de pesquisa -->
            <script>
                function searchUsersLive() {
                    var input, filter, table, tr, td, i, txtValue;
                    input = document.getElementById("searchUserInputLive");
                    filter = input.value.toUpperCase();
                    table = document.querySelector("table");
                    tr = table.getElementsByTagName("tr");

                    for (i = 0; i < tr.length; i++) {
                        td = tr[i].getElementsByTagName("td")[2]; // Index 2 corresponds to the 'Nome' column
                        if (td) {
                            txtValue = td.textContent || td.innerText;
                            if (txtValue.toUpperCase().indexOf(filter) > -1) {
                                tr[i].style.display = "";
                            } else {
                                tr[i].style.display = "none";
                            }
                        }
                    }
                }

                // Adicione este evento no input da barra de pesquisa
                document.getElementById("searchUserInputLive").addEventListener("keyup", function() {
                    searchUsersLive();
                });
            </script>
        <table>
            <tr>
                <th>ID</th>
                <th>CPF</th>
                <th>Nome</th>
                <th>Tipo</th>
                <th>Ações</th>
            </tr>
            <?php
            while ($row = $result_usuarios->fetch_assoc()) {
                echo "<tr>
                        <td>{$row['id']}</td>
                        <td>{$row['cpf']}</td>
                        <td>{$row['nome']}</td>
                        <td>{$row['tipo']}</td>
                        <td>
                            <a href='editar_usuario.php?id={$row['id']}'>Editar</a> |
                            <form method='post' style='display:inline;'>
                                <input type='hidden' name='delete_usuario' value='{$row['id']}'>
                                <button type='submit' onclick=\"return confirm('Tem certeza que deseja excluir o usuário?')\">Excluir</button>
                            </form>
                        </td>
                    </tr>";
            }
            ?>
        </table>
        <br><br><br><br><br><br><br><br><br><br><br><br><br><br>

        <!-- Formulário de logout -->
        <button class="logout-button" onclick="document.querySelector('.container form[name=logoutForm]').submit()">Sair</button>
        <form method="post" action="" name="logoutForm">
            <input type="hidden" name="logout" value="1">
        </form>

    </div>

    <script>
        function searchUsers() {
            var input, filter, table, tr, td, i, txtValue;
            input = document.getElementById("searchUserInput");
            filter = input.value.toUpperCase();
            table = document.querySelector("table");
            tr = table.getElementsByTagName("tr");

            for (i = 0; i < tr.length; i++) {
                td = tr[i].getElementsByTagName("td")[2]; // Index 2 corresponds to the 'Nome' column
                if (td) {
                    txtValue = td.textContent || td.innerText;
                    if (txtValue.toUpperCase().indexOf(filter) > -1) {
                        tr[i].style.display = "";
                    } else {
                        tr[i].style.display = "none";
                    }
                }
            }
        }
    </script>
</body>
</html>

