"""SQLite database layer for Lokus-Synapse."""
import sqlite3
import os
import json

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
DB_PATH = os.path.join(DB_DIR, 'synapse.db')

os.makedirs(DB_DIR, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT NOT NULL,
            directory TEXT NOT NULL,
            size INTEGER DEFAULT 0,
            modified TEXT,
            content TEXT,
            scanned_at TEXT
        );
        CREATE TABLE IF NOT EXISTS concepts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT DEFAULT 'keyword'
        );
        CREATE TABLE IF NOT EXISTS file_concepts (
            file_id INTEGER NOT NULL,
            concept_id INTEGER NOT NULL,
            weight REAL DEFAULT 1.0,
            PRIMARY KEY (file_id, concept_id)
        );
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            weight REAL DEFAULT 0.0,
            shared TEXT DEFAULT '[]',
            UNIQUE(source_id, target_id)
        );
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()


def clear_all():
    """Wipe all data for a fresh scan."""
    conn = get_conn()
    c = conn.cursor()
    for t in ['edges', 'file_concepts', 'files', 'concepts']:
        c.execute(f"DELETE FROM {t}")
    conn.commit()
    conn.close()


def insert_file(path, filename, ext, directory, size, modified, content):
    conn = get_conn()
    from datetime import datetime
    scanned_at = datetime.utcnow().isoformat()
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO files
                 (path,filename,extension,directory,size,modified,content,scanned_at)
                 VALUES (?,?,?,?,?,?,?,?)""",
              (path, filename, ext, directory, size, modified, content, scanned_at))
    fid = c.lastrowid
    conn.commit()
    conn.close()
    return fid


def get_file_by_path(path):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM files WHERE path=?", (path,))
    row = c.fetchone()
    conn.close()
    return row['id'] if row else None


def upsert_concept(name, category='keyword'):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO concepts (name,category) VALUES (?,?)", (name, category))
    c.execute("SELECT id FROM concepts WHERE name=?", (name,))
    cid = c.fetchone()['id']
    conn.commit()
    conn.close()
    return cid


def link_file_concept(file_id, concept_id, weight=1.0):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO file_concepts (file_id,concept_id,weight)
                 VALUES (?,?,?)""", (file_id, concept_id, weight))
    conn.commit()
    conn.close()


def insert_edge(src, tgt, weight, shared):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO edges (source_id,target_id,weight,shared)
                 VALUES (?,?,?,?)""", (src, tgt, weight, json.dumps(shared)))
    conn.commit()
    conn.close()


def get_all_files():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM files ORDER BY directory, filename").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_file_detail(fid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
    if not row:
        conn.close()
        return None
    concepts = conn.execute("""
        SELECT c.name, c.category, fc.weight
        FROM concepts c JOIN file_concepts fc ON c.id=fc.concept_id
        WHERE fc.file_id=? ORDER BY fc.weight DESC
    """, (fid,)).fetchall()
    edges_out = conn.execute("""
        SELECT e.target_id as other_id, e.weight, e.shared, f.filename, f.extension, f.directory
        FROM edges e JOIN files f ON e.target_id=f.id WHERE e.source_id=?
    """, (fid,)).fetchall()
    edges_in = conn.execute("""
        SELECT e.source_id as other_id, e.weight, e.shared, f.filename, f.extension, f.directory
        FROM edges e JOIN files f ON e.source_id=f.id WHERE e.target_id=?
    """, (fid,)).fetchall()
    conn.close()
    return {
        **dict(row),
        'concepts': [dict(c) for c in concepts],
        'connections': [dict(e) for e in edges_out + edges_in]
    }


def get_graph_data():
    files = get_all_files()
    if not files:
        return {'nodes': [], 'edges': []}

    conn = get_conn()
    nodes = []
    for f in files:
        concept_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM file_concepts WHERE file_id=?", (f['id'],)
        ).fetchone()['cnt']
        nodes.append({
            'id': f['id'],
            'label': f['filename'],
            'path': f['path'],
            'extension': f['extension'],
            'directory': f['directory'],
            'size': f['size'],
            'conceptCount': concept_count,
            'title': f"{f['path']}\n{concept_count} concepts"
        })

    edges_rows = conn.execute(
        "SELECT source_id, target_id, weight, shared FROM edges"
    ).fetchall()
    edges = []
    for e in edges_rows:
        edges.append({
            'from': e['source_id'],
            'to': e['target_id'],
            'weight': e['weight'],
            'shared': json.loads(e['shared']),
            'title': f"Similarity: {e['weight']:.2f}"
        })
    conn.close()
    return {'nodes': nodes, 'edges': edges}


def get_concept_graph_data():
    """Return concepts as nodes, files as edges (concept-centric view)."""
    conn = get_conn()
    concepts = conn.execute("""
        SELECT c.id, c.name, c.category, COUNT(fc.file_id) as file_count
        FROM concepts c JOIN file_concepts fc ON c.id=fc.concept_id
        GROUP BY c.id HAVING file_count >= 2
        ORDER BY file_count DESC
    """).fetchall()
    nodes = [{'id': f"c_{c['id']}", 'label': c['name'], 'category': c['category'],
              'fileCount': c['file_count'],
              'title': f"{c['name']}\n{c['category']}\nIn {c['file_count']} files"}
             for c in concepts]

    # Find concept pairs that co-occur in files
    pairs = conn.execute("""
        SELECT fc1.concept_id as c1, fc2.concept_id as c2, COUNT(DISTINCT fc1.file_id) as co_count
        FROM file_concepts fc1 JOIN file_concepts fc2 ON fc1.file_id=fc2.file_id
        WHERE fc1.concept_id < fc2.concept_id
        GROUP BY fc1.concept_id, fc2.concept_id
        HAVING co_count >= 1
    """).fetchall()
    edges = [{'from': f"c_{p['c1']}", 'to': f"c_{p['c2']}", 'weight': p['co_count'],
              'title': f"Co-occur in {p['co_count']} files"}
             for p in pairs]
    conn.close()
    return {'nodes': nodes, 'edges': edges}


def search(query):
    conn = get_conn()
    q = f"%{query}%"
    files = conn.execute(
        "SELECT id, path, filename, extension, directory FROM files WHERE filename LIKE ? OR path LIKE ?",
        (q, q)).fetchall()
    concepts = conn.execute(
        "SELECT id, name, category FROM concepts WHERE name LIKE ?", (q,)).fetchall()
    conn.close()
    return {
        'files': [dict(f) for f in files],
        'concepts': [dict(c) for c in concepts]
    }


def get_stats():
    conn = get_conn()
    fcount = conn.execute("SELECT COUNT(*) as c FROM files").fetchone()['c']
    ccount = conn.execute("SELECT COUNT(*) as c FROM concepts").fetchone()['c']
    ecount = conn.execute("SELECT COUNT(*) as c FROM edges").fetchone()['c']
    exts = conn.execute(
        "SELECT extension, COUNT(*) as c FROM files GROUP BY extension ORDER BY c DESC"
    ).fetchall()
    conn.close()
    return {
        'fileCount': fcount,
        'conceptCount': ccount,
        'edgeCount': ecount,
        'extensions': [dict(e) for e in exts]
    }


def set_meta(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO meta (key,value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()


def get_meta(key):
    conn = get_conn()
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else None
