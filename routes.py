import datetime
import csv
import io
from datetime import datetime as dt
from flask import jsonify
from db import db

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    Response,
)
from werkzeug.security import generate_password_hash, check_password_hash

from db import db
from extensions import limiter


def _normalize_order(order_param: str) -> str:
    value = (order_param or "asc").lower()
    return "desc" if value == "desc" else "asc"


def _map_sort(allowed: dict, requested: str, default_key: str) -> str:
    return allowed.get(requested, allowed.get(default_key, default_key))


def register_routes(app):
    @app.route('/')
    def login():
        return render_template('login.html')

    @app.route('/check_cpf', methods=['POST'])
    def check_cpf():
        cpf = request.form['cpf']
        conn = db.getconn()
        try:
            c = conn.cursor()
            c.execute('SELECT * FROM usuarios WHERE cpf = %s', (cpf,))
            user = c.fetchone()
        except Exception as e:
            app.logger.error(f"Erro ao verificar CPF: {e}")
            flash('Erro interno do servidor.')
            return redirect(url_for('login'))
        finally:
            db.putconn(conn)
        if user:
            tipo_usuario = user[4]
            if tipo_usuario == 'colhedor':
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
        conn = db.getconn()
        try:
            c = conn.cursor()
            c.execute('SELECT * FROM usuarios WHERE cpf = %s', (cpf,))
            user = c.fetchone()
        except Exception as e:
            app.logger.error(f"Erro ao realizar login: {e}")
            flash('Erro interno do servidor.')
            return redirect(url_for('login'))
        finally:
            db.putconn(conn)
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
        if 'user_id' not in session:
            flash('Acesso negado.')
            return redirect(url_for('login'))

        conn = db.getconn()
        try:
            c = conn.cursor()
            sort = request.args.get('sort', 'cpf')
            order = _normalize_order(request.args.get('order', 'asc'))
            new_order = 'asc' if order == 'desc' else 'desc'
            page = request.args.get('page', 1, type=int)
            limit = 25
            offset = (page - 1) * limit
            column_map = {
                'nome': 'nome',
                'cpf': 'cpf',
                'tipo_usuario': 'tipo_usuario',
                'data_inclusao': 'data_inclusao',
            }
            sort_column = _map_sort(column_map, sort, 'cpf')
            query = f'''
                SELECT nome, cpf, tipo_usuario, data_inclusao
                FROM usuarios
                ORDER BY {sort_column} {order}
                LIMIT %s OFFSET %s
            '''
            c.execute(query, (limit + 1, offset))
            usuarios = c.fetchall()
            has_next = len(usuarios) > limit
            usuarios = usuarios[:limit]
        except Exception as e:
            app.logger.error(f"Erro ao buscar usuários: {e}")
            flash('Erro interno do servidor.')
            return redirect(url_for('pagina_principal'))
        finally:
            db.putconn(conn)

        usuarios_formatados = [
            {
                'nome': usuario[0],
                'cpf': usuario[1],
                'tipo_usuario': usuario[2],
                'data_inclusao': usuario[3].strftime('%d/%m/%Y %H:%M:%S'),
            }
            for usuario in usuarios
        ]
        return render_template(
            'cadastro.html',
            usuarios=usuarios_formatados,
            sort=sort,
            order=order,
            new_order=new_order,
            page=page,
            has_next=has_next,
        )

    @app.route('/cadastro', methods=['POST'])
    def cadastro_post():
        nome = request.form['nome']
        cpf = request.form['cpf']
        senha = request.form['senha']
        tipo_usuario = request.form.get('tipo_usuario', 'colhedor')
        conn = db.getconn()
        try:
            c = conn.cursor()
            c.execute('SELECT 1 FROM usuarios WHERE cpf = %s', (cpf,))
            usuario_existente = c.fetchone()
            if usuario_existente:
                flash('CPF já cadastrado. Por favor, use outro CPF.')
                return redirect(url_for('cadastro'))
            c.execute(
                '''INSERT INTO usuarios (cpf, nome, senha, tipo_usuario) VALUES (%s, %s, %s, %s)''',
                (cpf, nome, generate_password_hash(senha), tipo_usuario),
            )
            conn.commit()
            flash('Usuário cadastrado com sucesso.')
            return redirect(url_for('cadastro'))
        except Exception as e:
            app.logger.error(f"Erro ao cadastrar usuário: {e}")
            flash('Erro interno do servidor.')
            return redirect(url_for('cadastro'))
        finally:
            db.putconn(conn)

    @app.route('/pesagens', methods=['GET'])
    def pesagens():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        cpf = session['user_id']
        return redirect(url_for('pagina_principal', cpf=cpf))

    @app.route('/adicionar_pesagem', methods=['POST'])
    def adicionar_pesagem():
        id_cartao = request.form['id_cartao']
        peso = request.form['peso']
        conn = db.getconn()
        try:
            c = conn.cursor()
            c.execute('SELECT cpf FROM usuarios WHERE id_cartao = %s', (id_cartao,))
            usuario_existente = c.fetchone()
            if usuario_existente:
                cpf = usuario_existente[0]
                c.execute(
                    '''INSERT INTO pesagens (cpf, id_cartao, peso, data, horario)
                       VALUES (%s, %s, %s, CURRENT_DATE, CURRENT_TIME)''',
                    (cpf, id_cartao, peso),
                )
                conn.commit()
                flash('Pesagem adicionada com sucesso.')
            else:
                flash('Cartão não encontrado. Verifique o ID do Cartão.')
        except Exception as e:
            app.logger.error(f"Erro ao adicionar pesagem: {e}")
            flash('Erro interno do servidor.')
        finally:
            db.putconn(conn)
        return redirect(url_for('registro_pesagem'))

    @app.route('/pagina_principal', methods=['GET'])
    def pagina_principal():
        if 'user_id' not in session:
            return redirect(url_for('login'))

        cpf_filter = request.args.get('cpf')
        id_cartao_filter = request.args.get('id_cartao')
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')
        sort = request.args.get('sort', 'id_pesagem')
        order = _normalize_order(request.args.get('order', 'desc'))
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
            'horario': 'horario',
        }
        sort_column = _map_sort(column_map, sort, 'id_pesagem')
        query = 'SELECT id_pesagem, id_cartao, cpf, peso, data, horario FROM pesagens'
        params = []
        conditions = []
        if id_cartao_filter:
            conditions.append(' id_cartao = %s')
            params.append(id_cartao_filter)
        if cpf_filter:
            conditions.append(' cpf = %s')
            params.append(cpf_filter)
        if data_inicio:
            conditions.append(' data >= %s')
            params.append(data_inicio)
        if data_fim:
            conditions.append(' data <= %s')
            params.append(data_fim)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += f' ORDER BY {sort_column} {order} LIMIT %s OFFSET %s'
        params.extend([limit + 1, offset])
        conn = db.getconn()
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
            db.putconn(conn)
        return render_template(
            'pagina_principal.html',
            pesagens=pesagens,
            sort=sort,
            order=order,
            new_order=new_order,
            page=page,
            has_next=has_next,
        )

    @app.route('/registro_pesagem', methods=['GET', 'POST'])
    def registro_pesagem():
        if 'user_id' not in session:
            flash('Você precisa estar logado para acessar esta página.')
            return redirect(url_for('login'))

        sort = request.args.get('sort', 'id_pesagem')
        order = _normalize_order(request.args.get('order', 'asc'))
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
            'horario': 'horario',
        }
        sort_column = _map_sort(column_map, sort, 'id_pesagem')
        query = f'''
            SELECT id_pesagem, cpf, id_cartao, peso, data, horario
            FROM pesagens
            ORDER BY {sort_column} {order}
            LIMIT %s OFFSET %s
        '''
        conn = db.getconn()
        try:
            c = conn.cursor()
            c.execute(query, (limit + 1, offset))
            pesagens = c.fetchall()
            has_next = len(pesagens) > limit
            pesagens = pesagens[:limit]
        except Exception as e:
            app.logger.error(f"Erro ao registrar pesagem: {e}")
            flash('Erro interno do servidor.')
            return redirect(url_for('pagina_principal'))
        finally:
            db.putconn(conn)
        return render_template(
            'registro_pesagem.html',
            pesagens=pesagens,
            sort=sort,
            order=order,
            new_order=new_order,
            page=page,
            has_next=has_next,
        )

    @app.route('/alterar_senha', methods=['GET', 'POST'])
    def alterar_senha():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if request.method == 'POST':
            senha_atual = request.form['senha_atual']
            nova_senha = request.form['nova_senha']
            confirmar_senha = request.form['confirmar_senha']
            user_id = session['user_id']
            conn = db.getconn()
            try:
                c = conn.cursor()
                c.execute('SELECT senha FROM usuarios WHERE cpf = %s', (user_id,))
                row = c.fetchone()
                if not row:
                    flash('Usuário não encontrado.')
                    return render_template('alterar_senha.html')
                senha_armazenada = row[0]
                if not check_password_hash(senha_armazenada, senha_atual):
                    flash('A senha atual está incorreta.')
                elif nova_senha != confirmar_senha:
                    flash('As novas senhas não coincidem.')
                else:
                    c.execute(
                        'UPDATE usuarios SET senha = %s WHERE cpf = %s',
                        (generate_password_hash(nova_senha), user_id),
                    )
                    conn.commit()
                    flash('Senha alterada com sucesso.')
            except Exception as e:
                app.logger.error(f"Erro ao alterar senha: {e}")
                flash('Erro interno do servidor.')
            finally:
                db.putconn(conn)
        return render_template('alterar_senha.html')

    @app.route('/excluir_usuario/<usuario_id>', methods=['POST'])
    def excluir_usuario(usuario_id):
        if 'user_id' in session:
            conn = db.getconn()
            try:
                c = conn.cursor()
                # Remover dependências antes do usuário
                c.execute('DELETE FROM pesagens WHERE cpf = %s', (usuario_id,))
                c.execute('DELETE FROM usuarios WHERE cpf = %s', (usuario_id,))
                conn.commit()
                flash('Usuário excluído com sucesso.')
            except Exception as e:
                app.logger.error(f"Erro ao excluir usuário: {e}")
                flash('Erro interno do servidor.')
            finally:
                db.putconn(conn)
        return redirect(url_for('cadastro'))

  @app.route('/vinculo_cartoes', methods=['GET', 'POST'])
    def vinculo_cartoes():
        conn = db.getconn()
        try:
            c = conn.cursor()
            c.execute('SELECT cpf, nome FROM usuarios')
            todos_usuarios = c.fetchall()
            sort = request.args.get('sort', 'cpf')
            order = _normalize_order(request.args.get('order', 'asc'))
            new_order = 'asc' if order == 'desc' else 'desc'
            page = request.args.get('page', 1, type=int)
            limit = 25
            offset = (page - 1) * limit
            column_map = {'cpf': 'cpf', 'nome': 'nome'}
            sort_column = _map_sort(column_map, sort, 'cpf')
            # Com estrutura nova, o cartão vem de usuarios.id_cartao
            query = f'''
                SELECT cpf, nome, ARRAY_REMOVE(ARRAY[id_cartao], NULL) AS cartoes_vinculados
                FROM usuarios
                ORDER BY {sort_column} {order}
                LIMIT %s OFFSET %s
            '''
            c.execute(query, (limit + 1, offset))
            usuarios_com_vinculo = c.fetchall()
            has_next = len(usuarios_com_vinculo) > limit
            usuarios_com_vinculo = usuarios_com_vinculo[:limit]
            
            if request.method == 'POST':
                cpf = request.form.get('cpf_usuario')
                novo_id = request.form.get('novo_id')
                if cpf and novo_id:
                    c.execute('UPDATE usuarios SET id_cartao = %s WHERE cpf = %s', (novo_id, cpf))
                    conn.commit()
                    
                    # --- INÍCIO DA MODIFICAÇÃO ---
                    # Atualiza o timestamp de 'usuarios' pois um cartão foi vinculado.
                    # A rota /api/status lerá esta mudança.
                    db.atualizar_sincronizacao("usuarios")
                    # --- FIM DA MODIFICAÇÃO ---
                    
                    flash('Cartão associado com sucesso!')
                else:
                    flash('Dados insuficientes para associação.')
                return redirect(url_for('vinculo_cartoes'))
        
        except Exception as e:
            app.logger.error(f"Erro ao vincular cartões: {e}")
            flash('Erro interno do servidor.')
        finally:
            db.putconn(conn)
        
        return render_template(
            'vinculo_cartoes.html',
            usuarios_sem_vinculo=todos_usuarios,
            usuarios_com_vinculo=usuarios_com_vinculo,
            sort=sort,
            order=order,
            new_order=new_order,
            page=page,
            has_next=has_next,
        )

