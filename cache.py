
# cache.py
import sqlite3, time

class MbCache:
    def __init__(self, db_path: str, mode: str = 'rw', ttl: int = 86400):
        self.db_path = db_path
        self.mode = mode
        self.ttl = ttl
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute('PRAGMA journal_mode=WAL;')
        self._init()

    def _init(self):
        c = self.conn.cursor()
        c.execute(
            CREATE TABLE IF NOT EXISTS ratings (
              mbid TEXT PRIMARY KEY,
              rating REAL,
              votes INTEGER,
              fetched_at INTEGER
            )
        )
        c.execute(
            CREATE TABLE IF NOT EXISTS search_map (
              qkey TEXT PRIMARY KEY,
              mbid TEXT,
              fetched_at INTEGER
            )
        )
        self.conn.commit()

    @staticmethod
    def key(artist, title, duration_ms):
        a=(artist or '').strip().lower(); t=(title or '').strip().lower(); d=int(round((duration_ms or 0)/1000))
        return f"{a}|{t}|{d}"

    def get_rating(self, mbid: str):
        if self.mode == 'refresh': return None
        c=self.conn.cursor(); c.execute('SELECT rating,votes,fetched_at FROM ratings WHERE mbid=?',(mbid,))
        r=c.fetchone();
        if not r: return None
        rating,votes,ts=r
        if self.mode!='ro' and (time.time()-ts)>self.ttl: return None
        return rating, votes

    def set_rating(self, mbid:str, rating, votes):
        if self.mode=='ro': return
        c=self.conn.cursor(); c.execute(
            INSERT INTO ratings(mbid,rating,votes,fetched_at)
            VALUES(?,?,?,?)
            ON CONFLICT(mbid) DO UPDATE SET rating=excluded.rating, votes=excluded.votes, fetched_at=excluded.fetched_at
        ,(mbid,rating,votes,int(time.time())))
        self.conn.commit()

    def get_search_mbid(self, artist, title, duration_ms):
        if self.mode == 'refresh': return None
        q=self.key(artist,title,duration_ms)
        c=self.conn.cursor(); c.execute('SELECT mbid,fetched_at FROM search_map WHERE qkey=?',(q,))
        r=c.fetchone();
        if not r: return None
        mbid,ts=r
        if self.mode!='ro' and (time.time()-ts)>self.ttl: return None
        return mbid

    def set_search_mbid(self, artist,title,duration_ms,mbid:str):
        if self.mode=='ro': return
        q=self.key(artist,title,duration_ms)
        c=self.conn.cursor(); c.execute(
            INSERT INTO search_map(qkey,mbid,fetched_at)
            VALUES(?,?,?)
            ON CONFLICT(qkey) DO UPDATE SET mbid=excluded.mbid, fetched_at=excluded.fetched_at
        ,(q,mbid,int(time.time())))
        self.conn.commit()

    def close(self):
        try: self.conn.close()
        except: pass
