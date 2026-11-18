import os
import sqlite3
from collections import Counter
from flask import Flask, render_template, request, redirect, url_for, g, jsonify

app = Flask(__name__)
DATABASE = "coding_log.db"

# Read-only reference data built from dv52's Mk7 BCM comparison PDF
# (see bcm_coding/extract_bcm.py). The app still works if this file is missing.
REFERENCE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "bcm_coding", "bcm_reference.db")

# Suggestions for the "Control unit" box on the add form
CONTROL_UNITS = [
    "01 Engine Electronics",
    "03 Brake Electronics",
    "08 Air Conditioning",
    "09 Central Electrics",
    "13 Distance Regulation (ACC)",
    "15 Airbag",
    "16 Steering Column Electronics",
    "17 Dash Board",
    "19 Gateway",
    "42 Driver Door Electronics",
    "44 Steering Assist",
    "52 Passenger Door Electronics",
    "5F Information Electronics",
    "A5 Front Sensors Driver Assistance",
]


# ---------- database helpers ----------
def get_db():
    """One connection per request, stored on Flask's 'g' object."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row   # lets you use row["car"] instead of row[1]
    return g.db


@app.teardown_appcontext
def close_db(exception):
    for name in ("db", "ref_db"):
        db = g.pop(name, None)
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


def get_ref_db():
    """Connection to the BCM reference database, or None if it isn't there."""
    if "ref_db" not in g:
        if not os.path.exists(REFERENCE_DB):
            return None
        g.ref_db = sqlite3.connect(f"file:{REFERENCE_DB}?mode=ro", uri=True)
        g.ref_db.row_factory = sqlite3.Row
    return g.ref_db


def bcm_reference(car, control_unit, channel):
    """Reference values for a BCM channel from other Mk7s, or None.

    Only used for 09 Central Electrics on Mk7 cars - the MK8 BCM is different.
    """
    ref = get_ref_db()
    if ref is None or "MK8" in car.upper() or not control_unit.startswith("09"):
        return None
    row = ref.execute(
        "SELECT * FROM bcm_channels WHERE channel_de = ?", (channel,)
    ).fetchone()
    if row is None:
        # allow the channel to be typed without its "(12)-" prefix
        matches = ref.execute(
            "SELECT * FROM bcm_channels WHERE channel_de LIKE ?", ("%)-" + channel,)
        ).fetchall()
        if len(matches) != 1:
            return None
        row = matches[0]
    values = ref.execute(
        """SELECT cars.name, cars.contributor, v.value
           FROM bcm_values v JOIN bcm_cars cars ON cars.id = v.car_id
           WHERE v.channel_id = ? ORDER BY cars.id""",
        (row["id"],),
    ).fetchall()
    if not values:
        return None
    common, count = Counter(v["value"] for v in values).most_common(1)[0]
    return {"channel": row, "cars": values, "common": common, "common_count": count}


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
    return render_template("add.html", control_units=CONTROL_UNITS)


@app.route("/channels/<module>")
def channels(module):
    """Channel suggestions for one control unit, like OBD11's adaptation list.

    `module` is the address code, e.g. "09". Returns your own previously
    logged channels for that module, plus the BCM reference list for 09.
    """
    code = module.strip().split(" ")[0].upper()
    results, seen = [], set()

    for row in get_db().execute(
        """SELECT DISTINCT channel FROM changes
           WHERE UPPER(control_unit) = ? OR UPPER(control_unit) LIKE ?
           ORDER BY channel""",
        (code, code + " %"),
    ):
        results.append({"value": row["channel"], "label": "Logged before"})
        seen.add(row["channel"])

    ref = get_ref_db()
    if code == "09" and ref is not None:
        for row in ref.execute(
            "SELECT channel_de, description_en FROM bcm_channels ORDER BY id"
        ):
            if row["channel_de"] not in seen:
                results.append({"value": row["channel_de"], "label": row["description_en"]})

    return jsonify(results)

@app.route("/change/<int:change_id>")
def detail(change_id):
    change = get_db().execute(
        "SELECT * FROM changes WHERE id = ?", (change_id,)
    ).fetchone()
    if change is None:
        return "Change not found", 404
    ref = bcm_reference(change["car"], change["control_unit"], change["channel"])
    return render_template("detail.html", c=change, ref=ref)


@app.route("/change/<int:change_id>/toggle-revert", methods=["POST"])
def toggle_revert(change_id):
    db = get_db()
    db.execute(
        "UPDATE changes SET reverted = 1 - reverted WHERE id = ?", (change_id,)
    )
    db.commit()
    return redirect(url_for("detail", change_id=change_id))

if __name__ == "__main__":
    app.run(debug=True, port=5001)