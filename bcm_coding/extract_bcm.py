"""
Extract dv52's MQB (Mk7) BCM adaptation-channel comparison PDF into SQLite.

The PDF is a wide spreadsheet printed in 9 vertical strips of 61 pages:
  strip 1        -> ID + English description
  strip 2        -> German channel name + Golf R value
  strips 3..8    -> 4 cars each
  strip 9        -> 2 cars
Rows line up by y-position across strips, so page N of every strip
holds the same channels.

Usage:  python extract_bcm.py "Modules code.pdf" bcm_reference.db
"""
import sqlite3
import sys

import pdfplumber

PAGES_PER_STRIP = 61

# (strip number, car name, contributor, BCM part number, BCM type)
CARS = [
    (2, "Golf R (RoW)", "Nut (VWW)", "5Q0-937-084-AJ", "MQBAB H"),
    (3, "110TDI (RoW)", "TDIJeff (VWW)", "5Q0-937-084-AE", "MQBAB H"),
    (3, "103TSI (RoW)", "Agentthumb (VWW)", "5Q0-937-086-AC", "PQ37BOSCH"),
    (3, "110TSI Highline MY16", "crherndo (VWW)", "5Q0-937-084-AN", "MQBAB H"),
    (3, "MY16 Mk7 Station Wagon DSG", "Loaner", "5Q0-937-086-AG", "PQ37BOSCH"),
    (4, "103TSI (RoW) - RT Ver 12.12", "DV52", "5Q0-937-084-N", "MQBAB M"),
    (4, "103TSI (RoW) - RT Ver 14.7", "DV52", "5Q0-937-084-N", "MQBAB M"),
    (4, "103TSI (RoW) - RT Ver 15.6", "DV52", "5Q0-937-084-N", "MQBAB M"),
    (4, "GTI SE 6MT", "Andy@RT (VWVortex)", "5Q0-937-087-K", "PQ37BOSCH"),
    (5, "2015 GTI SE 6MT", "Jezze269 (VWVortex)", "", "PQ37BOSCH"),
    (5, "Autobahn DSG - LP", "flygteye (VWVortex)", "5Q0-937-087-K", "PQ37BOSCH"),
    (5, "2015 S 1.8TSI 5MT (sunroof, bi-xenon, PDC)", "LIJetta (VWVortex)", "5Q0-937-087-R", "PQ37BOSCH"),
    (5, "2015 GTI S Manual with LP", "ABATurbo (VWVortex)", "5Q0-937-087-N", "PQ37BOSCH"),
    (6, "2015 TDI SEL - HID, manual", "burkut (RT Forum)", "5Q0-937-087-N", "PQ37BOSCH"),
    (6, "2015 1.8T Highline", "PanEuropean (VWVortex)", "5Q0-937-087-K", "PQ37BOSCH"),
    (6, "2016 GTI S NAR", "Ohsnapzombies (VWVortex)", "5Q0-937-087-AA", "PQ37BOSCH"),
    (6, "2016 USA GTI PP Autobahn (LP, DCC, DAP)", "bbjvwr (VWVortex)", "5Q0-937-087-AA", "PQ37BOSCH"),
    (7, "2016 Sportwagen S MT", "IceRacerX (RT Forum)", "5Q0-937-087-T", "PQ37BOSCH"),
    (7, "2015 TDI Highline Sportwagon", "DoctorKB (VWVortex)", "5Q0-937-087-R", "PQ37BOSCH"),
    (7, "GTD", "Phope (GolfGTD_UK)", "5Q0-937-084-AJ", "MQBAB H"),
    (7, "103kW 1.4TSI", "Bloggo (UK)", "5Q0-937-084-Q", "MQBAB H"),
    (8, "Golf Mk7", "g2dar (RT Forum)", "5Q0-937-084-AE", "MQBAB H"),
    (8, "GTI PP DSG", "Kevinm (GolfGTI_UK)", "5Q0-937-084-AE", "MQBAB H"),
    (8, "1.6 TDI with Lane Assist and bi-xenons", "BOFH (GolfGTI_UK)", "5Q0-937-084-AJ", "MQBAB H"),
    (8, "2016 Golf R", "Morde (VWW)", "5Q0-937-085-AF", "MQBAB H"),
    (9, "2016 Golf GTE", "Drive (RT Forum)", "5Q0-937-084-AN", "MQBAB H"),
    (9, "2014 Mk7 Golf GTI DSG", "MCK-Car-Sales (RT Forum)", "5Q0-937-085-T", "PQ37BOSCH"),
]

