
# utils_mb.py — ultra-safe MusicBrainz helpers (Python 3.8+)
import os
import re
import time
import threading
import requests
from requests.exceptions import ConnectionError, ReadTimeout, ChunkedEncodingError
from mutagen import File
from mutagen.id3 import ID3, ID3NoHeaderError, TXXX, POPM
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.mp4 import MP4, MP4FreeForm

API_ROOT = "https://musicbrainz.org/ws/2"
LOG_FILE = "mb_rating_tag.log"
AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".mp4", ".alac"}

# ---- Ultra-strict throttle ----
_MIN_INTERVAL = 1.5  # seconds between ANY two MB calls
_last_call_ts = 0.0
_lock = threading.Lock()
_session = requests.Session()

# In-run caches (avoid repeated hits within same run)
_mem_rating_rec = {}        # rec_mbid -> (value, votes) or None
_mem_releases_by_rec = {}   # rec_mbid -> first release MBID or None
_mem_rgid_by_release = {}   # release_mbid -> rgid or None
_mem_rating_rg = {}         # rgid -> (value, votes) or None


def _rate_limit():
    global _last_call_ts
    with _lock:
        now = time.time()
        delta = now - _last_call_ts
        if delta < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - delta)
        _last_call_ts = time.time()


def _safe_get(url: str, headers: dict, params: dict, timeout: int = 15, retries: int = 3):
    """GET with throttle + manual retries & backoff. Returns requests.Response.
    Retries on ConnectionError/ReadTimeout/ChunkedEncodingError and HTTP 429/503.
    """
    backoff = 2.0
    for attempt in range(1, retries + 1):
        _rate_limit()
        try:
            resp = _session.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code in (429, 503):
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
            return resp
        except (ConnectionError, ReadTimeout, ChunkedEncodingError):
            if attempt >= retries:
                raise
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("_safe_get: exhausted retries")


# ---------------- Log ----------------
def write_log(status: str, file_rel: str, details: str, log_file: str = LOG_FILE):
    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    line = f"{ts} | {status.upper()} | {file_rel} | {details}"
    with open(log_file, 'a', encoding='utf-8', errors='replace') as f:
        f.write(line)


# --------------- Helpers ---------------
def read_string(v):
    if v is None:
        return None
    if isinstance(v, list):
        return read_string(v[0]) if v else None
    if isinstance(v, bytes):
        try:
            return v.decode('utf-8', 'replace')
        except Exception:
            return None
    return str(v)


# --------------- MBID / Identity ---------------
def extract_mb_recording_id(audio, path: str):
    ext = os.path.splitext(path)[1].lower()
    if isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        if audio.tags:
            for key in ("MUSICBRAINZ_TRACKID","MUSICBRAINZ_RECORDINGID","MB_TRACKID"):
                val = audio.tags.get(key)
                if val:
                    s = read_string(val)
                    if s and re.match(r"^[0-9a-f-]{36}$", s, re.I):
                        return s
    if ext == ".mp3":
        try:
            id3 = ID3(path)
            for frame in id3.getall("TXXX"):
                desc = (frame.desc or '').strip().lower()
                if desc in {"musicbrainz track id","musicbrainz_trackid","musicbrainz recording id"}:
                    text = read_string(frame.text)
                    if text and re.match(r"^[0-9a-f-]{36}$", text, re.I):
                        return text
        except ID3NoHeaderError:
            pass
    if ext in {".m4a",".mp4"} and isinstance(audio, MP4):
        for k in (audio.tags or {}).keys():
            if k.lower().startswith("----:") and "musicbrainz" in k.lower() and "track" in k.lower():
                val = audio.tags.get(k)
                s = read_string(val)
                if s and re.match(r"^[0-9a-f-]{36}$", s, re.I):
                    return s
    return None


