import os
from app_factory import create_app


# Fallback local automático para desenvolvimento no macOS
os.environ.setdefault("DATABASE_URL", "postgresql://db_cdpro:admin@localhost:5432/db_cdpro")

app = create_app()


if __name__ == "__main__":
    port = app.config["PORT"]
    app.run(host='0.0.0.0', port=port, debug=app.config['DEBUG'])


