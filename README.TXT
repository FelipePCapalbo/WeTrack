README - Sistema de Informações Gerenciais

Objetivo:
Sistema de gerenciamento de usuários, pesagens e cartões, com funcionalidades administrativas para controle de dados de pesagens e vinculação de cartões.

1. **Tecnologias Utilizadas**:
   - **Backend**: Flask (Python)
   - **Banco de Dados**: PostgreSQL
   - **Frontend**: HTML, CSS, JavaScript (com Flask templates)
   - **Túnel de Rede**: Ngrok (para desenvolvimento e acesso remoto)

2. **Funcionalidades**:

   2.1 **Login de Usuário**:
       - Página de login onde os usuários inserem seu CPF.
       - Se o CPF for válido, o sistema verifica o tipo de usuário (comum ou administrador) e permite o login.
       - Acesso restrito para administradores em algumas páginas, como cadastro de usuários e vinculação de cartões.

   2.2 **Página Principal**:
       - Exibe uma tabela com todas as pesagens registradas.
       - A tabela inclui colunas para ID da pesagem, ID do cartão, CPF, peso, data e horário.
       - A página tem filtros para busca por CPF, intervalo de datas e ID do cartão.
       - Funcionalidade de ordenação das colunas e paginação.

   2.3 **Cadastro de Usuários**:
       - Permite cadastrar novos usuários, informando nome, CPF e senha.
       - Administradores podem gerenciar o tipo de usuário (comum ou administrador).
       - Paginação e ordenação das listas de usuários cadastrados.

   2.4 **Registro de Pesagens**:
       - Permite registrar pesagens manualmente, associando-as a um cartão.
       - Campos necessários: ID do cartão, peso.
       - A página exibe uma tabela com as pesagens registradas e a possibilidade de ordenação e paginação.

   2.5 **Vinculação de Cartões**:
       - Permite vincular um cartão a um usuário, inserindo o CPF do usuário e o ID do cartão.
       - A página exibe os usuários já vinculados com seus cartões e permite remover vínculos.
       - Suporte a ordenação e paginação.

   2.6 **Alteração de Senha**:
       - Funcionalidade para os usuários alterarem suas senhas.
       - Requer inserção da senha atual, nova senha e confirmação da nova senha.

3. **Estrutura do Projeto**:

   3.1 **Arquivos principais**:
       - **app.py**: Script principal com as rotas do Flask e lógica de conexão com o banco de dados.
       - **app_local.py**: Versão alternativa do script `app.py`, sem o ngrok.
       - **ngrok.yml**: Arquivo de configuração do ngrok para criar um túnel remoto (usado no ambiente de desenvolvimento).
       - **templates/**: Contém as páginas HTML (login.html, cadastro.html, etc.).
       - **static/**: Contém arquivos estáticos como CSS, imagens (logo) e JavaScript.

   3.2 **Banco de Dados**:
       - **Tabela `usuario`**: Contém informações sobre os usuários (cpf, nome, senha, tipo de usuário).
       - **Tabela `usuario_cartao`**: Relaciona os usuários com os cartões vinculados (cpf, id_cartao).
       - **Tabela `pesagem`**: Registra as pesagens (id_pesagem, cpf, id_cartao, peso, data, horario).

4. **Instalação do Sistema**:

   4.1 **Pré-requisitos**:
       - **Instalar Python 3.x**: O sistema requer Python 3.10 ou superior.
       - **Instalar PostgreSQL**: Sistema de gerenciamento de banco de dados utilizado para armazenar informações.
       - **Instalar Ngrok**: O ngrok é utilizado para criar um túnel HTTPS para desenvolvimento remoto.

   4.2 **Instalando as dependências**:
       1. Clone o repositório ou baixe o código-fonte.
       2. Navegue até o diretório onde o arquivo `requirements.txt` está localizado.
       3. Execute o comando para instalar as dependências:
          ```bash
          pip install -r requirements.txt
          ```

   4.3 **Instalando o Ngrok**:
       1. Baixe o ngrok: Vá até [ngrok.com](https://ngrok.com/download) e baixe a versão apropriada para o seu sistema operacional.
       2. Extraia o arquivo e adicione o ngrok ao seu PATH ou mantenha-o na pasta do projeto.
       3. Faça login na sua conta ngrok, ou crie uma conta em [ngrok.com](https://ngrok.com).
       4. Obtenha o **authtoken** em seu painel de controle do ngrok e insira-o no arquivo `ngrok.yml` como `authtoken`.

   4.4 **Configurando o ngrok**:
       - Certifique-se de que o arquivo `ngrok.yml` esteja corretamente configurado (conforme exemplo abaixo).
       - O arquivo `ngrok.yml` pode ser encontrado no mesmo diretório que o arquivo `app.py`.
       - Exemplo de configuração no arquivo `ngrok.yml`:
         ```yaml
         version: "2"
         authtoken: 2srEgzFtBmTZCbvxvESctDXfOTP_6VmuxDiyq25YrY31yH7fk
         tunnels:
           app:
             proto: http
             addr: 5000
             hostname: lenient-greatly-chipmunk.ngrok-free.app
         ```

   4.5 **Rodando o Sistema**:
       1. Para rodar o sistema em modo local (sem ngrok), basta executar:
          ```bash
          python app_local.py
          ```
       2. Para rodar o sistema com ngrok, execute o seguinte comando:
          ```bash
          python app.py
          ```
       3. O ngrok criará um túnel para o sistema e o acesso remoto será disponibilizado através do domínio gerado, como `https://lenient-greatly-chipmunk.ngrok-free.app`.

5. **Segurança**:
   - O sistema utiliza hashes para armazenar senhas de forma segura.
   - As permissões de acesso são controladas pelo tipo de usuário (comum ou administrador).

6. **Observações**:
   - **Banco de Dados**: O sistema utiliza PostgreSQL com pool de conexões para otimizar o uso do banco de dados.
   - **Interface Responsiva**: O layout das páginas é responsivo, ajustando-se automaticamente a diferentes tamanhos de tela.
   - **Segurança**: O sistema não deve ser utilizado em produção com as configurações atuais de banco de dados e autenticação.

7. **Licença**:
   - O código-fonte é fornecido sob a licença MIT, permitindo uso, modificação e distribuição.
