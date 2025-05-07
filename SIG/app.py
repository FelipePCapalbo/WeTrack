import os
import subprocess
import threading
import time
import psycopg2
from psycopg2 import pool
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, Response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import datetime
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import shutil
import sys


# Inicialização do Flask
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configuração de Logs
handler = RotatingFileHandler('app.log', maxBytes=1000000, backupCount=5)
handler.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
)
handler.setFormatter(formatter)
app.logger.addHandler(handler)

# Configuração do Flask-Limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# Configuração do pool de conexões com PostgreSQL
DATABASE_URL = "postgresql://db_WeTrack_owner:Hj3N8lMOnmFc@ep-mute-leaf-a5pr38hd-pooler.us-east-2.aws.neon.tech/db_WeTrack?sslmode=require"
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)
    if db_pool:
        app.logger.info("Pool de conexões criado com sucesso")
except (Exception, psycopg2.DatabaseError) as error:
    app.logger.error(f"Erro ao criar pool de conexões: {error}")
    raise

def init_db():
    conn = db_pool.getconn()
    try:
        c = conn.cursor()
        # Criação da tabela de usuários
        c.execute(''' 
            CREATE TABLE IF NOT EXISTS usuario (
                cpf TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                senha TEXT NOT NULL,
                data_inclusao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                tipo_usuario TEXT NOT NULL DEFAULT 'comum'
            )
        ''')
        # Criação da tabela para associação de cartões
        c.execute(''' 
            CREATE TABLE IF NOT EXISTS usuario_cartao (
                cpf TEXT NOT NULL,
                id_cartao TEXT NOT NULL,
                PRIMARY KEY (cpf, id_cartao),
                FOREIGN KEY (cpf) REFERENCES usuario(cpf)
            )
        ''')
        # Criação da tabela de pesagens
        c.execute(''' 
            CREATE TABLE IF NOT EXISTS pesagem (
                id_pesagem SERIAL PRIMARY KEY,
                cpf TEXT NOT NULL,
                id_cartao TEXT NOT NULL,
                peso REAL NOT NULL,
                data DATE NOT NULL,
                horario TIME NOT NULL,
                FOREIGN KEY (cpf) REFERENCES usuario(cpf)
            )
        ''')
        # Inserir usuário inicial (caso não exista)
        c.execute(''' 
            INSERT INTO usuario (cpf, nome, senha, tipo_usuario)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (cpf) DO NOTHING
        ''', ('00000000000', 'Felipe Capalbo', generate_password_hash('12345'), 'administrador'))
        # Inserir cartão inicial (caso não exista)
        c.execute(''' 
            INSERT INTO usuario_cartao (cpf, id_cartao)
            VALUES (%s, %s)
            ON CONFLICT (cpf, id_cartao) DO NOTHING
        ''', ('00000000000', 'BFBA5A'))
        conn.commit()
        app.logger.info("Banco de dados inicializado com sucesso")
    except Exception as e:
        app.logger.error(f"Erro durante a inicialização do banco de dados: {e}")
    finally:
        db_pool.putconn(conn)

# Funções para integração com NGROK via subprocess

def localizar_ngrok():
    # Tenta encontrar o executável no PATH
    ngrok_path = shutil.which("ngrok")
    if ngrok_path:
        return ngrok_path

    # Se não estiver no PATH, tenta caminhos padrão conforme o sistema
    if sys.platform.startswith("win"):
        caminhos_possiveis = [
            r"C:\ngrok\ngrok.exe",
            os.path.expanduser("~\\ngrok\\ngrok.exe"),
            os.path.join(os.getcwd(), "ngrok.exe"),
        ]
    else:
        caminhos_possiveis = [
            "/usr/local/bin/ngrok",
            os.path.expanduser("~/ngrok"),
            os.path.join(os.getcwd(), "ngrok"),
        ]

    for caminho in caminhos_possiveis:
        if os.path.exists(caminho) and os.access(caminho, os.X_OK):
            return caminho

    raise FileNotFoundError("O executável 'ngrok' não foi encontrado. Adicione ao PATH ou especifique o caminho.")

def localizar_configuracao_ngrok():
    arquivo_ngrok = "ngrok.yml"
    if os.path.exists(arquivo_ngrok):
        return os.path.abspath(arquivo_ngrok)
    else:
        raise FileNotFoundError("O arquivo ngrok.yml não foi encontrado.")

