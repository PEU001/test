
# mbtools (fallback release-group)

## Installation
```
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Exemple (avec fallback RG)
```
python mb_rating_tag.py "/chemin/musique"   --ua "PierreTools/1.0 (pierre@example.com)"   --search-fallback   --cache
```

Le script tentera d'abord le **rating du recording**, puis à défaut le **rating du release-group** (écrit dans `RATING_RG`, `MUSICBRAINZ_RG_RATING`, `MUSICBRAINZ_RG_RATING_VOTES`).
