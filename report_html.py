
# report_html.py
import base64
from datetime import datetime

def fmt_ms(ms):
    if not ms:
        return ''
    s=int(round(ms/1000)); m,s=divmod(s,60); h,m=divmod(m,60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def _esc(s):
    import html
    return html.escape('' if s is None else str(s))

_CSS = """
:root { color-scheme: light dark; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:24px; }
header { margin-bottom: 16px; }
h1 { font-size: 22px; margin:0 0 8px 0; }
.meta { color:#666; font-size:13px; }
.toolbar { display:flex; gap:12px; margin:16px 0; }
input[type=search]{ padding:8px 10px; border:1px solid #ccc; border-radius:6px; min-width:260px; }
table { border-collapse:collapse; width:100%; }
th,td { border-bottom:1px solid #eee; padding:6px; text-align:left; }
th { position:sticky; top:0; background:canvas; }
tr:hover { background: rgba(0,0,0,.03); }
.note { color:#666; font-size:12px; }
"""

def generate_html_report(results, started: datetime, ended: datetime, output_path: str):
    total=len(results)
    ok=sum(1 for r in results if str(r.get('status','')).startswith('ok'))
    restored=sum(1 for r in results if r.get('status')=='restore')
    errors=sum(1 for r in results if r.get('status')=='error')
    skipped=sum(1 for r in results if r.get('status')=='skip')
    not_found=sum(1 for r in results if r.get('status')=='not-found')
    cleaned=sum(1 for r in results if (r.get('removed_exotic') or []) and str(r.get('status','')).startswith('ok'))
    ratings=[r['rating'] for r in results if r.get('rating') is not None]
    avg=sum(ratings)/len(ratings) if ratings else 0.0

    def esc_csv(s):
        if s is None: return ''
        s=str(s)
        if any(c in s for c in [',','"','
']):
            return '"'+s.replace('"','""')+'"'
        return s

    csv_lines=["file,status,mbid,mbid_rg,fallback,rating,votes,artist,title,duration,has_cover,exotic_tags,removed_exotic,message"]
    for r in results:
        csv_lines.append(','.join([
            esc_csv(r.get('file')), esc_csv(r.get('status')), esc_csv(r.get('mbid')),
            esc_csv(r.get('mbid_rg')), esc_csv(r.get('fallback')),
            esc_csv(r.get('rating')), esc_csv(r.get('votes')),
            esc_csv(r.get('artist')), esc_csv(r.get('title')),
            esc_csv(fmt_ms(r.get('duration_ms'))), esc_csv('yes' if r.get('has_cover') else 'no'),
            esc_csv(';'.join(r.get('exotic_tags') or [])), esc_csv(';'.join(r.get('removed_exotic') or [])), esc_csv(r.get('message'))
        ]))
    csv_b64=base64.b64encode('
'.join(csv_lines).encode('utf-8')).decode('ascii')

    started_s=started.strftime('%Y-%m-%d %H:%M:%S'); ended_s=ended.strftime('%Y-%m-%d %H:%M:%S')

    rows=[]
    for r in results:
        rating_str = f"{r.get('rating'):.1f}" if r.get('rating') is not None else ''
        cover_str = '✔️' if r.get('has_cover') else '❌'
        exotic_str = ', '.join(r.get('exotic_tags') or [])
        removed_str = ', '.join(r.get('removed_exotic') or [])
        rows.append(
            "<tr data-status='{status}'>"
            "<td>{status}</td><td>{file}</td><td>{artist}</td><td>{title}</td>"
            "<td>{rating}</td><td>{votes}</td><td>{duration}</td>"
            "<td>{mbid}</td><td>{mbid_rg}</td><td>{fallback}</td>"
            "<td>{exotic}</td><td>{removed}</td><td>{cover}</td><td class='note'>{message}</td>"             "</tr>".format(
                status=_esc(r.get('status')),
                file=_esc(r.get('file')),
                artist=_esc(r.get('artist')),
                title=_esc(r.get('title')),
                rating=_esc(rating_str),
                votes=_esc(r.get('votes')),
                duration=_esc(fmt_ms(r.get('duration_ms'))),
                mbid=_esc(r.get('mbid')),
                mbid_rg=_esc(r.get('mbid_rg')),
                fallback=_esc(r.get('fallback')),
                exotic=_esc(exotic_str),
                removed=_esc(removed_str),
                cover=_esc(cover_str),
                message=_esc(r.get('message')),
            )
        )
    rows_html='
'.join(rows)

    html_head = (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<title>Rapport MusicBrainz</title><style>" + _CSS + "</style></head><body>"
    )
    html_header = (
        "<header><h1>Rapport — intégration des notes MusicBrainz</h1>"
        "<div class='meta'>Début: {start} · Fin: {end} · Fichiers: {total} · Succès: {ok} · Restaurés: {rest} · "
        "Nettoyés: {clean} · Sans note: {nf} · Erreurs: {err} · Ignorés: {skip} · Note moyenne: {avg:.2f}</div>"
        "</header>".format(start=_esc(started_s), end=_esc(ended_s), total=total, ok=ok, rest=restored, clean=cleaned, nf=not_found, err=errors, skip=skipped, avg=avg)
    )
    html_toolbar = (
        "<div class='toolbar'>"
        "<input id='q' type='search' placeholder='Filtrer (fichier, artiste, titre, statut, MBID)…'>"
        f"data:text/csv;base64,{csv_b64}Exporter CSV</a>"
        "</div>"
    )
    html_table = (
        "<table id='tbl'><thead><tr>"
        "<th>Statut</th><th>Fichier</th><th>Artiste</th><th>Titre</th><th>Note</th><th>Votes</th><th>Durée</th>"
        "<th>MBID</th><th>MBID RG</th><th>Fallback RG</th>"
        "<th>Tags exotiques</th><th>Supprimés</th><th>Pochette</th><th>Message</th>"
        "</tr></thead><tbody>" + rows_html + "</tbody></table>"
    )
    _JS = """
(function(){
  const q=document.getElementById('q');
  const rows=Array.from(document.querySelectorAll('#tbl tbody tr'));
  function norm(s){return (s||'').toLowerCase();}
  function apply(){
    const qq=norm(q.value);
    rows.forEach(tr=>{const ok=!qq||norm(tr.innerText).includes(qq); tr.style.display=ok?'':'none';});
  }
  q.addEventListener('input', apply);
})();
"""
    html_js = "<script>" + _JS + "</script>"

    html = html_head + html_header + html_toolbar + html_table + html_js + "</body></html>"
    with open(output_path,'w',encoding='utf-8') as f:
        f.write(html)
