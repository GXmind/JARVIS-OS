"""Short-lived SQLite connections are safe across GUI and background workers."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import sqlite3
import uuid
from jarvis.infrastructure.system.paths import ROOT, local_path

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

class Store:
    def __init__(self, path=None):
        self.path = local_path(path or ROOT / "data/jarvis.sqlite3")
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL, created TEXT NOT NULL, state TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id,id);
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY, content TEXT NOT NULL, created TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def new_session(self, title="新对话"):
        sid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (sid, title, now()))
        return sid

    def sessions(self):
        with self.connect() as db:
            return db.execute("SELECT id,title,created FROM sessions ORDER BY created DESC,rowid DESC LIMIT 100").fetchall()

    def add_message(self, session_id, role, content, state=None):
        if role not in ("user", "assistant"):
            raise ValueError("无效的消息角色")
        with self.connect() as db:
            db.execute("INSERT INTO messages(session_id,role,content,created,state) VALUES (?,?,?,?,?)",
                       (session_id, role, content, now(), json.dumps(state or {}, ensure_ascii=False)))
            if role == "user":
                db.execute("UPDATE sessions SET title=? WHERE id=? AND title='新对话'",
                           (content[:26], session_id))

    def history(self, session_id, limit=30):
        with self.connect() as db:
            rows = db.execute(
                "SELECT role,content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit)).fetchall()
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    def remember(self, content):
        content = content.strip()
        if not content or len(content) > 2000:
            raise ValueError("记忆内容需为 1–2000 字。")
        with self.connect() as db:
            cur = db.execute("INSERT INTO memories(content,created) VALUES (?,?)", (content, now()))
            return cur.lastrowid

    def memories(self):
        with self.connect() as db:
            return db.execute("SELECT id,content,created FROM memories ORDER BY id DESC LIMIT 200").fetchall()

    def forget(self, memory_id):
        with self.connect() as db:
            db.execute("DELETE FROM memories WHERE id=?", (int(memory_id),))

    def recall(self, query, limit=5):
        # Bounded transparent character/word overlap, not an embedding model.
        query = query.casefold()
        candidates = []
        for memory_id, text, _ in self.memories():
            score = len(set(query) & set(text.casefold()) - set(" ，。！？的了是我你"))
            if score:
                candidates.append((score, memory_id, text))
        candidates.sort(reverse=True)
        return [item[2] for item in candidates[:limit]]
    def counts(self, session_id):
        with self.connect() as db:
            return {"memories": db.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
                    "messages": db.execute("SELECT COUNT(*) FROM messages WHERE session_id=?", (session_id,)).fetchone()[0]}
