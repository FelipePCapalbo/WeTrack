from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


limiter = Limiter(key_func=get_remote_address)


def init_extensions(app):
    # Limiter centralizado
    default_limits = getattr(app.config, "RATE_LIMITS", None) or app.config.get("RATE_LIMITS")
    limiter.default_limits = default_limits
    limiter.init_app(app)