def start_ngrok():
    try:
        ngrok_path = localizar_ngrok()
        config_path = localizar_configuracao_ngrok()
        subprocess.run([ngrok_path, "start", "--config", config_path, "app"], check=True)
    except Exception as e:
        print(f"Erro ao iniciar o Ngrok: {e}")

# Rotas do sistema

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/check_cpf', methods=['POST'])
def check_cpf():
    cpf = request.form['cpf']
    conn = db_pool.getconn()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM usuario WHERE cpf = %s', (cpf,))
        user = c.fetchone()
    except Exception as e:
        app.logger.error(f"Erro ao verificar CPF: {e}")
        flash('Erro interno do servidor.')
        return redirect(url_for('login'))
    finally:
        db_pool.putconn(conn)
    if user:
        tipo_usuario = user[4]
        if tipo_usuario == 'comum':
            session['user_id'] = user[0]
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
    conn = db_pool.getconn()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM usuario WHERE cpf = %s', (cpf,))
        user = c.fetchone()
    except Exception as e:
        app.logger.error(f"Erro ao realizar login: {e}")
        flash('Erro interno do servidor.')
        return redirect(url_for('login'))
    finally:
        db_pool.putconn(conn)
    if user:
        if check_password_hash(user[2], senha):
            session['user_id'] = user[0]
            session['tipo_usuario'] = user[4]
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
        conn = db_pool.getconn()
        try:
            c = conn.cursor()
            sort = request.args.get('sort', 'cpf')
            order = request.args.get('order', 'asc')
            new_order = 'asc' if order == 'desc' else 'desc'
            page = request.args.get('page', 1, type=int)
            limit = 25
            offset = (page - 1) * limit
            column_map = {
                'nome': 'nome',
                'cpf': 'cpf',
                'tipo_usuario': 'tipo_usuario',
                'data_inclusao': 'data_inclusao'
            }
            sort_column = column_map.get(sort, 'cpf')
            query = f'''
                SELECT nome, cpf, tipo_usuario, data_inclusao
                FROM usuario
                ORDER BY {sort_column} {order}
                LIMIT %s OFFSET %s
            '''
            c.execute(query, (limit+1, offset))
            usuarios = c.fetchall()
            has_next = len(usuarios) > limit
            usuarios = usuarios[:limit]
        except Exception as e:
            app.logger.error(f"Erro ao buscar usuários: {e}")
            flash('Erro interno do servidor.')
            return redirect(url_for('pagina_principal'))
        finally:
            db_pool.putconn(conn)
        usuarios_formatados = [
            {
                'nome': usuario[0],
                'cpf': usuario[1],
                'tipo_usuario': usuario[2],
                'data_inclusao': usuario[3].strftime('%d/%m/%Y %H:%M:%S')
            }
            for usuario in usuarios
        ]
        return render_template('cadastro.html', usuarios=usuarios_formatados,
                               sort=sort, order=order, new_order=new_order,
                               page=page, has_next=has_next)
    else:
        flash('Acesso negado.')
        return redirect(url_for('login'))

@app.route('/cadastro', methods=['POST'])
def cadastro_post():
    nome = request.form['nome']
    cpf = request.form['cpf']
    senha = request.form['senha']
    tipo_usuario = request.form.get('tipo_usuario', 'comum')
    conn = db_pool.getconn()
    try:
        c = conn.cursor()
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
            return redirect(url_for('cadastro'))
    except Exception as e:
        app.logger.error(f"Erro ao cadastrar usuário: {e}")
        flash('Erro interno do servidor.')
        return redirect(url_for('cadastro'))
    finally:
        db_pool.putconn(conn)

