# Sistema de Controle de Registros - Relatório de Saídas

Este projeto é um sistema robusto de controle de registros de saídas, desenvolvido em PHP, HTML e CSS, que oferece diversas funcionalidades para facilitar a gestão e análise de informações. Com foco na praticidade e eficiência, o sistema é destinado a administradores responsáveis pelo controle e geração de relatórios de saídas.

## Funcionalidades

### Cadastro de Usuários

- **Adição de Usuários:** Registra usuários no sistema, incluindo informações cruciais como CPF, nome, senha e tipo de usuário (Super Admin ou Usuário Convencional).

- **Exclusão de Usuários:** Facilita a remoção de usuários do sistema, mantendo o controle sobre as contas ativas.

### Geração de Relatórios de Saídas

- **Filtragem por Data:** Possibilita a geração de relatórios de saídas filtrados por data de início e fim, proporcionando maior flexibilidade na análise de registros.

- **Visualização no Navegador:** Permite a visualização imediata dos relatórios no navegador, simplificando o processo de verificação.

- **Exportação em PDF:** Oferece a opção de exportar os relatórios de saídas em formato PDF, facilitando o compartilhamento e armazenamento.

- **Exportação em Planilha Excel:** Gera versões dos relatórios em planilhas Excel, proporcionando uma visão tabular dos dados para análises mais avançadas.

## Requisitos

- **PHP 7.0 ou superior**
- **MySQL ou outro banco de dados compatível**
- **Navegador Web moderno**
- **Servidor Web (por exemplo, Apache, Nginx)**

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
