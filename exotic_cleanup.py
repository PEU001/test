# exotic_cleanup.py
import os
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.mp4 import MP4

# ------------------------------
#  Listes blanches (standards)
# ------------------------------
STANDARD_TAGS_ID3 = {
    "TIT2","TALB","TPE1","TPE2","TPE3","TPE4","TCON","TDRC","TRCK","TPOS","TCOM","TEXT","TBPM",
    "TSOA","TSOP","TSOT","TSO2","TSRC","TKEY","TENC","COMM","USLT","APIC","PCNT","POPM","PRIV","UFID","WXXX",
    "TXXX"
}

ALLOWED_TXXX_DESCS = {
    "RATING","MUSICBRAINZ_RATING","MUSICBRAINZ_RATING_VOTES",
    "MusicBrainz Track Id","MusicBrainz Recording Id","MusicBrainz Release Id",
    "MusicBrainz Release Group Id","MusicBrainz Album Id","MusicBrainz Artist Id",
    "MusicBrainz Album Artist Id","Acoustid Id","Acoustid Fingerprint",
    "ReplayGain","REPLAYGAIN_TRACK_GAIN","REPLAYGAIN_ALBUM_GAIN",
    "REPLAYGAIN_TRACK_PEAK","REPLAYGAIN_ALBUM_PEAK"
}

STANDARD_TAGS_VORBIS = {
    "ARTIST","ALBUM","TITLE","ALBUMARTIST","TRACKNUMBER","TRACKTOTAL",
    "DISCNUMBER","DISCTOTAL","GENRE","DATE","ORIGINALDATE","ORIGINALYEAR",
    "COMMENT","LYRICS","BARCODE","CATALOGNUMBER","ISRC","SCRIPT","LANGUAGE",
    "RATING","MUSICBRAINZ_RATING","MUSICBRAINZ_RATING_VOTES"
}
ALLOWED_VORBIS_PREFIXES = ("MUSICBRAINZ_","ACOUSTID","REPLAYGAIN")

STANDARD_TAGS_MP4 = {
    "©ART","©alb","©nam","©day","©gen","trkn","disk","aART","cpil","tmpo"
}
ALLOWED_MP4_FREEFORM_KEYWORDS = ("musicbrainz","acoustid","rating","replaygain")


# =====================================================================
#   analyse_tags_and_cover()  —  EXISTE BIEN & SANS ERREUR
# =====================================================================
def analyze_tags_and_cover(audio, path: str):
    """
    Analyse les tags d’un fichier audio et détecte :
    - la liste des tags exotiques
    - la présence d’une pochette (cover)

    Retourne : (list[str], bool)
    """
    ext = os.path.splitext(path)[1].lower()

    # -------- MP3 --------
    if ext == ".mp3":
        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            return [], False

        exotic = []
        cover = any(id3.getall("APIC"))

        for f in id3.values():
            if f.FrameID not in STANDARD_TAGS_ID3:
                exotic.append(f.FrameID)

        return exotic, cover

    # -------- FLAC / OGG / OPUS --------
    if isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        exotic = []
        tags = (audio.tags or {}).keys()

        for k in tags:
            ku = k.upper()
            if ku in STANDARD_TAGS_VORBIS:
                continue
            if any(ku.startswith(p) for p in ALLOWED_VORBIS_PREFIXES):
                continue
            exotic.append(k)

        cover = hasattr(audio, "pictures") and bool(audio.pictures)
        return exotic, cover

    # -------- MP4 / M4A --------
    if isinstance(audio, MP4):
        exotic = []
        for k in (audio.tags or {}).keys():
            if k in STANDARD_TAGS_MP4:
                continue
            if k.lower().startswith("----:"):
                if any(kw in k.lower() for kw in ALLOWED_MP4_FREEFORM_KEYWORDS):
                    continue
            exotic.append(k)

        cover = "covr" in (audio.tags or {})
        return exotic, cover

    return [], False


# =====================================================================
#   remove_exotic_tags() —  EXISTE BIEN & SANS ERREUR
# =====================================================================
def remove_exotic_tags(audio, path: str, mode: str,
                       allow_txxx: set, allow_vorbis: set, allow_mp4: set):

    ext = os.path.splitext(path)[1].lower()
    removed = []

    # -------- MP3 --------
    if ext == ".mp3":
        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            return removed

        # Frames non standard, sauf TXXX
        for f in list(id3.values()):
            if f.FrameID not in STANDARD_TAGS_ID3 and f.FrameID != "TXXX":
                id3.delall(f.FrameID)
                removed.append(f.FrameID)

        # STRICT : filtrer aussi les TXXX
        if mode == "strict":
            keep = []
            for f in id3.getall("TXXX"):
                desc = f.desc or ""
                if desc in ALLOWED_TXXX_DESCS or desc in allow_txxx:
                    keep.append(f)
                else:
                    removed.append("TXXX:" + desc)
            id3.setall("TXXX", keep)

        id3.save(v2_version=3)
        return removed

    # -------- FLAC / OGG / OPUS --------
    if isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        for k in list((audio.tags or {}).keys()):
            ku = k.upper()
            if ku in STANDARD_TAGS_VORBIS or any(ku.startswith(p) for p in ALLOWED_VORBIS_PREFIXES):
                continue
            if k in allow_vorbis:
                continue
            try:
                del audio.tags[k]
                removed.append(k)
            except Exception:
                pass

        audio.save()
        return removed

    # -------- MP4 / M4A --------
    if isinstance(audio, MP4):
        for k in list((audio.tags or {}).keys()):
            if k in STANDARD_TAGS_MP4:
                continue
            if k in allow_mp4:
                continue
            if k.lower().startswith("----:"):
                keep_free = any(kw in k.lower() for kw in ALLOWED_MP4_FREEFORM_KEYWORDS)
                if mode == "conservative" and keep_free:
                    continue
                if mode == "strict" and keep_free:
                    continue
            try:
                del audio.tags[k]
                removed.append(k)
            except Exception:
                pass

        audio.save()
        return removed

    return removed
