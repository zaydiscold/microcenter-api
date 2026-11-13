"""SQLite-backed cache and cross-process pacing; stores no cookies or tokens."""

import hashlib, json, random, sqlite3, time
from pathlib import Path


class Storage:
    def __init__(
        self, path, *, delay=4.0, jitter=1.0, clock=time.time, sleep=time.sleep
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.delay = max(1.0, float(delay))
        self.jitter = max(0, float(jitter))
        self.clock = clock
        self.sleep = sleep
        with self.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, observed REAL, value TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS pacing (id INTEGER PRIMARY KEY CHECK(id=1), next_time REAL)"
            )
            db.execute("INSERT OR IGNORE INTO pacing VALUES (1,0)")

    def db(self):
        return sqlite3.connect(self.path, timeout=60)

    @staticmethod
    def key(request):
        return hashlib.sha256(
            json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def get(self, key, ttl):
        if ttl <= 0:
            return None
        with self.db() as db:
            r = db.execute(
                "SELECT observed,value FROM cache WHERE key=?", (key,)
            ).fetchone()
        return json.loads(r[1]) if r and self.clock() - r[0] <= ttl else None

    def put(self, key, value):
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                (key, self.clock(), json.dumps(value)),
            )

    def wait(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self.clock()
            reserved = max(
                now, db.execute("SELECT next_time FROM pacing WHERE id=1").fetchone()[0]
            )
            db.execute(
                "UPDATE pacing SET next_time=? WHERE id=1",
                (reserved + self.delay + random.uniform(0, self.jitter),),
            )
        if reserved > now:
            self.sleep(reserved - now)
