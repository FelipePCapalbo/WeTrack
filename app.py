import os
from app_factory import create_app
from ngrok_utils import start_ngrok_threaded


# DSN local padrão do servidor legado (pode ser sobrescrito por DATABASE_URL)
os.environ.setdefault("DATABASE_URL", "postgresql://db_CDPRO:admin@db:5432/db_CDPRO")

app = create_app()


if __name__ == "__main__":
    start_ngrok_threaded()
    port = app.config["PORT"]
    app.run(host='0.0.0.0', port=port, debug=app.config['DEBUG'])


