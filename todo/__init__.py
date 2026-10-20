"""Later Gator, a to-do list app.

Flask builds the app inside create_app() (the "app factory" pattern).
Tests call it with their own settings, so each test gets a fresh database.
"""
import os
from datetime import date

from flask import Flask


def create_app(test_config=None):
    # instance_relative_config puts the database in the instance/ folder,
    # which is kept out of git.
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        # SECRET_KEY signs the session cookie, which holds flash messages and
        # the CSRF token. Set a long random value in the environment before
        # putting the app online.
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        DATABASE=os.path.join(app.instance_path, "todo.sqlite"),
        # A function that returns today's date. Tests swap in a fixed day.
        TODAY=date.today,
    )
    if test_config:
        app.config.update(test_config)

    @app.url_defaults
    def add_static_version(endpoint, values):
        """Add ?v=<when the file last changed> to links to static files.

        Browsers keep a copy of style.css and the scripts, and may go on
        using an old one after a deploy. A new number after each change
        makes the link new, so the browser downloads the new file.
        """
        if endpoint == "static" and "filename" in values:
            path = os.path.join(app.static_folder, values["filename"])
            if os.path.isfile(path):
                values["v"] = int(os.path.getmtime(path))

    os.makedirs(app.instance_path, exist_ok=True)

    from . import auth, csrf, db, demo, lists, pages, profile, tasks

    db.init_app(app)
    # auth goes before csrf, so g.user is already known if the CSRF check
    # refuses a request and the error page shows the header.
    app.register_blueprint(auth.bp)
    csrf.init_app(app)
    app.register_blueprint(tasks.bp)
    app.register_blueprint(lists.bp)
    app.register_blueprint(pages.bp)
    app.register_blueprint(profile.bp)
    demo.init_app(app)  # the create-demo command
    return app
