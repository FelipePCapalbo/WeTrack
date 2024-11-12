import os
import psycopg2
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configuração de conexão com PostgreSQL no Neon
DATABASE_URL = "postgresql://db_WeTrack_owner:Hj3N8lMOnmFc@ep-mute-leaf-a5pr38hd-pooler.us-east-2.aws.neon.tech/db_WeTrack?sslmode=require"

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # Criação da tabela 'usuario' com PostgreSQL
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuario (
            cpf TEXT PRIMARY KEY,
            id_u TEXT NOT NULL UNIQUE,  
            nome TEXT NOT NULL,
            senha TEXT NOT NULL,
            data_u TIMESTAMP NOT NULL,
            tipo_usuario TEXT NOT NULL DEFAULT 'comum'
        )
    ''')

    # Criação da tabela 'dado' com PostgreSQL
    c.execute('''
        CREATE TABLE IF NOT EXISTS dado (
            id_d SERIAL PRIMARY KEY,
            id_u TEXT NOT NULL,
            cpf TEXT NOT NULL,
            peso REAL NOT NULL,
            timest TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            data_d DATE NOT NULL DEFAULT CURRENT_DATE,
            FOREIGN KEY (id_u) REFERENCES usuario(id_u),
            FOREIGN KEY (cpf) REFERENCES usuario(cpf)
        )
    ''')

    # Inserir o usuário Felipe Capalbo se não existir
    c.execute('''
        INSERT INTO usuario (cpf, id_u, nome, senha, data_u, tipo_usuario)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, 'administrador')
        ON CONFLICT (cpf) DO NOTHING
    ''', ('00000000000', '00000', 'Felipe Capalbo', generate_password_hash('12345')))

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
        tipo_usuario = user[5]  # Supondo que tipo_usuario é a sexta coluna
        
        if tipo_usuario == 'comum':
            session['user_id'] = user[1]
            session['tipo_usuario'] = tipo_usuario
            return redirect(url_for('pagina_principal'))  # Redireciona diretamente para usuários comuns
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

    # Testa diretamente se o hash da senha é compatível
    senha_verificada = check_password_hash(user[3], senha)

    if user and senha_verificada:
        session['user_id'] = user[1]
        session['tipo_usuario'] = user[5]
        return redirect(url_for('pagina_principal'))
    else:
        flash('CPF e/ou senha incorretos.')
        return render_template('login.html', show_password=True, cpf=cpf)

    
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

@app.route('/cadastro')
def cadastro():
    if 'user_id' in session:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        # Captura os parâmetros de ordenação
        sort = request.args.get('sort', 'id_u')  # Ordena por id_u por padrão
        order = request.args.get('order', 'asc')  # Ordena de forma ascendente por padrão

        # Mapear as colunas para evitar SQL injection, incluindo tipo_usuario
        column_map = {
            'id_u': 'id_u',
            'nome': 'nome',
            'cpf': 'cpf',
            'data_u': 'data_u',
            'tipo_usuario': 'tipo_usuario'
        }

        # Verifica se a coluna a ser ordenada está no mapa
        sort_column = column_map.get(sort, 'id_u')  # Ordena por id_u se a coluna não for válida

        # Consulta SQL com ordenação, incluindo tipo_usuario
        query = f'SELECT cpf, id_u, nome, data_u, tipo_usuario FROM usuario ORDER BY {sort_column} {order}'

        c.execute(query)
        usuarios = c.fetchall()
        conn.close()

        # Alterna entre ascendente e descendente
        new_order = 'asc' if order == 'desc' else 'desc'

        return render_template('cadastro.html', usuarios=usuarios, sort=sort, order=order, new_order=new_order)
    else:
        flash('Acesso negado.')
        return redirect(url_for('login'))

@app.route('/cadastro', methods=['POST'])
def cadastro_post():
    nome = request.form['nome']
    cpf = request.form['cpf']
    senha = request.form['senha']
    tipo_usuario = request.form.get('tipo_usuario', 'comum')
    id_u = ""  # ID do cartão vazio

    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    c.execute('SELECT * FROM usuario WHERE cpf = %s', (cpf,))
    usuario_existente = c.fetchone()

    if usuario_existente:
        flash('CPF já cadastrado. Por favor, use outro CPF.')
        return redirect(url_for('cadastro'))
    else:
        c.execute('''
            INSERT INTO usuario (cpf, id_u, nome, senha, data_u, tipo_usuario)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
        ''', (cpf, id_u, nome, generate_password_hash(senha), tipo_usuario))
        conn.commit()
        flash('Usuário cadastrado com sucesso.')

    conn.close()
    return redirect(url_for('cadastro'))

@app.route('/pesagens')
def pesagens():
    if 'user_id' in session:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        # Carregar todas as pesagens realizadas
        c.execute('SELECT * FROM dado')
        pesagens = c.fetchall()
        conn.close()

        return render_template('pesagens.html', pesagens=pesagens)
    else:
        return redirect(url_for('login'))

@app.route('/adicionar_pesagem', methods=['POST'])
def adicionar_pesagem():
    id_cartao = request.form['id_cartao']  # ID do cartão
    peso = request.form['peso']

    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # Buscar o CPF associado ao ID do cartão (id_u)
    c.execute('SELECT cpf FROM usuario WHERE id_u = %s', (id_cartao,))
    usuario_existente = c.fetchone()

    if usuario_existente:
        cpf = usuario_existente[0]
        # Inserir nova pesagem com o CPF do colhedor vinculado
        c.execute('''
            INSERT INTO dado (id_u, cpf, peso, timest, data_d)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_DATE)
        ''', (id_cartao, cpf, peso))
        conn.commit()
        flash('Pesagem adicionada com sucesso.')
    else:
        flash('Usuário não encontrado. Verifique o ID do Usuário.')

    conn.close()
    return redirect(url_for('registro_pesagem'))


@app.route('/pagina_principal', methods=['GET', 'POST'])
def pagina_principal():
    if 'user_id' in session:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        cpf = request.form.get('cpf') if session.get('tipo_usuario') == 'administrador' else session.get('user_id')
        data_inicio = request.form.get('data_inicio')
        data_fim = request.form.get('data_fim')

        query = '''
            SELECT dado.id_d, dado.id_u, dado.cpf, dado.peso, dado.timest 
            FROM dado
            WHERE 1=1
        '''
        params = []

        # Se for usuário comum, filtra pelo próprio CPF
        if session.get('tipo_usuario') == 'comum':
            query += ' AND dado.cpf = %s'
            params.append(cpf)
        elif cpf:
            query += ' AND dado.cpf = %s'
            params.append(cpf)

        if data_inicio:
            query += ' AND dado.timest >= %s'
            params.append(data_inicio)
        if data_fim:
            query += ' AND dado.timest <= %s'
            params.append(data_fim)

        query += ' ORDER BY dado.timest DESC'
        c.execute(query, params)
        pesagens = c.fetchall()
        conn.close()

        return render_template('pagina_principal.html', pesagens=pesagens)
    else:
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
            c.execute('SELECT senha FROM usuario WHERE id_u = %s', (user_id,))
            senha_armazenada = c.fetchone()[0]

            if not check_password_hash(senha_armazenada, senha_atual):
                mensagem = "A senha atual está incorreta."
            elif nova_senha != confirmar_senha:
                mensagem = "A nova senha e a confirmação não coincidem."
            else:
                nova_senha_hashed = generate_password_hash(nova_senha)
                c.execute('UPDATE usuario SET senha = %s WHERE id_u = %s', (nova_senha_hashed, user_id))
                conn.commit()
                flash('Senha alterada com sucesso.')
                return redirect(url_for('pagina_principal'))

            conn.close()
            return render_template('alterar_senha.html', mensagem=mensagem)

        return render_template('alterar_senha.html')
    else:
        flash('Você precisa estar logado para acessar esta página.')
        return redirect(url_for('login'))

@app.route('/excluir_usuario/<usuario_id>', methods=['POST'])
def excluir_usuario(usuario_id):
    if 'user_id' in session:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('DELETE FROM usuario WHERE id_u = %s', (usuario_id,))
        conn.commit()
        flash('Usuário excluído com sucesso.')
        conn.close()
    return redirect(url_for('cadastro'))


@app.route('/registro_pesagem')
def registro_pesagem():
    if 'user_id' in session:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        # Captura os parâmetros de ordenação
        sort = request.args.get('sort', 'timest')  # Ordena por timest por padrão
        order = request.args.get('order', 'desc')  # Ordena de forma decrescente por padrão

        # Mapear colunas para evitar ambiguidade
        column_map = {
            'id_d': 'dado.id_d',
            'id_u': 'dado.id_u',
            'cpf': 'dado.cpf',
            'peso': 'dado.peso',
            'timest': 'dado.timest'
        }

        # Verifica se a coluna a ser ordenada está no mapa
        sort_column = column_map.get(sort, 'dado.timest')  # Ordena por timest se a coluna não for válida

        # Consulta SQL com ordenação para todas as pesagens
        query = f'''
            SELECT dado.id_d, dado.id_u, dado.cpf, dado.peso, dado.timest
            FROM dado
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

    # Para o container da esquerda: buscar usuários sem ID_U
    c.execute("SELECT cpf, nome FROM usuario WHERE id_u IS NULL OR id_u = ''")
    usuarios_sem_vinculo = c.fetchall()

    # Para o container da direita: buscar usuários com ID_U preenchido
    c.execute("SELECT cpf, nome, id_u FROM usuario WHERE id_u IS NOT NULL AND id_u != ''")
    usuarios_com_vinculo = c.fetchall()

    # Se o método for POST (para associar um ID a um usuário)
    if request.method == 'POST':
        cpf = request.form.get('cpf_usuario')
        novo_id = request.form.get('novo_id')
        
        if cpf and novo_id:
            # Associar o novo ID ao usuário
            c.execute('UPDATE usuario SET id_u = %s WHERE cpf = %s', (novo_id, cpf))
            conn.commit()
            flash('ID associado com sucesso!')

        return redirect(url_for('vinculo_cartoes'))

    conn.close()
    return render_template('vinculo_cartoes.html', usuarios_sem_vinculo=usuarios_sem_vinculo, usuarios_com_vinculo=usuarios_com_vinculo)

