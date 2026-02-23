
# mbtools — ULTRA-SAFE (retry + session + throttle 1.5s + RG fallback)

## Installation
```
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scriptsctivate
pip install -r requirements.txt
```

## Exécution
```
python mb_rating_tag.py "/chemin/musique"   --ua "PierreTools/1.0 (pierre@example.com)"   --search-fallback   --cache
```

Le client applique :
- throttle global 1.5s, session HTTP persistante, retries exponentiels (429/503, timeout, reset)
- fallback vers le rating du release-group si le recording n'a pas de note
- cache SQLite (optionnel) + cache mémoire (dans le run)
