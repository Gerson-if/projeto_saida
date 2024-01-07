# Sistema de Controle de Registros - Relatório de Saídas

Este projeto é um sistema de controle de registros de saídas desenvolvido em PHP, HTML e CSS. Ele permite que administradores gerem relatórios de saídas filtrados por data, exportem esses relatórios em formato PDF e planilha Excel, além de realizar o cadastro e exclusão de usuários.

## Funcionalidades

- **Cadastro de Usuários:** Adiciona usuários ao sistema com informações como CPF, nome, senha e tipo de usuário (Super Admin ou Usuário Convencional).

- **Exclusão de Usuários:** Permite a exclusão de usuários do sistema.

- **Geração de Relatórios de Saídas:** Administradores podem gerar relatórios de saídas filtrados por data de início e fim. Esses relatórios podem ser visualizados no navegador, baixados em formato PDF e planilha Excel.

- **Exportação em PDF:** Possibilidade de exportar os relatórios de saídas em formato PDF para armazenamento ou compartilhamento.

- **Exportação em Planilha Excel:** Gera uma versão dos relatórios de saídas em planilha Excel para facilitar análises e manipulações adicionais.

## Requisitos

- PHP 7.0 ou superior
- MySQL ou outro banco de dados compatível
- Navegador Web moderno
- Servidor Web (por exemplo, Apache, Nginx)

## Instalação

1. Clone este repositório para o diretório do seu servidor web.

   ```bash
   git clone https://github.com/seu-usuario/seu-repositorio.git
   ```

2. Configure o banco de dados no arquivo `conexao.php`. Insira as informações corretas para se conectar ao seu banco de dados.

3. Importe o arquivo `schema.sql` para criar a estrutura do banco de dados.

   ```bash
   mysql -u seu-usuario -p sua-senha seu-banco-de-dados < schema.sql
   ```

4. Certifique-se de que o PHP e o TCPDF estão instalados no seu servidor.

   ```bash
   composer install
   ```

5. Abra o sistema em um navegador e inicie a administração dos usuários e registros de saídas.

   ```bash
   http://localhost/seu-diretorio
   ```

## Estrutura do Projeto

- `index.php`: Página de login.
- `dashboard_admin.php`: Painel de controle do administrador.
- `gerar_pdf.php`: Página para geração de relatórios em PDF.
- `tcpdf/`: Diretório contendo a biblioteca TCPDF.
- `css/`: Estilos CSS para o projeto.
- `images/`: Imagens utilizadas no projeto.
- `schema.sql`: Script SQL para criação da estrutura do banco de dados.

## Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir problemas (issues) e pull requests para melhorar o projeto.

## Licença

Este projeto está licenciado sob a Licença MIT - consulte o arquivo [LICENSE](LICENSE) para obter detalhes.