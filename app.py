import os
import psycopg2
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import datetime
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configuração de conexão com PostgreSQL
DATABASE_URL = "postgresql://db_WeTrack_owner:Hj3N8lMOnmFc@ep-mute-leaf-a5pr38hd-pooler.us-east-2.aws.neon.tech/db_WeTrack?sslmode=require"

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # Criação da tabela 'usuario'
    c.execute(''' 
        CREATE TABLE IF NOT EXISTS usuario (
            cpf TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            senha TEXT NOT NULL,
            data_inclusao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            tipo_usuario TEXT NOT NULL DEFAULT 'comum'
        )
    ''')

    # Criação da tabela 'usuario_cartao' para associar cartões aos usuários
    c.execute(''' 
        CREATE TABLE IF NOT EXISTS usuario_cartao (
            cpf TEXT NOT NULL,
            id_cartao TEXT NOT NULL,
            PRIMARY KEY (cpf, id_cartao),
            FOREIGN KEY (cpf) REFERENCES usuario(cpf)
        )
    ''')

    # Criação da tabela 'pesagem'
    c.execute(''' 
        CREATE TABLE IF NOT EXISTS pesagem (
            id_pesagem SERIAL PRIMARY KEY,  -- ID da pesagem gerado automaticamente
            cpf TEXT NOT NULL,
            id_cartao TEXT NOT NULL,
            peso REAL NOT NULL,
            data DATE NOT NULL,
            horario TIME NOT NULL,
            FOREIGN KEY (cpf) REFERENCES usuario(cpf)
        )
    ''')

    # Inserir usuário inicial caso não exista
    c.execute(''' 
        INSERT INTO usuario (cpf, nome, senha, tipo_usuario)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (cpf) DO NOTHING
    ''', ('00000000000', 'Felipe Capalbo', generate_password_hash('12345'), 'administrador'))

    conn.commit()
    conn.close()

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/check_cpf', methods=['POST'])
def check_cpf():
    cpf = request.form['cpf']
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute('SELECT * FROM usuario WHERE cpf = %s', (cpf,))
    user = c.fetchone()
    conn.close()

    if user:
        tipo_usuario = user[4]  # Índice para tipo_usuario
        if tipo_usuario == 'comum':
            session['user_id'] = user[0]  # Armazenando o CPF como 'user_id'
            session['tipo_usuario'] = tipo_usuario
            return redirect(url_for('pagina_principal'))
        else:
            return render_template('login.html', show_password=True, cpf=cpf)
    else:
        flash('CPF não encontrado.')
        return redirect(url_for('login'))

@app.route('/login_post', methods=['POST'])
def login_post():
    cpf = request.form['cpf']
    senha = request.form['senha']
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute('SELECT * FROM usuario WHERE cpf = %s', (cpf,))
    user = c.fetchone()
    conn.close()

    if user:
        senha_verificada = check_password_hash(user[2], senha)  # Índice da senha
        if senha_verificada:
            session['user_id'] = user[0]  # Armazenando o CPF como 'user_id'
            session['tipo_usuario'] = user[4]  # Tipo de usuário
            return redirect(url_for('pagina_principal'))
        else:
            flash('CPF e/ou senha incorretos.')
            return render_template('login.html', show_password=True, cpf=cpf)
    else:
        flash('CPF não encontrado.')
        return redirect(url_for('login'))

