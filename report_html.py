# report_html.py
import base64
from datetime import datetime


def fmt_ms(ms):
    if not ms:
        return ""
    s = int(round(ms / 1000))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def generate_html_report(results, started: datetime, ended: datetime, output_path: str):
    total = len(results)
    ok = sum(1 for r in results if str(r.get("status", "")).startswith("ok"))
    restored = sum(1 for r in results if r.get("status") == "restore")
    errors = sum(1 for r in results if r.get("status") == "error")
    skipped = sum(1 for r in results if r.get("status") == "skip")
    not_found = sum(1 for r in results if r.get("status") == "not-found")
    cleaned = sum(1 for r in results if (r.get("removed_exotic") or []) and str(r.get("status", "")).startswith("ok"))
    ratings = [r["rating"] for r in results if r.get("rating") is not None]
    avg = sum(ratings) / len(ratings) if ratings else 0.0

    # CSV inline
    def esc(s):
        if s is None:
            return ""
        s = str(s)
        if any(c in s for c in [",", '"', "\n"]):
            return '"' + s.replace('"', '""') + '"'
        return s

    csv_lines = [
        "file,status,mbid,rating,votes,artist,title,duration,has_cover,exotic_tags,removed_exotic,message"
    ]
    for r in results:
        csv_lines.append(
            ",".join(
                [
                    esc(r.get("file")),
                    esc(r.get("status")),
                    esc(r.get("mbid")),
                    esc(r.get("rating")),
                    esc(r.get("votes")),
                    esc(r.get("artist")),
                    esc(r.get("title")),
                    esc(fmt_ms(r.get("duration_ms"))),
                    esc("yes" if r.get("has_cover") else "no"),
                    esc(";".join(r.get("exotic_tags") or [])),
                    esc(";".join(r.get("removed_exotic") or [])),
                    esc(r.get("message")),
                ]
            )
        )
    csv_b64 = base64.b64encode("\n".join(csv_lines).encode("utf-8")).decode("ascii")

    started_s = started.strftime("%Y-%m-%d %H:%M:%S")
    ended_s = ended.strftime("%Y-%m-%d %H:%M:%S")

    def h(s):
        import html

        return html.escape("" if s is None else str(s))

    rows = []
    for r in results:
        rows.append(
            f"""
        <tr data-status='{h(r.get('status'))}'>
          <td>{h(r.get('status'))}</td>
          <td>{h(r.get('file'))}</td>
          <td>{h(r.get('artist'))}</td>
          <td>{h(r.get('title'))}</td>
          <td>{h(f"{r.get('rating'):.1f}" if r.get('rating') is not None else "")}</td>
          <td>{h(r.get('votes'))}</td>
          <td>{h(fmt_ms(r.get('duration_ms')))}</td>
          <td>{h(r.get('mbid'))}</td>
          <td>{h(', '.join(r.get('exotic_tags') or []))}</td>
          <td>{h(', '.join(r.get('removed_exotic') or []))}</td>
          <td>{"✔️" if r.get('has_cover') else "❌"}</td>
          <td>{h(r.get('message'))}</td>
        </tr>"""
        )

    html = f"""<!doctype html>
<html lang='fr'><head><meta charset='utf-8'><title>Rapport MusicBrainz</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:24px; }}
header {{ margin-bottom: 16px; }} h1 {{ font-size: 22px; margin:0 0 8px 0; }} .meta {{ color:#666; font-size:13px; }}
.toolbar {{ display:flex; gap:12px; margin:16px 0; }} input[type=search]{{ padding:8px 10px; border:1px solid #ccc; border-radius:6px; min-width:260px; }}
table {{ border-collapse:collapse; width:100%; }} th,td {{ border-bottom:1px solid #eee; padding:6px; text-align:left; }} th {{ position:sticky; top:0; background:canvas; }}
tr:hover {{ background: rgba(0,0,0,.03); }} .note {{ color:#666; font-size:12px; }}
</style></head>
<body>
<header>
  <h1>Rapport — intégration des notes MusicBrainz</h1>
  <div class='meta'>Début: {started_s} · Fin: {ended_s} · Fichiers: {total} · Succès: {ok} · Restaurés: {restored} · Nettoyés: {cleaned} · Sans note: {not_found} · Erreurs: {errors} · Ignorés: {skipped} · Note moyenne: {avg:.2f}</div>
</header>
<div class='toolbar'>
  <input id='q' type='search' placeholder='Filtrer (fichier, artiste, titre, statut, MBID)…'>
  <a class='btn' href='data:text/csv;base64,{csv_b64}' download='mbtools_export.csv'>Exporter CSV</a>
</div>
<table id='tbl'>
  <thead><tr>
    <th>Statut</th><th>Fichier</th><th>Artiste</th><th>Titre</th><th>Note</th><th>Votes</th><th>Durée</th><th>MBID</th><th>Tags exotiques</th><th>Supprimés</th><th>Pochette</th><th>Message</th>
  </tr></thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
<script>
(function(){{
  const q=document.getElementById('q');
  const rows=[...document.querySelectorAll('#tbl tbody tr')];
  function n(s){{return (s||'').toLowerCase()}}
  function f(){{
    const qq=n(q.value);
    rows.forEach(tr=>{{const ok=!qq||n(tr.innerText).includes(qq); tr.style.display=ok?'':'none';}});
  }}
  q.addEventListener('input', f);
}})();
</script>
</body></html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
