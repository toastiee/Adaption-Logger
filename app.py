import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g

app = Flask(__name__)
DATABASE = "coding_log.db"


# ---------- database helpers ----------
def get_db():
    """One connection per request, stored on Flask's 'g' object."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row   # lets you use row["car"] instead of row[1]
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the table if it doesn't exist yet. Safe to run every startup."""
    db = sqlite3.connect(DATABASE)
    db.execute("""
        CREATE TABLE IF NOT EXISTS changes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            car          TEXT NOT NULL,
            control_unit TEXT NOT NULL,
            channel      TEXT NOT NULL,
            old_value    TEXT,
            new_value    TEXT,
            method       TEXT,
            date         TEXT,
            notes        TEXT,
            reverted     INTEGER DEFAULT 0
        )
    """)
    db.commit()
    db.close()


init_db()   # runs on import, so it also works on PythonAnywhere later


# ---------- routes ----------
@app.route("/")
def index():
    changes = get_db().execute(
        "SELECT * FROM changes ORDER BY date DESC, id DESC"
    ).fetchall()
    return render_template("index.html", changes=changes)


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        f = request.form
        db = get_db()
        db.execute(
            """INSERT INTO changes
               (car, control_unit, channel, old_value, new_value, method, date, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (f["car"], f["control_unit"], f["channel"], f["old_value"],
             f["new_value"], f["method"], f["date"], f["notes"]),
        )
        db.commit()
        return redirect(url_for("index"))
    return render_template("add.html")


if __name__ == "__main__":
    app.run(debug=True, port=5001)