@app.route('/pesagens', methods=['GET', 'POST'])
def pesagens():
    if 'user_id' in session:
        cpf = session['user_id']
        sort = request.args.get('sort', 'id_pesagem')
        order = request.args.get('order', 'asc')
        new_order = 'asc' if order == 'desc' else 'desc'
        page = request.args.get('page', 1, type=int)
        limit = 25
        offset = (page - 1) * limit
        column_map = {
            'id_pesagem': 'id_pesagem',
            'id_cartao': 'id_cartao',
            'peso': 'peso',
            'data': 'data',
            'horario': 'horario'
        }
        sort_column = column_map.get(sort, 'id_pesagem')
        data_inicio = request.values.get('data_inicio')
        data_fim = request.values.get('data_fim')
        query = '''
            SELECT id_pesagem, cpf, id_cartao, peso, data, horario 
            FROM pesagem
            WHERE cpf = %s
        '''
        params = [cpf]
        if data_inicio:
            query += ' AND data >= %s'
            params.append(data_inicio)
        if data_fim:
            query += ' AND data <= %s'
            params.append(data_fim)
        query += f' ORDER BY {sort_column} {order} LIMIT %s OFFSET %s'
        params.extend([limit+1, offset])
        conn = db_pool.getconn()
        try:
            c = conn.cursor()
            c.execute(query, params)
            pesagens_data = c.fetchall()
            has_next = len(pesagens_data) > limit
            pesagens_data = pesagens_data[:limit]
        except Exception as e:
            app.logger.error(f"Erro ao buscar pesagens: {e}")
            flash('Erro interno do servidor.')
            return redirect(url_for('pagina_principal'))
        finally:
            db_pool.putconn(conn)
        return render_template('pesagens.html', pesagens=pesagens_data,
                               sort=sort, order=order, new_order=new_order,
                               page=page, has_next=has_next)
    else:
        return redirect(url_for('login'))

@app.route('/adicionar_pesagem', methods=['POST'])
def adicionar_pesagem():
    id_cartao = request.form['id_cartao']
    peso = request.form['peso']
    conn = db_pool.getconn()
    try:
        c = conn.cursor()
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
    except Exception as e:
        app.logger.error(f"Erro ao adicionar pesagem: {e}")
        flash('Erro interno do servidor.')
    finally:
        db_pool.putconn(conn)
    return redirect(url_for('registro_pesagem'))

@app.route('/pagina_principal', methods=['GET'])
def pagina_principal():
    if 'user_id' in session:
        cpf_filter = request.args.get('cpf')
        id_cartao_filter = request.args.get('id_cartao')
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')
        sort = request.args.get('sort', 'id_pesagem')
        order = request.args.get('order', 'desc')
        new_order = 'asc' if order == 'desc' else 'desc'
        page = request.args.get('page', 1, type=int)
        limit = 25
        offset = (page - 1) * limit

        column_map = {
            'id_pesagem': 'id_pesagem',
            'id_cartao': 'id_cartao',
            'cpf': 'cpf',
            'peso': 'peso',
            'data': 'data',
            'horario': 'horario'
        }
        sort_column = column_map.get(sort, 'id_pesagem')
        query = 'SELECT id_pesagem, id_cartao, cpf, peso, data, horario FROM pesagem'
        params = []
        conditions = []
        if id_cartao_filter:
            conditions.append(" id_cartao = %s")
            params.append(id_cartao_filter)
        if cpf_filter:
            conditions.append(" cpf = %s")
            params.append(cpf_filter)
        if data_inicio:
            conditions.append(" data >= %s")
            params.append(data_inicio)
        if data_fim:
            conditions.append(" data <= %s")
            params.append(data_fim)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f' ORDER BY {sort_column} {order} LIMIT %s OFFSET %s'
        params.extend([limit+1, offset])
        conn = db_pool.getconn()
        try:
            c = conn.cursor()
            c.execute(query, params)
            pesagens = c.fetchall()
            has_next = len(pesagens) > limit
            pesagens = pesagens[:limit]
        except Exception as e:
            app.logger.error(f"Erro ao buscar pesagens na página principal: {e}")
            flash('Erro interno do servidor.')
            return redirect(url_for('pagina_principal'))
        finally:
            db_pool.putconn(conn)
        return render_template('pagina_principal.html',
                               pesagens=pesagens,
                               sort=sort,
                               order=order,
                               new_order=new_order,
                               page=page,
                               has_next=has_next)
    else:
        return redirect(url_for('login'))

