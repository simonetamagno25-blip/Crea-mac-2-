import json
import sqlite3

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS regioni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS province (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regione_id INTEGER NOT NULL REFERENCES regioni(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    UNIQUE(regione_id, nome)
);

CREATE TABLE IF NOT EXISTS localita (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provincia_id INTEGER NOT NULL REFERENCES province(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'Comune',
    UNIQUE(provincia_id, nome)
);

CREATE TABLE IF NOT EXISTS onoranze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    localita_id INTEGER NOT NULL REFERENCES localita(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    indirizzo TEXT DEFAULT '',
    telefono TEXT DEFAULT '',
    email TEXT DEFAULT '',
    link TEXT DEFAULT '',
    note TEXT DEFAULT '',
    ordine INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_province_regione ON province(regione_id);
CREATE INDEX IF NOT EXISTS idx_localita_provincia ON localita(provincia_id);
CREATE INDEX IF NOT EXISTS idx_onoranze_localita ON onoranze(localita_id);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def count_rows(conn):
    counts = {}
    for table in ("regioni", "province", "localita", "onoranze"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return counts


def needs_migration(conn):
    counts = count_rows(conn)
    if any(counts.values()):
        return False
    for chiave in ("dati_onoranze", "dati_onoranze_backup"):
        row = conn.execute(
            "SELECT valore FROM impostazioni WHERE chiave = ?", (chiave,)
        ).fetchone()
        if row is not None and row[0].strip() not in ("", "{}"):
            return True
    return False


def migrate_from_json_blob(conn):
    row = conn.execute(
        "SELECT valore FROM impostazioni WHERE chiave = 'dati_onoranze'"
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT valore FROM impostazioni WHERE chiave = 'dati_onoranze_backup'"
        ).fetchone()
    if not row:
        return False

    conn.execute(
        """
        INSERT OR REPLACE INTO impostazioni (chiave, valore)
        VALUES ('dati_onoranze_backup', ?)
        """,
        (row[0],),
    )
    conn.commit()

    data = json.loads(row[0])
    save_data_from_json(conn, data)
    return True


def load_data_as_json(conn):
    result = {}
    regioni = conn.execute("SELECT id, nome FROM regioni ORDER BY nome COLLATE NOCASE").fetchall()

    for regione in regioni:
        result[regione["nome"]] = {}
        province = conn.execute(
            "SELECT id, nome FROM province WHERE regione_id = ? ORDER BY nome COLLATE NOCASE",
            (regione["id"],),
        ).fetchall()

        for provincia in province:
            result[regione["nome"]][provincia["nome"]] = {}
            localita = conn.execute(
                """
                SELECT id, nome, tipo FROM localita
                WHERE provincia_id = ?
                ORDER BY nome COLLATE NOCASE
                """,
                (provincia["id"],),
            ).fetchall()

            for loc in localita:
                onoranze = conn.execute(
                    """
                    SELECT nome, indirizzo, telefono, email, link, note
                    FROM onoranze
                    WHERE localita_id = ?
                    ORDER BY ordine, nome COLLATE NOCASE
                    """,
                    (loc["id"],),
                ).fetchall()

                entry = {"type": loc["tipo"] or "Comune"}
                if onoranze:
                    entry["onoranze"] = [
                        {
                            "name": o["nome"],
                            "address": o["indirizzo"] or "",
                            "phone": o["telefono"] or "",
                            "email": o["email"] or "",
                            "link": o["link"] or "",
                            "note": o["note"] or "",
                        }
                        for o in onoranze
                    ]
                result[regione["nome"]][provincia["nome"]][loc["nome"]] = entry

    return result


def save_data_from_json(conn, data):
    conn.execute("DELETE FROM regioni")

    for regione_nome, province_map in data.items():
        cur = conn.execute("INSERT INTO regioni (nome) VALUES (?)", (regione_nome,))
        regione_id = cur.lastrowid

        for provincia_nome, localita_map in province_map.items():
            cur = conn.execute(
                "INSERT INTO province (regione_id, nome) VALUES (?, ?)",
                (regione_id, provincia_nome),
            )
            provincia_id = cur.lastrowid

            for localita_nome, info in localita_map.items():
                if not isinstance(info, dict):
                    info = {}
                tipo = (info.get("type") or "Comune").strip() or "Comune"
                cur = conn.execute(
                    "INSERT INTO localita (provincia_id, nome, tipo) VALUES (?, ?, ?)",
                    (provincia_id, localita_nome, tipo),
                )
                localita_id = cur.lastrowid

                for ordine, onoranza in enumerate(info.get("onoranze") or []):
                    conn.execute(
                        """
                        INSERT INTO onoranze
                            (localita_id, nome, indirizzo, telefono, email, link, note, ordine)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            localita_id,
                            onoranza.get("name", "").strip(),
                            onoranza.get("address", "") or "",
                            onoranza.get("phone", "") or "",
                            onoranza.get("email", "") or "",
                            onoranza.get("link", "") or "",
                            onoranza.get("note", "") or "",
                            ordine,
                        ),
                    )

    conn.execute("DELETE FROM impostazioni WHERE chiave = 'dati_onoranze'")
    conn.commit()