# x-centre of each car column in strips 3..9
CAR_COL_CENTRES = [100, 210, 320, 430]


def join(words):
    """Join words in reading order (line by line, left to right)."""
    words = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    return " ".join(w["text"] for w in words).strip()


_cache = {}


def words_on(pdf, i):
    """Read a page's words once, then release the page to save memory."""
    if i not in _cache:
        page = pdf.pages[i]
        _cache[i] = page.extract_words()
        page.close()
    return _cache.pop(i)


def row_anchors(words):
    """Channel IDs and their y-positions from a strip-1 page's words."""
    anchors = []
    for w in words:
        if w["x0"] < 90 and w["text"].isdigit():
            anchors.append((int(w["text"]), w["top"]))
    return anchors


def bucket(words, anchors):
    """Assign each word to the row whose band contains it."""
    rows = {cid: [] for cid, _ in anchors}
    for w in words:
        owner = None
        for cid, top in anchors:
            if w["top"] >= top - 2:
                owner = cid
            else:
                break
        if owner is not None:
            rows[owner].append(w)
    return rows


def main(pdf_path, db_path):
    pdf = pdfplumber.open(pdf_path)
    channels = {}      # id -> {"en": .., "de": ..}
    values = {}        # (id, car_index) -> value

    for n in range(PAGES_PER_STRIP):
        strip1 = words_on(pdf, n)
        anchors = row_anchors(strip1)
        if not anchors:
            continue

        # strip 1: English description
        rows = bucket([w for w in strip1 if w["x0"] >= 90], anchors)
        for cid, ws in rows.items():
            channels.setdefault(cid, {})["en"] = join(ws)

        # strip 2: German channel name + Golf R value
        words = words_on(pdf, PAGES_PER_STRIP + n)
        names = bucket([w for w in words if w["x0"] < 336], anchors)
        vals = bucket([w for w in words if w["x0"] >= 336], anchors)
        for cid in names:
            channels[cid]["de"] = join(names[cid])
            values[(cid, 0)] = join(vals[cid])

        # strips 3..9: car columns
        car_idx = 1
        for strip in range(3, 10):
            strip_cars = [c for c in CARS if c[0] == strip]
            words = words_on(pdf, (strip - 1) * PAGES_PER_STRIP + n)
            for col, _ in enumerate(strip_cars):
                centre = CAR_COL_CENTRES[col]
                mine = [
                    w for w in words
                    if min(CAR_COL_CENTRES[:len(strip_cars)],
                           key=lambda c: abs(c - (w["x0"] + w["x1"]) / 2)) == centre
                ]
                for cid, ws in bucket(mine, anchors).items():
                    values[(cid, car_idx + col)] = join(ws)
            car_idx += len(strip_cars)
        print(f"page {n + 1}/{PAGES_PER_STRIP}", end="\r")

    db = sqlite3.connect(db_path)
    db.executescript("""
        DROP TABLE IF EXISTS bcm_values;
        DROP TABLE IF EXISTS bcm_channels;
        DROP TABLE IF EXISTS bcm_cars;
        CREATE TABLE bcm_cars (
            id INTEGER PRIMARY KEY,
            name TEXT, contributor TEXT, part_number TEXT, bcm_type TEXT
        );
        CREATE TABLE bcm_channels (
            id INTEGER PRIMARY KEY,
            description_en TEXT,
            channel_de TEXT
        );
        CREATE TABLE bcm_values (
            channel_id INTEGER REFERENCES bcm_channels(id),
            car_id INTEGER REFERENCES bcm_cars(id),
            value TEXT,
            PRIMARY KEY (channel_id, car_id)
        );
    """)
    db.executemany(
        "INSERT INTO bcm_cars VALUES (?,?,?,?,?)",
        [(i + 1, c[1], c[2], c[3], c[4]) for i, c in enumerate(CARS)],
    )
    db.executemany(
        "INSERT INTO bcm_channels VALUES (?,?,?)",
        [(cid, ch.get("en", ""), ch.get("de", "")) for cid, ch in sorted(channels.items())],
    )
    db.executemany(
        "INSERT INTO bcm_values VALUES (?,?,?)",
        [(cid, car + 1, v) for (cid, car), v in values.items() if v],
    )
    db.commit()
    print(f"\n{len(channels)} channels, {len(CARS)} cars, "
          f"{sum(1 for v in values.values() if v)} values -> {db_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
