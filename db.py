import logging
import os
from typing import Optional
from urllib.parse import urlparse, unquote

import psycopg2
from psycopg2 import pool, sql
from werkzeug.security import generate_password_hash


class Database:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: Optional[pool.SimpleConnectionPool] = None

    def init_app(self, app):
        try:
            self._pool = psycopg2.pool.SimpleConnectionPool(1, 20, self._dsn)
            app.logger.info("Pool de conexões criado com sucesso")
        except (Exception, psycopg2.DatabaseError) as error:
            app.logger.error(f"Erro ao criar pool de conexões: {error}")
            error_str = str(error).lower()
            if "does not exist" in error_str or "não existe" in error_str:
                # Banco de dados não existe: tenta criar e reabrir pool
                try:
                    self._bootstrap_database(app.logger)
                    self._pool = psycopg2.pool.SimpleConnectionPool(1, 20, self._dsn)
                    app.logger.info("Banco criado e pool reestabelecido com sucesso")
                except Exception as e:
                    app.logger.error(f"Falha no bootstrap do banco: {e}")
                    raise
            else:
                raise

    def _parse_dsn(self):
        parsed = urlparse(self._dsn)
        user = unquote(parsed.username) if parsed.username else None
        password = unquote(parsed.password) if parsed.password else None
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        dbname = parsed.path.lstrip("/") if parsed.path else None
        return {"user": user, "password": password, "host": host, "port": port, "dbname": dbname}

    def _bootstrap_database(self, logger: logging.Logger):
        info = self._parse_dsn()
        user = info["user"]
        password = info["password"] or ""
        host = info["host"]
        port = info["port"]
        dbname = info["dbname"]

        admin_url = os.environ.get("DB_ADMIN_URL", f"postgresql://{user}:{password}@{host}:{port}/postgres")
        logger.info("Inicializando banco ausente usando conexão administrativa")
        admin_conn = psycopg2.connect(admin_url)
        try:
            admin_conn.autocommit = True
            cur = admin_conn.cursor()
            # Garante role
            if user:
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
                if cur.fetchone() is None:
                    cur.execute(sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(sql.Identifier(user)), (password,))
                    logger.info(f"Role {user} criada")
            # Cria DB se necessário
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone() is None:
                if user:
                    cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(dbname), sql.Identifier(user)))
                else:
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
                logger.info(f"Banco {dbname} criado")
        finally:
            admin_conn.close()

    def getconn(self):
        if not self._pool:
            raise RuntimeError("Pool de conexões não inicializado")
        return self._pool.getconn()

    def putconn(self, conn):
        if self._pool:
            self._pool.putconn(conn)

    def init_schema(self, app_logger: logging.Logger):
        conn = self.getconn()
        try:
            c = conn.cursor()
            # Reset opcional (ambiente local): derruba tabelas para recriar do zero
            reset_db = True if (os.environ.get('DB_RESET') == '1') else False
            if reset_db:
                c.execute('DROP TABLE IF EXISTS pesagens')
                c.execute('DROP TABLE IF EXISTS usuario_cartao')
                c.execute('DROP TABLE IF EXISTS usuarios')
                c.execute('DROP TABLE IF EXISTS usuario')
                c.execute('DROP TABLE IF EXISTS pesagem')
                c.execute('DROP TABLE IF EXISTS sincronizacao')

            # Tabela unificada de usuários (com id_cartao opcional)
            c.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    cpf TEXT PRIMARY KEY,
                    nome TEXT NOT NULL,
                    senha TEXT NOT NULL,
                    data_inclusao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    tipo_usuario TEXT NOT NULL DEFAULT 'colhedor',
                    id_cartao TEXT UNIQUE
                )
            ''')

            # Tabela de sincronização
            c.execute('''
                CREATE TABLE IF NOT EXISTS sincronizacao (
                    tabela TEXT PRIMARY KEY,
                    ultima_atualizacao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Garante registro inicial da tabela usuarios
            c.execute('''
                INSERT INTO sincronizacao (tabela, ultima_atualizacao)
                VALUES ('usuarios', CURRENT_TIMESTAMP)
                ON CONFLICT (tabela) DO NOTHING
            ''')

            # Migra dados antigos caso tabela 'usuario' exista
            c.execute("SELECT to_regclass('public.usuario')")
            if c.fetchone()[0]:
                c.execute('''
                    INSERT INTO usuarios (cpf, nome, senha, data_inclusao, tipo_usuario)
                    SELECT cpf, nome, senha, data_inclusao, tipo_usuario FROM usuario
                    ON CONFLICT (cpf) DO NOTHING
                ''')

            # Migra vínculos de cartões (pegando o primeiro por CPF)
            c.execute("SELECT to_regclass('public.usuario_cartao')")
            if c.fetchone()[0]:
                c.execute('''
                    UPDATE usuarios u SET id_cartao = v.id_cartao
                    FROM (
                        SELECT cpf, MIN(id_cartao) AS id_cartao FROM usuario_cartao GROUP BY cpf
                    ) v
                    WHERE u.cpf = v.cpf AND u.id_cartao IS NULL
                ''')

            # Tabela de pesagens
            c.execute('''
                CREATE TABLE IF NOT EXISTS pesagens (
                    id_pesagem SERIAL PRIMARY KEY,
                    cpf TEXT NOT NULL,
                    id_cartao TEXT,
                    peso REAL NOT NULL,
                    data DATE NOT NULL,
                    horario TIME NOT NULL,
                    FOREIGN KEY (cpf) REFERENCES usuarios(cpf)
                )
            ''')

            # Migra pesagens antigas
            c.execute("SELECT to_regclass('public.pesagem')")
            if c.fetchone()[0]:
                c.execute('''
                    INSERT INTO pesagens (cpf, id_cartao, peso, data, horario)
                    SELECT cpf, id_cartao, peso, data, horario FROM pesagem
                ''')

            # Usuário semente (admin)
            c.execute('''
                INSERT INTO usuarios (cpf, nome, senha, tipo_usuario, id_cartao)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (cpf) DO NOTHING
            ''', ('00000000000', 'Felipe Capalbo', generate_password_hash('12345'), 'administrador', 'BFBA5A'))

            conn.commit()
            app_logger.info("Banco de dados inicializado com sucesso")
        except Exception as e:
            app_logger.error(f"Erro durante a inicialização do banco de dados: {e}")
        finally:
            self.putconn(conn)

    def atualizar_sincronizacao(self, tabela: str = "usuarios"):
        """Atualiza o timestamp da tabela de sincronização"""
        conn = self.getconn()
        try:
            c = conn.cursor()
            c.execute('''
                UPDATE sincronizacao
                SET ultima_atualizacao = CURRENT_TIMESTAMP
                WHERE tabela = %s
            ''', (tabela,))
            conn.commit()
        finally:
            self.putconn(conn)


db = Database(dsn="")
