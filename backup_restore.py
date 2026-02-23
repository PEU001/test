
# backup_restore.py
import os, json, base64
from mutagen import File
from mutagen.id3 import ID3, ID3NoHeaderError, TXXX, APIC, Frames
from mutagen.flac import Picture
from mutagen.mp4 import MP4, MP4Cover

def backup_tags(audio, path: str, rel: str, backup_dir: str):
    os.makedirs(backup_dir, exist_ok=True)
    out = os.path.join(backup_dir, rel.replace(os.sep,'__')+'.json')
    ext = os.path.splitext(path)[1].lower()
    data = {"path": rel, "format": None, "tags": {}}
    if ext=='.mp3':
        data['format']='MP3'
        try: id3=ID3(path)
        except ID3NoHeaderError: id3=None
        if id3:
            for f in id3.values():
                fid=f.FrameID
                if fid=='APIC':
                    data['tags']['APIC']={"mime":f.mime,"desc":f.desc,"type":f.type,"data":base64.b64encode(f.data).decode('ascii')}
                elif fid=='TXXX':
                    data['tags'][f'TXXX:{f.desc}']=f.text
                else:
                    try: data['tags'][fid]=f.text
                    except: data['tags'][fid]=str(f)
    elif isinstance(audio, MP4):
        data['format']='MP4'
        for k,v in (audio.tags or {}).items():
            if k=='covr':
                covers=[]
                for c in v:
                    covers.append({"data":base64.b64encode(bytes(c)).decode('ascii'),"type":c.imageformat})
                data['tags']['covr']=covers
            else:
                try: data['tags'][k]=[vv.decode('utf-8','ignore') if isinstance(vv,bytes) else str(vv) for vv in v]
                except: data['tags'][k]=str(v)
    else:
        data['format']='VORBIS'
        if audio.tags:
            for k,v in audio.tags.items(): data['tags'][k]=v
        if hasattr(audio,'pictures'):
            pics=[]
            for p in audio.pictures:
                pics.append({"mime":p.mime,"type":p.type,"desc":p.desc,"data":base64.b64encode(p.data).decode('ascii')})
            data['tags']['__PICTURES__']=pics
    with open(out,'w',encoding='utf-8') as f: json.dump(data,f,indent=2)
    return out


def restore_tags(path: str, rel: str, backup_dir: str):
    in_path = os.path.join(backup_dir, rel.replace(os.sep,'__')+'.json')
    if not os.path.exists(in_path):
        return False, 'Backup manquant'
    from mutagen import File
    with open(in_path,'r',encoding='utf-8') as f: data=json.load(f)
    audio = File(path, easy=False)
    fmt=data.get('format'); tags=data.get('tags',{})
    if fmt=='MP3':
        try: id3=ID3(path)
        except ID3NoHeaderError: id3=ID3()
        id3.delete()
        for k,v in tags.items():
            if k=='APIC':
                blob=base64.b64decode(v['data'])
                id3.add(APIC(mime=v.get('mime'), desc=v.get('desc'), type=v.get('type',3), data=blob))
            elif k.startswith('TXXX:'):
                desc=k.split(':',1)[1]; id3.add(TXXX(encoding=3, desc=desc, text=v))
            else:
                cls=Frames.get(k)
                if cls:
                    try: id3.add(cls(encoding=3, text=v))
                    except: pass
        id3.save(v2_version=3); return True, 'Tags restaurés (MP3)'
    if fmt=='VORBIS':
        try: audio.delete()
        except: pass
        for k,v in tags.items():
            if k=='__PICTURES__':
                if hasattr(audio,'clear_pictures'):
                    try: audio.clear_pictures()
                    except: pass
                for p in v:
                    pic=Picture(); pic.mime=p['mime']; pic.type=p['type']; pic.desc=p['desc']; pic.data=base64.b64decode(p['data'])
                    try: audio.add_picture(pic)
                    except: pass
            else:
                audio[k]=v
        audio.save(); return True, 'Tags restaurés (Vorbis)'
    if fmt=='MP4':
        if not isinstance(audio, MP4): return False,'Format incompatible'
        try: audio.delete()
        except: pass
        for k,v in tags.items():
            if k=='covr':
                covs=[]
                for c in v: covs.append(MP4Cover(base64.b64decode(c['data']), c['type']))
                audio.tags['covr']=covs
            else:
                audio.tags[k]=v
        audio.save(); return True, 'Tags restaurés (MP4)'
    return False, 'Format backup inconnu'