def extract_basic_identity(audio, path: str):
    ext = os.path.splitext(path)[1].lower()
    artist = title = None
    duration_ms = None
    if hasattr(audio, 'info') and getattr(audio.info, 'length', None):
        duration_ms = int(audio.info.length * 1000)
    if isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        tags = audio.tags or {}
        artist = read_string(tags.get('ARTIST')) or read_string(tags.get('ALBUMARTIST'))
        title = read_string(tags.get('TITLE'))
    elif ext == '.mp3':
        try:
            id3 = ID3(path)
            artist = read_string(getattr(id3.get('TPE1'),'text',None))
            title = read_string(getattr(id3.get('TIT2'),'text',None))
        except ID3NoHeaderError:
            pass
    elif ext in {'.m4a','.mp4'} and isinstance(audio, MP4):
        tags = audio.tags or {}
        artist = read_string(tags.get('©ART'))
        title = read_string(tags.get('©nam'))
    return artist, title, duration_ms


# --------------- MusicBrainz API helpers (ultra-safe) ---------------
def _headers(ua: str):
    return {"User-Agent": ua or "mbtools/1.0 (no-contact)"}


def mb_get_recording_rating(mbid: str, ua: str):
    if mbid in _mem_rating_rec:
        return _mem_rating_rec[mbid]
    url = f"{API_ROOT}/recording/{mbid}"
    params = {"inc":"ratings","fmt":"json"}
    r = _safe_get(url, _headers(ua), params)
    if r.status_code == 404:
        _mem_rating_rec[mbid] = None
        return None
    r.raise_for_status()
    data = r.json()
    rating = data.get('rating', {})
    val = rating.get('value')
    votes = rating.get('votes-count')
    out = (val, votes)
    _mem_rating_rec[mbid] = out
    return out


def mb_search_recording(artist: str, title: str, duration_ms: int, ua: str):
    query = f'recording:"{title}" AND artist:"{artist}"'
    url = f"{API_ROOT}/recording"
    params = {"query": query, "fmt":"json", "limit": 5}
    r = _safe_get(url, _headers(ua), params)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    recs = data.get('recordings') or []
    if not recs:
        return None
    recs.sort(key=lambda x: x.get('score',0), reverse=True)
    best = recs[0]
    if duration_ms:
        def penalty(rec):
            length = rec.get('length') or 10**9
            return abs(length - duration_ms)
        recs.sort(key=penalty)
        if abs((recs[0].get('length') or 10**9) - duration_ms) <= 2000:
            best = recs[0]
    return best.get('id')


def mb_get_first_release_id_for_recording(rec_mbid: str, ua: str):
    if rec_mbid in _mem_releases_by_rec:
        return _mem_releases_by_rec[rec_mbid]
    url = f"{API_ROOT}/recording/{rec_mbid}"
    params = {"inc":"releases","fmt":"json"}
    r = _safe_get(url, _headers(ua), params)
    if r.status_code == 404:
        _mem_releases_by_rec[rec_mbid] = None
        return None
    r.raise_for_status()
    data = r.json()
    rels = data.get('releases') or []
    rid = rels[0]['id'] if rels else None
    _mem_releases_by_rec[rec_mbid] = rid
    return rid


def mb_get_release_group_id(release_mbid: str, ua: str):
    if release_mbid in _mem_rgid_by_release:
        return _mem_rgid_by_release[release_mbid]
    url = f"{API_ROOT}/release/{release_mbid}"
    params = {"inc":"release-groups","fmt":"json"}
    r = _safe_get(url, _headers(ua), params)
    if r.status_code == 404:
        _mem_rgid_by_release[release_mbid] = None
        return None
    r.raise_for_status()
    data = r.json()
    rg = data.get('release-group') or {}
    rgid = rg.get('id')
    _mem_rgid_by_release[release_mbid] = rgid
    return rgid


def mb_get_release_group_rating(rgid: str, ua: str):
    if rgid in _mem_rating_rg:
        return _mem_rating_rg[rgid]
    url = f"{API_ROOT}/release-group/{rgid}"
    params = {"inc":"ratings","fmt":"json"}
    r = _safe_get(url, _headers(ua), params)
    if r.status_code == 404:
        _mem_rating_rg[rgid] = None
        return None
    r.raise_for_status()
    data = r.json()
    rating = data.get('rating', {})
    val = rating.get('value')
    votes = rating.get('votes-count')
    out = (val, votes)
    _mem_rating_rg[rgid] = out
    return out