@app.route('/remover_vinculo/<cpf>/<id_cartao>', methods=['POST'])
    def remover_vinculo(cpf, id_cartao):
        conn = db.getconn()
        try:
            c = conn.cursor()
            c.execute('UPDATE usuarios SET id_cartao = NULL WHERE cpf = %s AND id_cartao = %s', (cpf, id_cartao))
            c.execute(
                'UPDATE sincronizacao SET ultima_atualizacao = CURRENT_TIMESTAMP WHERE tabela = %s', 
                ('usuarios',)
            )
            conn.commit()
            flash('Vínculo removido com sucesso!')
        except Exception as e:
            app.logger.error(f"Erro ao remover vínculo: {e}")
            flash('Erro interno do servidor.')
        finally:
            db.putconn(conn)
        return redirect(url_for('vinculo_cartoes'))    @app.route('/api/status')
        
    def api_status():
        """
        Endpoint para sistemas embarcados verificarem a versão dos dados.
        """
        conn = None
        try:
            conn = db.getconn()
            cursor = conn.cursor()

            cursor.execute("SELECT ultima_atualizacao FROM sincronizacao WHERE tabela = 'usuarios';")
            result = cursor.fetchone()
            
            cursor.close()

            if result:
                # Formata o timestamp para o padrão ISO 8601, que é fácil de processar
                timestamp = result[0].isoformat()
                return jsonify({"usuarios_ultima_atualizacao": timestamp})
            else:
                return jsonify({"erro": "Informação de sincronização não encontrada"}), 404

        except Exception as e:
            app.logger.error(f"Erro no endpoint de status: {e}")
            return jsonify({"erro": "Erro interno do servidor"}), 500
        
        finally:
            if conn:
                db.putconn(conn)

    @app.route('/exportar_usuarios')
    def exportar_usuarios():
        """
        Exporta os usuários (id_cartao, nome) para um arquivo CSV.
        - Delimitador: Vírgula (,).
        - Formato: ID_cartao,Nome
        """
        conn = None
        try:
            conn = db.getconn()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id_cartao, nome 
                FROM usuarios 
                WHERE id_cartao IS NOT NULL 
                ORDER BY nome ASC;
            """)
            usuarios_com_cartao = cursor.fetchall()
            
            cursor.close()

            # Cria o CSV em memória
            output = io.StringIO()
            # Altera o delimitador para vírgula (,)
            writer = csv.writer(output, delimiter=',')
            writer.writerows(usuarios_com_cartao)
            
            # Prepara a resposta HTTP
            response = Response(output.getvalue(), mimetype='text/csv')
            response.headers.set("Content-Disposition", "attachment", filename="export_usuarios.csv")
            return response

        except Exception as e:
            app.logger.error(f"Erro ao exportar dados de usuários para CSV: {e}")
            return jsonify({"erro": "Erro interno do servidor"}), 500
        
        finally:
            if conn:
                db.putconn(conn)

    @app.route('/adicionar_pesagem_remota', methods=['POST'])
    @limiter.limit('30 per minute') 
    def adicionar_pesagem_remota():
        try:
            payload_string = request.data.decode('utf-8')
            
            linhas = payload_string.strip().split('\n')
            
            if not linhas:
                return jsonify({'message': 'Requisição vazia.'}), 400

            conn = db.getconn()
            try:
                c = conn.cursor()
                registros_inseridos = 0
                registros_falhados = 0

                for linha in linhas:
                    if not linha or "id_cartao" in linha:
                        continue
                    
                    partes = linha.split(',')
                    
                    if len(partes) != 5:
                        app.logger.warning(f"Linha CSV mal formatada recebida: {linha}")
                        registros_falhados += 1
                        continue 

                    id_cartao = partes[0]
                    peso = partes[1]
                    data_str = partes[2]
                    horario_str = partes[3]
                    id_pesagem = partes[4] 

                    try:
                        data_pesagem = dt.strptime(data_str, '%d/%m/%Y').date()
                        horario_pesagem = dt.strptime(horario_str, '%H:%M:%S').time()
                        cpf_usuario = obter_cpf_por_cartao(id_cartao)

                        c.execute(
                            '''INSERT INTO pesagens (id_pesagem, cpf, id_cartao, peso, data, horario)
                            VALUES (%s, %s, %s, %s, %s, %s)''',
                            (id_pesagem, cpf_usuario, id_cartao, peso, data_pesagem, horario_pesagem)
                        )
                        registros_inseridos += 1
                    except ValueError as ve:
                        # Captura erros de cartão não encontrado ou formatos inválidos
                        app.logger.warning(f"Erro ao processar registro CSV {linha}: {ve}")
                        registros_falhados += 1
                        continue
                
                conn.commit()
                msg = f'{registros_inseridos} pesagens registradas. {registros_falhados} falharam.'
                app.logger.info(msg)
                return jsonify({'message': msg}), 200

            except Exception as e:
                conn.rollback()
                app.logger.error(f'Erro ao inserir pesagens CSV: {e}')
                return jsonify({'message': 'Erro interno do servidor ao processar o CSV.'}), 500
            finally:
                db.putconn(conn)

        except Exception as e:
            app.logger.error(f'Erro inesperado no endpoint /adicionar_pesagem_remota: {e}')
            return jsonify({'message': 'Erro interno do servidor.'}), 500
