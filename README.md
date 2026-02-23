# mbtools — MusicBrainz Rating + Tags Toolkit

Ce paquet permet d'intégrer la **note MusicBrainz** dans vos fichiers audio et de gérer vos tags :
- Log texte, rapport HTML, détection/suppression de tags exotiques,
- Sauvegarde & restauration des tags,
- Cache local (SQLite) pour accélérer les gros volumes.

## 🚀 Reconstruction des sources (Structure A)
Ce ZIP contient des **placeholders**. Pour récupérer le code complet :

1. Placez le fichier `rebuild_payload.json` dans le même dossier que `mb_rating_tag.py`.
2. Exécutez :
   ```bash
   python mb_rating_tag.py --rebuild
   ```
3. Une fois terminé, utilisez normalement le script :
   ```bash
   python mb_rating_tag.py --help
   ```

> Le fichier `rebuild_payload.json` vous sera fourni (base64). Il contient le code de tous les modules.

## 📦 Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 🧩 Dépendances
- Python 3.8+
- `mutagen`
- `requests`

## 📁 Contenu
```
mbtools/
 ├── mb_rating_tag.py        # reconstructeur + lanceur
 ├── cache.py                # placeholder (sera remplacé)
 ├── backup_restore.py       # placeholder (sera remplacé)
 ├── exotic_cleanup.py       # placeholder (sera remplacé)
 ├── report_html.py          # placeholder (sera remplacé)
 ├── utils_mb.py             # placeholder (sera remplacé)
 ├── README.md
 └── requirements.txt
```

## ❓ Utilisation (une fois reconstruit)
Consultez `README.md` dans la version finale pour tous les exemples.
