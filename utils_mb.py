#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mb_rating_tag.py — Script principal (COMPLET)

Fonctionnalités :
- Récupère la note MusicBrainz (0–5) et l’écrit dans les tags (Vorbis/ID3/MP4).
- Option POPM (MP3).
- Recherche MBID (artist + title + dur) si manquant.
- Nettoyage des tags exotiques (conservative/strict + listes d’exceptions).
- Détection de pochette.
- Backup et restauration des tags.
- Cache local SQLite (ratings + résolutions de recherche).
- Rapport HTML + log texte.

Python 3.8+ (testé 3.12.8)
Dépendances : mutagen, requests
"""

import os
import sys
import time
import argparse
from datetime import datetime
from mutagen import File

from utils_mb import (
    write_log, iter_audio_files, extract_mb_recording_id, extract_basic_identity,
    mb_get_recording_rating, mb_search_recording, write_rating_generic
)
from cache import MbCache
from exotic_cleanup import analyze_tags_and_cover, remove_exotic_tags
from backup_restore import backup_tags, restore_tags
from report_html import generate_html_report


RATE_LIMIT_SECONDS = 1.1  # règle MusicBrainz : max 1 req/s


def process_file(
    path: str,
    root: str,
    ua: str,
    write_popm: bool,
    search_fallback: bool,
    dry_run: bool,
    remove_exotic: bool,
    exotic_mode: str,
    allow_txxx: set,
    allow_vorbis: set,
    allow_mp4: set,
    do_backup: bool,
    do_restore: bool,
    backup_dir: str,
    cache: "MbCache | None" = None,
) -> dict:
    """Traite un fichier et retourne un dict de résultat (pour le rapport)."""

    rel = os.path.relpath(path, root) if os.path.isdir(root) else os.path.basename(path)
    result = {
        "file": rel,
        "status": "skip",
        "mbid": None,
        "rating": None,
        "votes": None,
        "artist": None,
        "title": None,
        "duration_ms": None,
        "has_cover": None,
        "exotic_tags": [],
        "removed_exotic": [],
        "message": "",
    }

    try:
        audio = File(path, easy=False)
        if audio is None:
            msg = "Non audio ou format non supporté"
            write_log("skip", rel, msg)
            result.update({"status": "skip", "message": msg})
            return result

        # ---- Restauration (prioritaire) ----
        if do_restore:
            ok, msg = restore_tags(path, rel, backup_dir)
            write_log("restore", rel, msg)
            result.update({"status": "restore", "message": msg})
            # Réanalyse (exotiques + pochette) après restauration
            audio2 = File(path, easy=False)
            ex2, cov2 = analyze_tags_and_cover(audio2, path)
            result.update({"exotic_tags": ex2, "has_cover": cov2})
            return result

        # ---- Analyse préliminaire (exotiques + pochette) ----
        exotic, has_cover = analyze_tags_and_cover(audio, path)
        result["exotic_tags"] = exotic
        result["has_cover"] = has_cover

        # ---- Backup avant modifs ----
        if do_backup:
            bpath = backup_tags(audio, path, rel, backup_dir)
            write_log("backup", rel, f"Backup: {bpath}")
            result["backup"] = bpath

        # ---- Nettoyage éventuel des tags exotiques ----
        if remove_exotic and exotic:
            if dry_run:
                write_log("plan-clean", rel, f"Suppression prévue ({exotic_mode}) : {', '.join(exotic)}")
                result["removed_exotic"] = exotic[:]  # planifié
            else:
                removed = remove_exotic_tags(audio, path, exotic_mode, allow_txxx, allow_vorbis, allow_mp4)
                if removed:
                    write_log("clean", rel, f"Supprimés ({exotic_mode}) : {', '.join(removed)}")
                result["removed_exotic"] = removed
                # Recharger le fichier (tags à jour)
                audio = File(path, easy=False)

        # ---- Identification MBID / identité basique ----
        mbid = extract_mb_recording_id(audio, path)
        artist, title, duration_ms = extract_basic_identity(audio, path)
        result.update({"artist": artist, "title": title, "duration_ms": duration_ms})

        # ---- Cache : tentative de hit ----
        value_votes = None
        if mbid and cache:
            value_votes = cache.get_rating(mbid)
        if not mbid and cache:
            cached_mbid = cache.get_search_mbid(artist, title, duration_ms)
            if cached_mbid:
                mbid = cached_mbid

        # ---- Recherche si pas de MBID ----
        if not mbid and not (search_fallback and artist and title):
            msg = "Aucun MBID et infos insuffisantes pour recherche"
            write_log("skip", rel, msg)
            result.update({"status": "skip", "message": msg})
            return result

        if mbid:
            if not value_votes:
                value_votes = mb_get_recording_rating(mbid, ua)
                time.sleep(RATE_LIMIT_SECONDS)
                if cache and value_votes is not None:
                    cache.set_rating(mbid, value_votes[0], value_votes[1])
        else:
            mbid = mb_search_recording(artist or "", title or "", duration_ms, ua)
            time.sleep(RATE_LIMIT_SECONDS)
            if cache and mbid:
                cache.set_search_mbid(artist, title, duration_ms, mbid)
            if not mbid:
                msg = f"Recherche sans résultat pour {artist} - {title}"
                write_log("not-found", rel, msg)
                result.update({"status": "not-found", "message": msg})
                return result
            value_votes = cache.get_rating(mbid) if cache else None
            if not value_votes:
                value_votes = mb_get_recording_rating(mbid, ua)
                time.sleep(RATE_LIMIT_SECONDS)
                if cache and value_votes is not None:
                    cache.set_rating(mbid, value_votes[0], value_votes[1])

        result["mbid"] = mbid
        if not value_votes or value_votes[0] is None:
            msg = f"Aucune note pour MBID {mbid}"
            write_log("not-found", rel, msg)
            result.update({"status": "not-found", "message": msg})
            return result

        rating, votes = value_votes
        result["rating"] = float(rating)
        result["votes"] = votes

        if dry_run:
            msg = f"(dry-run) MBID={mbid} rating={rating} votes={votes}"
            write_log("ok(dry)", rel, msg)
            result.update({"status": "ok(dry)", "message": msg})
            return result

        # ---- Écriture des tags ----
        write_rating_generic(audio, path, float(rating), votes, write_popm)
        msg = f"MBID={mbid} rating={rating} votes={votes}"
        write_log("ok", rel, msg)
        result.update({"status": "ok", "message": msg})
        return result

    except Exception as e:
        write_log("error", rel, f"{type(e).__name__}: {e}")
        result.update({"status": "error", "message": f"{type(e).__name__}: {e}"})
        return result


def main():
    p = argparse.ArgumentParser(
        description="MusicBrainz rating + log + report + cleanup + backup/restore + cache"
    )
    p.add_argument("path", help="Fichier ou dossier")
    p.add_argument("--ua", required=True, help="User-Agent requis par MusicBrainz (ex: 'MonApp/1.0 (email)')")
    p.add_argument("--write-popm", action="store_true", help="(MP3) Ecrire aussi POPM (0..255).")
    p.add_argument("--search-fallback", action="store_true", help="Si pas de MBID, recherche par artist+title+durée.")
    p.add_argument("--dry-run", action="store_true", help="Simulation : n'écrit pas, ne supprime pas.")
    # Nettoyage exotiques
    p.add_argument("--remove-exotic", action="store_true", help="Supprime les tags exotiques.")
    p.add_argument("--exotic-mode", choices=["conservative", "strict"], default="conservative")
    p.add_argument("--exotic-allow-txxx", default="", help="Descriptions TXXX à conserver (séparées par ';').")
    p.add_argument("--exotic-allow-vorbis", default="", help="Clés Vorbis à conserver (séparées par ';').")
    p.add_argument("--exotic-allow-mp4", default="", help="Atoms MP4 à conserver (séparées par ';').")
    # Rapport
    p.add_argument("--report", default="", help="Chemin du rapport HTML (défaut auto).")
    # Backup / Restore
    p.add_argument("--backup-tags", action="store_true", help="Sauvegarde des tags avant modifs.")
    p.add_argument("--restore-tags", action="store_true", help="Restaure les tags depuis backups (aucune autre action).")
    p.add_argument("--backup-dir", default="backups", help="Répertoire de backups (défaut: backups/).")
    # Cache local
    p.add_argument("--cache", action="store_true", help="Active le cache local SQLite.")
    p.add_argument("--cache-db", default=".mbcache.sqlite", help="Fichier cache (défaut: .mbcache.sqlite).")
    p.add_argument("--cache-ttl", type=int, default=86400, help="Durée de validité du cache en secondes (défaut: 86400).")
    p.add_argument("--cache-mode", choices=["ro", "rw", "refresh"], default="rw",
                   help="ro=read-only, rw=lecture/écriture, refresh=ignore TTL et réécrit.")

    args = p.parse_args()

    # Restore = prioritaire, on désactive autres modifs
    if args.restore_tags:
        args.remove_exotic = False
        args.write_popm = False
        args.dry_run = False

    allow_txxx = set([s for s in args.exotic_allow_txxx.split(";") if s.strip()])
    allow_vorbis = set([s for s in args.exotic_allow_vorbis.split(";") if s.strip()])
    allow_mp4 = set([s for s in args.exotic_allow_mp4.split(";") if s.strip()])

    cache = None
    if args.cache:
        cache = MbCache(args.cache_db, mode=args.cache_mode, ttl=args.cache_ttl)

    started = datetime.now()
    results = []
    target = args.path
    try:
        for fpath in iter_audio_files(target):
            res = process_file(
                path=fpath,
                root=target,
                ua=args.ua,
                write_popm=args.write_popm,
                search_fallback=args.search_fallback,
                dry_run=args.dry_run,
                remove_exotic=args.remove_exotic,
                exotic_mode=args.exotic_mode,
                allow_txxx=allow_txxx,
                allow_vorbis=allow_vorbis,
                allow_mp4=allow_mp4,
                do_backup=args.backup_tags,
                do_restore=args.restore_tags,
                backup_dir=args.backup_dir,
                cache=cache,
            )
            results.append(res)
    finally:
        if cache:
            cache.close()

    ended = datetime.now()
    report_path = args.report or f"mb_rating_report_{ended.strftime('%Y%m%d_%H%M%S')}.html"
    generate_html_report(results, started, ended, report_path)
    print("Terminé.")
    print(" - Log: mb_rating_tag.log")
    print(f" - Report: {report_path}")


if __name__ == "__main__":
    main()