@app.route('/remover_vinculo/<cpf>', methods=['POST'])
def remover_vinculo(cpf):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    
    # Remover o vínculo de ID_U do usuário (definir como string vazia "")
    c.execute("UPDATE usuario SET id_u = '' WHERE cpf = %s", (cpf,))
    conn.commit()
    conn.close()

    flash('Vínculo removido com sucesso!')
    return redirect(url_for('vinculo_cartoes'))

@app.route('/adicionar_pesagem_remota', methods=['POST'])
def adicionar_pesagem_remota():
    data = request.json  # Receber dados no formato JSON
    
    if not data or 'id_cartao' not in data or 'peso' not in data:
        return jsonify({'message': 'Dados inválidos'}), 400

    id_cartao = data['id_cartao']
    peso = data['peso']

    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # Buscar o CPF associado ao ID do cartão (id_u)
    c.execute('SELECT cpf FROM usuario WHERE id_u = %s', (id_cartao,))
    usuario_existente = c.fetchone()

    if usuario_existente:
        cpf = usuario_existente[0]
        # Inserir nova pesagem com o CPF do colhedor vinculado
        c.execute('''
            INSERT INTO dado (id_u, cpf, peso, timest, data_d)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_DATE)
        ''', (id_cartao, cpf, peso))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Pesagem registrada com sucesso'}), 201
    else:
        return jsonify({'message': 'Usuário não encontrado'}), 404


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)