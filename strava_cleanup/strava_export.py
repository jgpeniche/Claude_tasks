#!/usr/bin/env python3
"""
Trabaja con el ZIP del export masivo de Strava.

    python3 strava_export.py index export.zip
    python3 strava_export.py index export.zip --grep keiser
    python3 strava_export.py extract export.zip --ids 123,456,789 --out rescatadas/
    STRAVA_ACCESS_TOKEN=xxx python3 strava_export.py upload rescatadas/ --dry-run
    STRAVA_ACCESS_TOKEN=xxx python3 strava_export.py upload rescatadas/

El token de `upload` tiene que ser de la CUENTA NUEVA y con scope activity:write.
"""

import argparse
import csv
import io
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

import requests

API = "https://www.strava.com/api/v3"
# data_type que acepta POST /uploads, por extension del fichero
DATA_TYPES = {
    ".fit": "fit", ".fit.gz": "fit.gz",
    ".tcx": "tcx", ".tcx.gz": "tcx.gz",
    ".gpx": "gpx", ".gpx.gz": "gpx.gz",
}


def token():
    t = os.environ.get("STRAVA_ACCESS_TOKEN")
    if not t:
        sys.exit("Falta STRAVA_ACCESS_TOKEN (cuenta nueva, scope activity:write).")
    return t


def read_index(zip_path):
    """Filas de activities.csv, normalizadas a las claves que nos importan."""
    with zipfile.ZipFile(zip_path) as z:
        name = next(
            (n for n in z.namelist() if n.endswith("activities.csv")), None
        )
        if not name:
            sys.exit(f"{zip_path} no contiene activities.csv. ZIP incompleto?")
        text = z.read(name).decode("utf-8-sig")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        # Strava localiza las cabeceras, asi que buscamos por posicion tambien
        vals = list(r.values())
        rows.append({
            "id": (r.get("Activity ID") or vals[0] or "").strip(),
            "date": (r.get("Activity Date") or vals[1] or "").strip(),
            "name": (r.get("Activity Name") or vals[2] or "").strip(),
            "type": (r.get("Activity Type") or vals[3] or "").strip(),
            "filename": next(
                (v for v in vals if v and v.startswith("activities/")), ""
            ),
        })
    return rows


def data_type_for(filename):
    low = filename.lower()
    for ext in sorted(DATA_TYPES, key=len, reverse=True):
        if low.endswith(ext):
            return DATA_TYPES[ext]
    return None


def cmd_index(args):
    rows = read_index(args.zip)
    if args.grep:
        needle = args.grep.lower()
        rows = [r for r in rows
                if needle in f"{r['name']} {r['type']} {r['filename']}".lower()]
    print(f"{len(rows)} actividades\n")
    print(f"{'ID':<14}{'FECHA':<22}{'TIPO':<16}NOMBRE")
    for r in rows:
        missing = "" if r["filename"] else "   [SIN FICHERO]"
        print(f"{r['id']:<14}{r['date'][:20]:<22}{r['type'][:14]:<16}"
              f"{r['name'][:40]}{missing}")
    if not args.grep:
        print("\nFiltra con --grep para encontrar las de Keiser.")


def cmd_extract(args):
    wanted = {i.strip() for i in args.ids.split(",") if i.strip()}
    rows = {r["id"]: r for r in read_index(args.zip)}
    missing = wanted - rows.keys()
    if missing:
        sys.exit(f"Estos IDs no estan en el export: {', '.join(sorted(missing))}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {}
    with zipfile.ZipFile(args.zip) as z:
        names = set(z.namelist())
        for aid in sorted(wanted):
            r = rows[aid]
            if not r["filename"]:
                print(f"  {aid}: sin fichero (actividad manual, no se puede subir)")
                continue
            if r["filename"] not in names:
                print(f"  {aid}: {r['filename']} no esta dentro del ZIP")
                continue
            dest = out / Path(r["filename"]).name
            with z.open(r["filename"]) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            meta[dest.name] = {"name": r["name"], "date": r["date"], "id": aid}
            print(f"  {aid}: {dest.name} ({dest.stat().st_size} bytes)")
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"\n{len(meta)} ficheros en {out}/ (nombres originales en meta.json)")


def upload_one(path, name):
    dt = data_type_for(path.name)
    if not dt:
        print(f"  {path.name}: extension no soportada, salto")
        return None
    with path.open("rb") as f:
        r = requests.post(
            f"{API}/uploads",
            headers={"Authorization": f"Bearer {token()}"},
            files={"file": (path.name, f)},
            data={"data_type": dt, "name": name},
            timeout=60,
        )
    if r.status_code >= 400:
        print(f"  {path.name}: error {r.status_code} {r.text[:200]}")
        return None
    upload_id = r.json()["id"]
    # el procesado es asincrono: hay que preguntar hasta que resuelva
    for _ in range(30):
        time.sleep(2)
        s = requests.get(
            f"{API}/uploads/{upload_id}",
            headers={"Authorization": f"Bearer {token()}"},
            timeout=30,
        ).json()
        if s.get("error"):
            print(f"  {path.name}: rechazado -> {s['error']}")
            return None
        if s.get("activity_id"):
            url = f"https://www.strava.com/activities/{s['activity_id']}"
            print(f"  {path.name}: OK -> {url}")
            return s["activity_id"]
    print(f"  {path.name}: sigue procesando, revisa en Strava dentro de un rato")
    return None


def cmd_upload(args):
    src = Path(args.dir)
    meta_file = src / "meta.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    files = sorted(p for p in src.iterdir()
                   if p.is_file() and data_type_for(p.name))
    if not files:
        sys.exit(f"No hay ficheros subibles en {src}/")
    print(f"{len(files)} ficheros para subir:")
    for p in files:
        print(f"  {p.name}  ->  {meta.get(p.name, {}).get('name', p.stem)!r}")
    if args.dry_run:
        print("\n--dry-run: no se ha subido nada.")
        return
    print()
    ok = 0
    for p in files:
        if upload_one(p, meta.get(p.name, {}).get("name") or p.stem):
            ok += 1
    print(f"\n{ok}/{len(files)} subidas correctamente.")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("index", help="lista lo que hay en el ZIP")
    i.add_argument("zip")
    i.add_argument("--grep", help="filtra por nombre/tipo/fichero")
    i.set_defaults(fn=cmd_index)

    e = sub.add_parser("extract", help="saca los ficheros de los IDs indicados")
    e.add_argument("zip")
    e.add_argument("--ids", required=True, help="IDs separados por coma")
    e.add_argument("--out", default="rescatadas")
    e.set_defaults(fn=cmd_extract)

    u = sub.add_parser("upload", help="sube una carpeta a la cuenta nueva")
    u.add_argument("dir")
    u.add_argument("--dry-run", action="store_true")
    u.set_defaults(fn=cmd_upload)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
