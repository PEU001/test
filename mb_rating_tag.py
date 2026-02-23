
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mb_rating_tag.py — Script principal (ULTRA-SAFE + fallback release-group)
"""
import os, argparse
from datetime import datetime
from mutagen import File

from utils_mb import (
    write_log, iter_audio_files, extract_mb_recording_id, extract_basic_identity,
    mb_get_recording_rating, mb_search_recording, write_rating_generic,
    mb_get_first_release_id_for_recording, mb_get_release_group_id, mb_get_release_group_rating,
    write_rg_rating_tags
)
from cache import MbCache
from exotic_cleanup import analyze_tags_and_cover, remove_exotic_tags
from backup_restore import backup_tags, restore_tags
from report_html import generate_html_report


def process_file(path: str, root: str, ua: str,
                 write_popm: bool, search_fallback: bool, dry_run: bool,
                 remove_exotic: bool, exotic_mode: str,
                 allow_txxx: set, allow_vorbis: set, allow_mp4: set,
                 do_backup: bool, do_restore: bool, backup_dir: str,
                 cache: 'MbCache|None' = None) -> dict:

    rel = os.path.relpath(path, root) if os.path.isdir(root) else os.path.basename(path)
    result = {
        'file': rel, 'status': 'skip', 'mbid': None, 'mbid_rg': None, 'fallback': None,
        'rating': None, 'votes': None,
        'artist': None, 'title': None, 'duration_ms': None,
        'has_cover': None, 'exotic_tags': [], 'removed_exotic': [], 'message': ''
    }

    try:
        audio = File(path, easy=False)
        if audio is None:
            msg='Non audio ou format non supporté'; write_log('skip', rel, msg)
            result.update({'status':'skip','message':msg}); return result

        if do_restore:
            ok,msg = restore_tags(path, rel, backup_dir)
            write_log('restore', rel, msg)
            result.update({'status':'restore','message':msg})
            audio2 = File(path, easy=False)
            ex2, cov2 = analyze_tags_and_cover(audio2, path)
            result.update({'exotic_tags': ex2, 'has_cover': cov2})
            return result

        exotic, has_cover = analyze_tags_and_cover(audio, path)
        result['exotic_tags'] = exotic; result['has_cover'] = has_cover

        if do_backup:
            bpath = backup_tags(audio, path, rel, backup_dir)
            write_log('backup', rel, f'Backup: {bpath}')
            result['backup'] = bpath

        if remove_exotic and exotic:
            if dry_run:
                write_log('plan-clean', rel, f"Suppression prévue ({exotic_mode}) : {', '.join(exotic)}")
                result['removed_exotic'] = exotic[:]
            else:
                removed = remove_exotic_tags(audio, path, exotic_mode, allow_txxx, allow_vorbis, allow_mp4)
                if removed:
                    write_log('clean', rel, f"Supprimés ({exotic_mode}) : {', '.join(removed)}")
                result['removed_exotic'] = removed
                audio = File(path, easy=False)

        mbid = extract_mb_recording_id(audio, path)
        artist, title, duration_ms = extract_basic_identity(audio, path)
        result.update({'artist':artist,'title':title,'duration_ms':duration_ms})

        value_votes = None
        if mbid and cache:
            value_votes = cache.get_rating(mbid)
        if not mbid and cache:
            cached_mbid = cache.get_search_mbid(artist, title, duration_ms)
            if cached_mbid:
                mbid = cached_mbid

        if not mbid and not (search_fallback and artist and title):
            msg='Aucun MBID et infos insuffisantes pour recherche'; write_log('skip', rel, msg)
            result.update({'status':'skip','message':msg}); return result

        if mbid:
            if not value_votes:
                value_votes = mb_get_recording_rating(mbid, ua)
                if cache and value_votes is not None:
                    cache.set_rating(mbid, value_votes[0], value_votes[1])
        else:
            mbid = mb_search_recording(artist or '', title or '', duration_ms, ua)
            if cache and mbid:
                cache.set_search_mbid(artist, title, duration_ms, mbid)
            if not mbid:
                msg=f'Recherche sans résultat pour {artist} - {title}'; write_log('not-found', rel, msg)
                result.update({'status':'not-found','message':msg}); return result
            value_votes = cache.get_rating(mbid) if cache else None
            if not value_votes:
                value_votes = mb_get_recording_rating(mbid, ua)
                if cache and value_votes is not None:
                    cache.set_rating(mbid, value_votes[0], value_votes[1])

        result['mbid'] = mbid
        if value_votes and value_votes[0] is not None:
            rating, votes = value_votes
            result['rating']=float(rating); result['votes']=votes
            if dry_run:
                msg=f'(dry-run) MBID={mbid} rating={rating} votes={votes}'; write_log('ok(dry)', rel, msg)
                result.update({'status':'ok(dry)','message':msg}); return result
            write_rating_generic(audio, path, float(rating), votes, write_popm)
            msg=f'MBID={mbid} rating={rating} votes={votes}'; write_log('ok', rel, msg)
            result.update({'status':'ok','message':msg}); return result

        # ---------- FALLBACK : release-group ----------
        release_id = mb_get_first_release_id_for_recording(mbid, ua)
        if release_id:
            rgid = mb_get_release_group_id(release_id, ua)
            if rgid:
                rg_rating = mb_get_release_group_rating(rgid, ua)
                if rg_rating and rg_rating[0] is not None:
                    rg_value, rg_votes = rg_rating
                    result['mbid_rg'] = rgid
                    result['fallback'] = 'release-group'
                    result['rating'] = float(rg_value)
                    result['votes'] = rg_votes
                    if dry_run:
                        msg=f'(dry-run) FALLBACK RG: MBID_RG={rgid} rating={rg_value} votes={rg_votes}'
                        write_log('ok(dry)', rel, msg)
                        result.update({'status':'ok(dry)','message':msg}); return result
                    write_rg_rating_tags(audio, path, float(rg_value), rg_votes)
                    msg=f'FALLBACK RG: MBID_RG={rgid} rating={rg_value} votes={rg_votes}'
                    write_log('ok', rel, msg)
                    result.update({'status':'ok','message':msg}); return result

        msg = f"Aucune note pour MBID {mbid} (ni recording ni release-group)"
        write_log('not-found', rel, msg)
        result.update({'status':'not-found','message':msg}); return result

    except Exception as e:
        write_log('error', rel, f"{type(e).__name__}: {e}")
        result.update({'status':'error','message':f"{type(e).__name__}: {e}"}); return result


def main():
    p=argparse.ArgumentParser(description='ULTRA-SAFE MusicBrainz rating + log + report + cleanup + backup/restore + cache + RG fallback')
    p.add_argument('path')
    p.add_argument('--ua', required=True)
    p.add_argument('--write-popm', action='store_true')
    p.add_argument('--search-fallback', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--remove-exotic', action='store_true')
    p.add_argument('--exotic-mode', choices=['conservative','strict'], default='conservative')
    p.add_argument('--exotic-allow-txxx', default='')
    p.add_argument('--exotic-allow-vorbis', default='')
    p.add_argument('--exotic-allow-mp4', default='')
    p.add_argument('--report', default='')
    p.add_argument('--backup-tags', action='store_true')
    p.add_argument('--restore-tags', action='store_true')
    p.add_argument('--backup-dir', default='backups')
    p.add_argument('--cache', action='store_true')
    p.add_argument('--cache-db', default='.mbcache.sqlite')
    p.add_argument('--cache-ttl', type=int, default=86400)
    p.add_argument('--cache-mode', choices=['ro','rw','refresh'], default='rw')
    args=p.parse_args()

    if args.restore_tags:
        args.remove_exotic=False; args.write_popm=False; args.dry_run=False

    allow_txxx=set([s for s in args.exotic_allow_txxx.split(';') if s.strip()])
    allow_vorbis=set([s for s in args.exotic_allow_vorbis.split(';') if s.strip()])
    allow_mp4=set([s for s in args.exotic_allow_mp4.split(';') if s.strip()])

    cache=None
    if args.cache:
        cache=MbCache(args.cache_db, mode=args.cache_mode, ttl=args.cache_ttl)

    started=datetime.now(); results=[]
    target=args.path
    try:
        for f in iter_audio_files(target):
            res=process_file(f, target, args.ua, args.write_popm, args.search_fallback, args.dry_run,
                             args.remove_exotic, args.exotic_mode, allow_txxx, allow_vorbis, allow_mp4,
                             args.backup_tags, args.restore_tags, args.backup_dir, cache)
            results.append(res)
    finally:
        if cache: cache.close()

    ended=datetime.now()
    report_path = args.report or f"mb_rating_report_{ended.strftime('%Y%m%d_%H%M%S')}.html"
    generate_html_report(results, started, ended, report_path)
    print('Terminé. Log: mb_rating_tag.log')
    print(f'Report: {report_path}')

if __name__=='__main__':
    main()