@app.route('/registro_pesagem', methods=['GET', 'POST'])
def registro_pesagem():
    if 'user_id' in session:
        sort = request.args.get('sort', 'id_pesagem')
        order = request.args.get('order', 'asc')
        new_order = 'asc' if order == 'desc' else 'desc'
        page = request.args.get('page', 1, type=int)
        limit = 25
        offset = (page - 1) * limit
        column_map = {
            'id_pesagem': 'id_pesagem',
            'id_cartao': 'id_cartao',
            'cpf': 'cpf',
            'peso': 'peso',
            'data': 'data',
            'horario': 'horario'
        }
        sort_column = column_map.get(sort, 'id_pesagem')
        query = f'''
            SELECT id_pesagem, cpf, id_cartao, peso, data, horario
            FROM pesagem
            ORDER BY {sort_column} {order}
            LIMIT %s OFFSET %s
        '''
        conn = db_pool.getconn()
        try:
            c = conn.cursor()
            c.execute(query, (limit+1, offset))
            pesagens = c.fetchall()
            has_next = len(pesagens) > limit
            pesagens = pesagens[:limit]
        except Exception as e:
            app.logger.error(f"Erro ao registrar pesagem: {e}")
            flash('Erro interno do servidor.')
            return redirect(url_for('pagina_principal'))
        finally:
            db_pool.putconn(conn)
        return render_template('registro_pesagem.html', pesagens=pesagens,
                               sort=sort, order=order, new_order=new_order,
                               page=page, has_next=has_next)
    else:
        flash('Você precisa estar logado para acessar esta página.')
        return redirect(url_for('login'))

@app.route('/alterar_senha', methods=['GET', 'POST'])
def alterar_senha():
    if 'user_id' in session:
        if request.method == 'POST':
            senha_atual = request.form['senha_atual']
            nova_senha = request.form['nova_senha']
            confirmar_senha = request.form['confirmar_senha']
            user_id = session['user_id']
            conn = db_pool.getconn()
            try:
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
            except Exception as e:
                app.logger.error(f"Erro ao alterar senha: {e}")
                flash('Erro interno do servidor.')
            finally:
                db_pool.putconn(conn)
        return render_template('alterar_senha.html')
    else:
        return redirect(url_for('login'))

@app.route('/excluir_usuario/<usuario_id>', methods=['POST'])
def excluir_usuario(usuario_id):
    if 'user_id' in session:
        conn = db_pool.getconn()
        try:
            c = conn.cursor()
            c.execute('DELETE FROM usuario WHERE cpf = %s', (usuario_id,))
            conn.commit()
            flash('Usuário excluído com sucesso.')
        except Exception as e:
            app.logger.error(f"Erro ao excluir usuário: {e}")
            flash('Erro interno do servidor.')
        finally:
            db_pool.putconn(conn)
    return redirect(url_for('cadastro'))

@app.route('/vinculo_cartoes', methods=['GET', 'POST'])
def vinculo_cartoes():
    conn = db_pool.getconn()
    try:
        c = conn.cursor()
        c.execute("SELECT cpf, nome FROM usuario")
        todos_usuarios = c.fetchall()
        sort = request.args.get('sort', 'cpf')
        order = request.args.get('order', 'asc')
        new_order = 'asc' if order == 'desc' else 'desc'
        page = request.args.get('page', 1, type=int)
        limit = 25
        offset = (page - 1) * limit
        query = """
            SELECT u.cpf, u.nome, ARRAY_AGG(c.id_cartao) AS cartoes_vinculados 
            FROM usuario u 
            LEFT JOIN usuario_cartao c ON u.cpf = c.cpf 
            GROUP BY u.cpf, u.nome
            ORDER BY {col} {ord}
            LIMIT %s OFFSET %s
        """.format(col=sort, ord=order)
        c.execute(query, (limit+1, offset))
        usuarios_com_vinculo = c.fetchall()
        has_next = len(usuarios_com_vinculo) > limit
        usuarios_com_vinculo = usuarios_com_vinculo[:limit]
        if request.method == 'POST':
            cpf = request.form.get('cpf_usuario')
            novo_id = request.form.get('novo_id')
            if cpf and novo_id:
                c.execute("SELECT * FROM usuario_cartao WHERE cpf = %s AND id_cartao = %s", (cpf, novo_id))
                cartao_existente = c.fetchone()
                if cartao_existente:
                    flash('Este cartão já está vinculado a este usuário.')
                else:
                    c.execute("INSERT INTO usuario_cartao (cpf, id_cartao) VALUES (%s, %s)", (cpf, novo_id))
                    conn.commit()
                    flash('Cartão associado com sucesso!')
            else:
                flash('Dados insuficientes para associação.')
            return redirect(url_for('vinculo_cartoes'))
    except Exception as e:
        app.logger.error(f"Erro ao vincular cartões: {e}")
        flash('Erro interno do servidor.')
    finally:
        db_pool.putconn(conn)
    return render_template('vinculo_cartoes.html', usuarios_sem_vinculo=todos_usuarios,
                           usuarios_com_vinculo=usuarios_com_vinculo, sort=sort, order=order,
                           new_order=new_order, page=page, has_next=has_next)