# --------------- Write rating (recording) ---------------
def write_rating_generic(audio, path: str, rating: float, votes: int, write_popm: bool):
    ext = os.path.splitext(path)[1].lower()
    rating_str = f"{rating:.1f}"
    votes_str = str(votes) if votes is not None else None

    if isinstance(audio,(FLAC,OggVorbis,OggOpus)):
        audio['RATING'] = rating_str
        audio['MUSICBRAINZ_RATING'] = rating_str
        if votes_str: audio['MUSICBRAINZ_RATING_VOTES'] = votes_str
        audio.save(); return

    if ext == '.mp3':
        try: id3 = ID3(path)
        except ID3NoHeaderError: id3 = ID3()
        keep=[]
        for f in id3.getall('TXXX'):
            d=(f.desc or '').lower()
            if d not in {'rating','musicbrainz_rating','musicbrainz_rating_votes'}:
                keep.append(f)
        id3.setall('TXXX', keep)
        id3.add(TXXX(encoding=3, desc='RATING', text=rating_str))
        id3.add(TXXX(encoding=3, desc='MUSICBRAINZ_RATING', text=rating_str))
        if votes_str:
            id3.add(TXXX(encoding=3, desc='MUSICBRAINZ_RATING_VOTES', text=votes_str))
        if write_popm:
            scaled = int(round((rating/5.0)*255))
            popms = [f for f in id3.getall('POPM') if getattr(f,'email','')!='musicbrainz@mb-rating']
            popms.append(POPM(email='musicbrainz@mb-rating', rating=scaled, count=0))
            id3.setall('POPM', popms)
        id3.save(v2_version=3); return

    if ext in {'.m4a','.mp4'} and isinstance(audio, MP4):
        ff_rating = '----:com.apple.iTunes:RATING'
        ff_mbr = '----:com.apple.iTunes:MUSICBRAINZ_RATING'
        ff_votes = '----:com.apple.iTunes:MUSICBRAINZ_RATING_VOTES'
        audio.tags[ff_rating] = [MP4FreeForm(rating_str.encode('utf-8'))]
        audio.tags[ff_mbr] = [MP4FreeForm(rating_str.encode('utf-8'))]
        if votes_str:
            audio.tags[ff_votes] = [MP4FreeForm(votes_str.encode('utf-8'))]
        audio.save(); return


# --------------- Write rating (release-group fallback) ---------------
def write_rg_rating_tags(audio, path: str, rating: float, votes: int):
    ext = os.path.splitext(path)[1].lower()
    rating_str = f"{rating:.1f}"
    votes_str = str(votes) if votes is not None else None

    if isinstance(audio,(FLAC,OggVorbis,OggOpus)):
        audio['RATING_RG'] = rating_str
        audio['MUSICBRAINZ_RG_RATING'] = rating_str
        if votes_str: audio['MUSICBRAINZ_RG_RATING_VOTES'] = votes_str
        audio.save(); return

    if ext == '.mp3':
        try: id3 = ID3(path)
        except ID3NoHeaderError: id3 = ID3()
        id3.add(TXXX(encoding=3, desc='RATING_RG', text=rating_str))
        id3.add(TXXX(encoding=3, desc='MUSICBRAINZ_RG_RATING', text=rating_str))
        if votes_str:
            id3.add(TXXX(encoding=3, desc='MUSICBRAINZ_RG_RATING_VOTES', text=votes_str))
        id3.save(v2_version=3); return

    if ext in {'.m4a','.mp4'} and isinstance(audio, MP4):
        ff_rating = '----:com.apple.iTunes:RATING_RG'
        ff_mbr = '----:com.apple.iTunes:MUSICBRAINZ_RG_RATING'
        ff_votes = '----:com.apple.iTunes:MUSICBRAINZ_RG_RATING_VOTES'
        audio.tags[ff_rating] = [MP4FreeForm(rating_str.encode('utf-8'))]
        audio.tags[ff_mbr] = [MP4FreeForm(rating_str.encode('utf-8'))]
        if votes_str:
            audio.tags[ff_votes] = [MP4FreeForm(votes_str.encode('utf-8'))]
        audio.save(); return


# --------------- File iteration ---------------
def iter_audio_files(root: str):
    if os.path.isfile(root):
        yield root
    else:
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if os.path.splitext(fname)[1].lower() in AUDIO_EXTS:
                    yield os.path.join(dirpath, fname)