@app.before_request
def restrict_pages():
    restricted_paths = ['/cadastro', '/registro_pesagem', '/vinculo_cartoes']
    if request.path in restricted_paths and session.get('tipo_usuario') != 'administrador':
        flash('Acesso negado.')
        return redirect(url_for('pagina_principal'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/cadastro', methods=['GET'])
def cadastro():
    if 'user_id' in session:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        # Captura os parâmetros de ordenação
        sort = request.args.get('sort', 'data_inclusao')  # Ordena por data_inclusao por padrão
        order = request.args.get('order', 'desc')  # Ordena de forma ascendente por padrão

        # Mapeamento de colunas
        column_map = {
            'nome': 'nome',
            'cpf': 'cpf',
            'tipo_usuario': 'tipo_usuario',
            'data_inclusao': 'data_inclusao'
        }

        # Verifica se a coluna a ser ordenada está no mapa
        sort_column = column_map.get(sort, 'data_inclusao')

        # Consulta SQL para obter as colunas desejadas
        query = f'''
            SELECT nome, cpf, tipo_usuario, data_inclusao
            FROM usuario
            ORDER BY {sort_column} {order}
        '''

        c.execute(query)
        usuarios = c.fetchall()
        conn.close()

        # Formatar a data de inclusão para exibição
        usuarios_formatados = [
            {
                'nome': usuario[0],
                'cpf': usuario[1],
                'tipo_usuario': usuario[2],
                'data_inclusao': usuario[3].strftime('%d/%m/%Y %H:%M:%S')  # Formatar data
            }
            for usuario in usuarios
        ]

        # Alterna entre ascendente e descendente
        new_order = 'asc' if order == 'desc' else 'desc'

        return render_template('cadastro.html', usuarios=usuarios_formatados, sort=sort, order=order, new_order=new_order)
    else:
        flash('Acesso negado.')
        return redirect(url_for('login'))

@app.route('/cadastro', methods=['POST'])
def cadastro_post():
    nome = request.form['nome']
    cpf = request.form['cpf']
    senha = request.form['senha']
    tipo_usuario = request.form.get('tipo_usuario', 'comum')

    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # Verifica se o CPF já está cadastrado
    c.execute('SELECT * FROM usuario WHERE cpf = %s', (cpf,))
    usuario_existente = c.fetchone()

    if usuario_existente:
        flash('CPF já cadastrado. Por favor, use outro CPF.')
        return redirect(url_for('cadastro'))
    else:
        c.execute(''' 
            INSERT INTO usuario (cpf, nome, senha, tipo_usuario) 
            VALUES (%s, %s, %s, %s)
        ''', (cpf, nome, generate_password_hash(senha), tipo_usuario))
        conn.commit()
        flash('Usuário cadastrado com sucesso.')
        conn.close()
        return redirect(url_for('cadastro'))

@app.route('/pesagens')
def pesagens():
    if 'user_id' in session:
        cpf = session['user_id']  # Obtém o cpf da sessão
        data_inicio = request.form.get('data_inicio')
        data_fim = request.form.get('data_fim')

        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        query = '''
            SELECT pesagem.cpf, pesagem.id_cartao, pesagem.peso, pesagem.data, pesagem.horario 
            FROM pesagem
            WHERE pesagem.cpf = %s
        '''
        params = [cpf]

        if data_inicio:
            query += ' AND pesagem.data >= %s'
            params.append(data_inicio)
        if data_fim:
            query += ' AND pesagem.data <= %s'
            params.append(data_fim)

        query += ' ORDER BY pesagem.data DESC, pesagem.horario DESC'
        c.execute(query, params)

        pesagens = c.fetchall()
        conn.close()

        return render_template('pesagens.html', pesagens=pesagens)
    else:
        return redirect(url_for('login'))

@app.route('/adicionar_pesagem', methods=['POST'])
def adicionar_pesagem():
    id_cartao = request.form['id_cartao']
    peso = request.form['peso']

    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # Verificar se o id_cartao está associado a algum CPF
    c.execute('SELECT cpf FROM usuario_cartao WHERE id_cartao = %s', (id_cartao,))
    usuario_existente = c.fetchone()

    if usuario_existente:
        cpf = usuario_existente[0]
        c.execute(''' 
            INSERT INTO pesagem (cpf, id_cartao, peso, data, horario)
            VALUES (%s, %s, %s, CURRENT_DATE, CURRENT_TIME)
        ''', (cpf, id_cartao, peso))
        conn.commit()
        flash('Pesagem adicionada com sucesso.')
    else:
        flash('Cartão não encontrado. Verifique o ID do Cartão.')

    conn.close()
    return redirect(url_for('registro_pesagem'))

@app.route('/pagina_principal', methods=['GET', 'POST'])
def pagina_principal():
    if 'user_id' in session:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        # Obtendo as datas de filtro via GET
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')

        # Consulta base para todas as pesagens com a ID da pesagem
        query = '''
            SELECT 
                ROW_NUMBER() OVER () AS id_pesagem,  -- ID gerado automaticamente para a pesagem
                pesagem.id_cartao, 
                pesagem.cpf, 
                pesagem.peso, 
                pesagem.data, 
                pesagem.horario 
            FROM pesagem
        '''
        params = []

        # Adiciona filtros de data, se fornecidos
        if data_inicio:
            query += ' WHERE pesagem.data >= %s'
            params.append(data_inicio)
        if data_fim:
            # Adiciona filtro para data fim, com "AND" para o caso de já ter sido adicionado o filtro de início
            if 'WHERE' in query:
                query += ' AND pesagem.data <= %s'
            else:
                query += ' WHERE pesagem.data <= %s'
            params.append(data_fim)

        # Ordenando por data e horário
        query += ' ORDER BY pesagem.data DESC, pesagem.horario DESC'

        # Executando a consulta
        c.execute(query, params)
        pesagens = c.fetchall()

        conn.close()

        # Passando os dados para o template
        return render_template('pagina_principal.html', pesagens=pesagens)

    else:
        # Caso o usuário não esteja logado, redireciona para a página de login
        return redirect(url_for('login'))

    
@app.route('/alterar_senha', methods=['GET', 'POST'])
def alterar_senha():
    if 'user_id' in session:
        if request.method == 'POST':
            senha_atual = request.form['senha_atual']
            nova_senha = request.form['nova_senha']
            confirmar_senha = request.form['confirmar_senha']
            user_id = session['user_id']

            conn = psycopg2.connect(DATABASE_URL)
            c = conn.cursor()
            c.execute('SELECT senha FROM usuario WHERE cpf = %s', (user_id,))
            senha_armazenada = c.fetchone()[0]

            if not check_password_hash(senha_armazenada, senha_atual):
                flash("A senha atual está incorreta.")
            elif nova_senha != confirmar_senha:
                flash("As novas senhas não coincidem.")
            else:
                c.execute('UPDATE usuario SET senha = %s WHERE cpf = %s',
                          (generate_password_hash(nova_senha), user_id))
                conn.commit()
                flash("Senha alterada com sucesso.")
            conn.close()

        return render_template('alterar_senha.html')
    else:
        return redirect(url_for('login'))
    
@app.route('/excluir_usuario/<usuario_id>', methods=['POST'])
def excluir_usuario(usuario_id):
    if 'user_id' in session:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('DELETE FROM usuario WHERE cpf = %s', (usuario_id,))
        conn.commit()
        flash('Usuário excluído com sucesso.')
        conn.close()
    return redirect(url_for('cadastro'))


@app.route('/registro_pesagem', methods=['GET', 'POST'])
def registro_pesagem():
    if 'user_id' in session:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        # Captura os parâmetros de ordenação
        sort = request.args.get('sort', 'data')  # Ordena por 'data' por padrão
        order = request.args.get('order', 'desc')  # Ordena de forma descendente por padrão

        # Mapeamento de colunas para ordenação
        column_map = {
            'cpf': 'cpf', 
            'nome': 'nome',
            'tipo_usuario': 'tipo_usuario',
            'data': 'data',
            'peso': 'peso',
            'horario': 'horario'
        }

        # Captura a coluna para ordenação
        sort_column = column_map.get(sort, 'data')  # Ordena por 'data' por padrão

        # Consulta SQL com ordenação para todas as pesagens
        query = f'''
            SELECT pesagem.cpf, pesagem.id_cartao, pesagem.peso, pesagem.data, pesagem.horario
            FROM pesagem
            ORDER BY {sort_column} {order}
        '''

        c.execute(query)
        pesagens = c.fetchall()
        conn.close()

        # Alterna entre ascendente e descendente
        new_order = 'asc' if order == 'desc' else 'desc'

        return render_template('registro_pesagem.html', pesagens=pesagens, sort=sort, order=order, new_order=new_order)
    else:
        flash('Você precisa estar logado para acessar esta página.')
        return redirect(url_for('login'))

@app.route('/vinculo_cartoes', methods=['GET', 'POST'])
def vinculo_cartoes():
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # Buscar todos os usuários (independentemente de já terem cartões vinculados ou não)
    c.execute("SELECT cpf, nome FROM usuario")
    todos_usuarios = c.fetchall()

    # Buscar usuários com cartões vinculados e agrupá-los
    c.execute("""SELECT u.cpf, u.nome, ARRAY_AGG(c.id_cartao) AS cartoes_vinculados 
                 FROM usuario u 
                 LEFT JOIN usuario_cartao c ON u.cpf = c.cpf 
                 GROUP BY u.cpf, u.nome""")
    usuarios_com_vinculo = c.fetchall()  # Agora a variável está corretamente definida

    # Se o método for POST (para associar um ID a um usuário)
    if request.method == 'POST':
        cpf = request.form.get('cpf_usuario')
        novo_id = request.form.get('novo_id')

        if cpf and novo_id:
            # Verifica se o cartão "novo_id" já está associado ao mesmo CPF
            c.execute("SELECT * FROM usuario_cartao WHERE cpf = %s AND id_cartao = %s", (cpf, novo_id))
            cartao_existente = c.fetchone()

            if cartao_existente:
                flash('Este cartão já está vinculado a este usuário.')
            else:
                # Associar o novo ID ao usuário na tabela usuario_cartao
                c.execute("INSERT INTO usuario_cartao (cpf, id_cartao) VALUES (%s, %s)", (cpf, novo_id))
                conn.commit()
                flash('Cartão associado com sucesso!')

        # Após o POST, a página será recarregada para refletir as alterações
        return redirect(url_for('vinculo_cartoes'))

    conn.close()
    return render_template(
        'vinculo_cartoes.html',
        usuarios_sem_vinculo=todos_usuarios,  # Exibindo todos os usuários
        usuarios_com_vinculo=usuarios_com_vinculo  # Variável agora corretamente definida
    )

@app.route('/remover_vinculo/<cpf>/<id_cartao>', methods=['POST'])
def remover_vinculo(cpf, id_cartao):
    if request.method == 'POST':
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        # Remover o vínculo de cartão específico para o CPF especificado
        c.execute(''' 
            DELETE FROM usuario_cartao WHERE cpf = %s AND id_cartao = %s
        ''', (cpf, id_cartao))
        conn.commit()
        conn.close()

        flash('Vínculo removido com sucesso!')
        return redirect(url_for('vinculo_cartoes'))
    else:
        flash('Método inválido para remoção de vínculo.')
        return redirect(url_for('vinculo_cartoes'))

def obter_cpf_por_cartao(id_cartao):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # Buscar o CPF associado ao id_cartao
    c.execute('''
        SELECT cpf FROM usuario_cartao WHERE id_cartao = %s
    ''', (id_cartao,))

    cpf = c.fetchone()
    conn.close()

    if cpf:
        return cpf[0]
    else:
        raise ValueError(f"Cartão {id_cartao} não encontrado.")


@app.route('/adicionar_pesagem_remota', methods=['POST'])
def adicionar_pesagem_remota():
    data = request.get_json()  # Recebe o JSON enviado pela requisição

    id_cartao = data.get('id_cartao')
    peso = data.get('peso')
    data_pesagem = data.get('data')  # A data no formato "1/11/2024"
    horario = data.get('horario')    # O horário no formato "14:21:55"

    # Converter a data para o formato DATE
    data_pesagem = datetime.strptime(data_pesagem, "%d/%m/%Y").date()

    # Converter o horário para o formato TIME
    horario = datetime.strptime(horario, "%H:%M:%S").time()

    # Obter o CPF do usuário vinculado ao id_cartao
    cpf_usuario = obter_cpf_por_cartao(id_cartao)

    # Inserir os dados da pesagem no banco
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    c.execute(''' 
        INSERT INTO pesagem (cpf, id_cartao, peso, data, horario)
        VALUES (%s, %s, %s, %s, %s)
    ''', (cpf_usuario, id_cartao, peso, data_pesagem, horario))

    conn.commit()
    conn.close()

    return jsonify({"message": "Pesagem registrada com sucesso!"}), 200

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