@app.route('/remover_vinculo/<cpf>/<id_cartao>', methods=['POST'])
def remover_vinculo(cpf, id_cartao):
    if request.method == 'POST':
        conn = db_pool.getconn()
        try:
            c = conn.cursor()
            c.execute('DELETE FROM usuario_cartao WHERE cpf = %s AND id_cartao = %s', (cpf, id_cartao))
            conn.commit()
            flash('Vínculo removido com sucesso!')
        except Exception as e:
            app.logger.error(f"Erro ao remover vínculo: {e}")
            flash('Erro interno do servidor.')
        finally:
            db_pool.putconn(conn)
        return redirect(url_for('vinculo_cartoes'))
    else:
        flash('Método inválido para remoção de vínculo.')
        return redirect(url_for('vinculo_cartoes'))

def obter_cpf_por_cartao(id_cartao):
    conn = db_pool.getconn()
    try:
        c = conn.cursor()
        c.execute('SELECT cpf FROM usuario_cartao WHERE id_cartao = %s', (id_cartao,))
        cpf = c.fetchone()
        if cpf:
            return cpf[0]
        else:
            raise ValueError(f"Cartão {id_cartao} não encontrado.")
    finally:
        db_pool.putconn(conn)

@app.route('/adicionar_pesagem_remota', methods=['POST'])
@limiter.limit("100 per minute")
def adicionar_pesagem_remota():
    try:
        data = request.get_json()
        app.logger.info(f"Recebida pesagem remota: {data}")
        id_cartao = data.get('id_cartao')
        peso = data.get('peso')
        data_pesagem = data.get('data')  # Formato "dd/mm/aaaa"
        horario = data.get('horario')    # Formato "HH:MM:SS"
        if not all([id_cartao, peso, data_pesagem, horario]):
            app.logger.warning("Dados incompletos recebidos na pesagem remota.")
            return jsonify({"message": "Dados incompletos."}), 400
        try:
            data_pesagem = datetime.strptime(data_pesagem, "%d/%m/%Y").date()
        except ValueError:
            app.logger.warning("Formato de data inválido recebido.")
            return jsonify({"message": "Formato de data inválido. Use dd/mm/aaaa."}), 400
        try:
            horario = datetime.strptime(horario, "%H:%M:%S").time()
        except ValueError:
            app.logger.warning("Formato de horário inválido recebido.")
            return jsonify({"message": "Formato de horário inválido. Use HH:MM:SS."}), 400
        try:
            cpf_usuario = obter_cpf_por_cartao(id_cartao)
        except ValueError as ve:
            app.logger.warning(f"{ve}")
            return jsonify({"message": str(ve)}), 400
        conn = db_pool.getconn()
        try:
            c = conn.cursor()
            c.execute(''' 
                INSERT INTO pesagem (cpf, id_cartao, peso, data, horario)
                VALUES (%s, %s, %s, %s, %s)
            ''', (cpf_usuario, id_cartao, peso, data_pesagem, horario))
            conn.commit()
            app.logger.info(f"Pesagem remota registrada para cartão {id_cartao}.")
        except Exception as e:
            app.logger.error(f"Erro ao inserir pesagem remota: {e}")
            return jsonify({"message": "Erro interno do servidor."}), 500
        finally:
            db_pool.putconn(conn)
        return jsonify({"message": "Pesagem registrada com sucesso!"}), 200
    except Exception as e:
        app.logger.error(f"Erro inesperado no endpoint /adicionar_pesagem_remota: {e}")
        return jsonify({"message": "Erro interno do servidor."}), 500

# Inicia o NGROK em uma thread separada e, em seguida, inicia o Flask
if __name__ == "__main__":
    init_db()
    ngrok_thread = threading.Thread(target=start_ngrok, daemon=True)
    ngrok_thread.start()
    # Aguarda um instante para que o ngrok inicie
    time.sleep(2)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
