"""Build the self-hosted Flask app."""

import os

from flask import Flask

from dinkydash.config import ConfigError
from dinkydash.mode import validate

SINGLE = "single"
SELF_HOSTED_KEY = "dinkydash-self-hosted"


def mode():
    return validate(os.environ.get("DINKYDASH_MODE"))


def create_app(store=None):
    """Build an app using the provided file store, or the default one."""
    mode()

    if store is None:
        from dinkydash.store import FileStore
        store = FileStore()

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(MODE=SINGLE, STORE=store,
                      APP_HOST=os.environ.get("DINKYDASH_APP_HOST", "").strip())
    app.secret_key = os.environ.get("DINKYDASH_SECRET_KEY") or SELF_HOSTED_KEY

    from . import feedback, parent
    from .request_log import quieten_the_request_log
    quieten_the_request_log()
    parent.check_configuration(app)
    app.jinja_env.globals["feedback_enabled"] = feedback.enabled
    app.jinja_env.globals["parent_sign_in_on"] = parent.enabled

    from .session import configure as configure_session
    configure_session(app)
    from .assets import configure as configure_assets
    configure_assets(app)

    from .routes.board import bp as board_bp
    from .routes.settings import bp as settings_bp
    from .routes.parent import bp as parent_bp
    from .routes.phone import bp as phone_bp, pins_bp
    from .routes.activity import bp as activity_bp

    app.register_blueprint(board_bp)
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(parent_bp)
    app.register_blueprint(phone_bp)
    app.register_blueprint(pins_bp, url_prefix="/settings/pins")
    app.register_blueprint(activity_bp, url_prefix="/settings/activity")

    if parent.password():
        from .routes.wall import admin_bp as wall_admin_bp, bp as wall_bp
        app.register_blueprint(wall_bp)
        app.register_blueprint(wall_admin_bp, url_prefix="/settings/wall")

    @app.errorhandler(ConfigError)
    def unreadable_config(error):
        """Say what to fix: an unreadable config is the owner's to repair, not a server fault."""
        return str(error), 500, {"Content-Type": "text/plain; charset=utf-8"}

    @app.after_request
    def no_referrer(response):
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    return app
