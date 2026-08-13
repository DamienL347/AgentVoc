"""
Convertit le CSV exporté par scripts/export_schema.sql en scripts/schema.sql.

Le SQL Editor de Supabase renvoie le DDL dans une unique cellule ; « Download CSV »
produit donc un fichier d'une colonne (`ddl`) et d'une ligne, avec le texte échappé.
Ce script en extrait le SQL brut.

Usage :
    venv\\Scripts\\python.exe scripts/csv_to_schema.py "C:\\Users\\...\\Downloads\\result.csv"
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "scripts" / "schema.sql"


def main():
    if len(sys.argv) < 2:
        sys.exit(f"Usage : python {Path(__file__).name} <fichier.csv téléchargé>")

    src = Path(sys.argv[1])
    if not src.exists():
        sys.exit(f"[ERREUR] Fichier introuvable : {src}")

    # Le DDL contient des retours à la ligne : il faut le lecteur CSV, pas un split().
    csv.field_size_limit(10_000_000)
    with src.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    if len(rows) < 2 or not rows[1]:
        sys.exit("[ERREUR] CSV inattendu : une ligne d'en-tête + une ligne de données étaient attendues.")

    ddl = rows[1][0].strip()
    if not ddl:
        sys.exit("[ERREUR] La cellule DDL est vide — la requête a-t-elle bien été exécutée ?")

    OUT.write_text(ddl + "\n", encoding="utf-8")

    tables = ddl.count("CREATE TABLE")
    print(f"[OK] Schema ecrit : {OUT}")
    print(f"   {tables} tables · {len(ddl.splitlines())} lignes · {OUT.stat().st_size} octets")
    print("   Pense à le committer : git add scripts/schema.sql")


if __name__ == "__main__":
    main()
