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
   git clone https://github.com/Gerson-if/projeto_saida.git
   ```

2. Configure o banco de dados no arquivo `conexao.php`. Insira as informações corretas para se conectar ao seu banco de dados.

3. Importe o arquivo `banco_original.sql` para criar a estrutura do banco de dados.

   ```bash
   mysql -u seu-usuario -p sua-senha seu-banco-de-dados < banco_orignal.sql
   ```

4. Certifique-se de que o PHP e o TCPDF estão instalados no seu servidor.

   ```bash
   composer install
   ```

5. Abra o sistema em um navegador e inicie a administração dos usuários e registros de saídas.

   ```bash
   http://localhost/saida
   ```

# 🐧 Guia de Instalação no Linux

## ⚠️ Avisos Importantes

- **Não use este script em ambientes de produção!**  
  Este script foi desenvolvido para **fins de teste ou desenvolvimento**.  
  O uso em servidores de produção pode gerar riscos de segurança, devido às permissões e configurações padrão aplicadas.  

- **Compatibilidade:**  
  O script foi **testado exclusivamente no Ubuntu 20.04**.  
  Seu funcionamento em outras versões ou distribuições **não é garantido**.

---

## 🚀 Passo a Passo da Instalação

### 1️⃣ Baixar o Script
Faça o download do arquivo `linux_saida.zip` e salve-o no diretório desejado.

---

### 2️⃣ Descompactar o Arquivo
Execute o comando abaixo para descompactar o arquivo:  
```bash
unzip linux_saida.zip
```

---

### 3️⃣ Configurar Permissões
Após a descompactação, ajuste as permissões da pasta extraída:  
```bash
chmod 777 -R pasta_descompactada
```

---

### 4️⃣ Executar o Script de Instalação
Rode o script para instalar e configurar os seguintes componentes:  
- **Apache** (servidor web)  
- **MariaDB** (banco de dados)  
- Configurações do banco de dados automaticamente aplicadas  

Comando para executar o script:  
```bash
./linux_saida_update.sh
```

> **⚠️ Importante:**  
> Certifique-se de que este script **não seja executado em servidores de produção**.  
> Ele aplica permissões amplas e configurações que podem ser inadequadas para ambientes públicos.

---

### 5️⃣ Acessar o Sistema
Após a instalação, abra o navegador e acesse o sistema em:  
```
http://localhost/saida
```

Use as credenciais padrão para login:  
- **Usuário:** `admin`  
- **Senha:** `admin_123`

---

### 6️⃣ Resolver Problemas de Permissão
Caso enfrente problemas com a escrita de relatórios ou arquivos, ajuste as permissões do diretório de saída:  
```bash
chmod 777 -R /var/www/saida/saida
```

---

### 7️⃣ Configuração do Diretório Web
O script altera o diretório padrão do Apache (`/var/www/html`) para:  
```
/var/www/saida/saida
```
Verifique e garanta que o diretório tenha as permissões adequadas para o funcionamento.

---

### 8️⃣ Instalar Interface Web para Gerenciamento de Banco de Dados
Se desejar uma interface para gerenciar o banco de dados, como o **Adminer**, siga estes passos:  

1. Baixe o arquivo do Adminer para o diretório `/var/www/saida/saida`:  
   ```bash
   cp adminer.php /var/www/saida/saida
   ```

2. (Opcional) Renomeie o arquivo para um nome mais amigável:  
   ```bash
   mv /var/www/saida/saida/adminer.php /var/www/saida/saida/admin.php
   ```

3. Ajuste as permissões:  
   ```bash
   chmod 777 -R /var/www/saida/saida/admin.php
   ```

---

### 9️⃣ Acessar o Gerenciador de Banco de Dados
Abra o navegador e acesse o gerenciador pelo endereço:  
```
http://localhost/admin.php
```

Credenciais padrão:  
- **Usuário:** `root`  
- **Senha:** `root`

---

## 🛠️ Logs e Depuração
Em caso de problemas, confira os logs do Apache:  
```bash
/var/log/apache2/error.log
```

---

## ✅ Considerações Finais

- **Segurança:**  
  Este script é para uso **somente em ambientes de teste**.  
  Não utilize em servidores públicos sem revisar e ajustar as permissões e credenciais.  

- **Compatibilidade:**  
  Testado exclusivamente no **Ubuntu 20.04**. Para outras versões ou distribuições, pode ser necessário realizar ajustes.

- **Contribuições:**  
  Caso identifique algo que possa ser melhorado, sinta-se à vontade para enviar um **Pull Request** ou abrir uma **Issue**.

---

✨ **Pronto!** Seu ambiente Linux está configurado para rodar o sistema com Apache, MariaDB e uma interface web para gerenciamento do banco de dados. Se precisar de ajuda, fique à vontade para perguntar!  
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
