#!/usr/bin/env python3
"""
Auditoria de actividades de Strava por origen de subida.

Objetivo: separar lo que subio la app de Keiser M Series del resto.

Uso:
    export STRAVA_ACCESS_TOKEN=xxxx
    python3 strava_audit.py fetch                 # descarga todas las actividades a cache
    python3 strava_audit.py sources               # que origenes existen y cuantas de cada uno
    python3 strava_audit.py detail --sample 30    # rellena device_name (gasta cuota de API)
    python3 strava_audit.py list --keep keiser    # lo que NO es Keiser, con enlaces para borrar

La API v3 de Strava no permite borrar actividades, asi que 'list' genera la
lista de trabajo (y un CSV) para hacerlo desde la web.
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

API = "https://www.strava.com/api/v3"
CACHE = Path(__file__).parent / "activities.json"


def token():
    t = os.environ.get("STRAVA_ACCESS_TOKEN")
    if not t:
        sys.exit(
            "Falta STRAVA_ACCESS_TOKEN.\n"
            "Consiguelo en https://www.strava.com/settings/api con scope "
            "activity:read_all (y activity:write si algun dia hace falta escribir)."
        )
    return t


def get(path, **params):
    r = requests.get(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token()}"},
        params=params,
        timeout=30,
    )
    if r.status_code == 429:
        sys.exit("Limite de rate de Strava alcanzado (100/15min). Espera y reintenta.")
    r.raise_for_status()
    return r.json()


def load_cache():
    if not CACHE.exists():
        sys.exit("No hay cache. Ejecuta primero: python3 strava_audit.py fetch")
    return json.loads(CACHE.read_text())


def cmd_fetch(args):
    acts, page = [], 1
    while True:
        batch = get("/athlete/activities", per_page=200, page=page)
        if not batch:
            break
        acts.extend(batch)
        print(f"  pagina {page}: {len(batch)} actividades", file=sys.stderr)
        page += 1
        time.sleep(0.5)
    CACHE.write_text(json.dumps(acts, indent=2))
    print(f"{len(acts)} actividades guardadas en {CACHE}")


def source_of(a):
    """Etiqueta de origen, lo mas especifica que permita el dato disponible."""
    if a.get("device_name"):
        return f"device:{a['device_name']}"
    ext = a.get("external_id")
    if ext:
        # los uploaders usan prefijos estables: keiser-123.fit, garmin_push_...
        stem = ext.rsplit(".", 1)[0]
        for sep in ("-", "_"):
            if sep in stem:
                return f"external:{stem.split(sep)[0]}{sep}*"
        return f"external:{stem}"
    if a.get("manual"):
        return "manual (creada a mano en Strava)"
    if a.get("trainer"):
        return "sin external_id (trainer)"
    return "sin external_id"


def cmd_sources(args):
    acts = load_cache()
    counts = {}
    for a in acts:
        counts.setdefault(source_of(a), []).append(a)
    print(f"{len(acts)} actividades, {len(counts)} origenes:\n")
    for src, group in sorted(counts.items(), key=lambda kv: -len(kv[1])):
        sample = group[0]
        print(f"{len(group):>5}  {src}")
        print(
            f"         ej: {sample['name'][:45]!r} "
            f"external_id={sample.get('external_id')!r}"
        )
    print(
        "\nIdentifica arriba el origen de Keiser M Series y pasalo a "
        "`list --keep <texto>`."
    )


def cmd_detail(args):
    """device_name solo viene en el detalle; 1 llamada por actividad."""
    acts = load_cache()
    pending = [a for a in acts if "device_name" not in a][: args.sample]
    print(f"Pidiendo detalle de {len(pending)} actividades...", file=sys.stderr)
    by_id = {a["id"]: a for a in acts}
    for i, a in enumerate(pending, 1):
        d = get(f"/activities/{a['id']}")
        by_id[a["id"]]["device_name"] = d.get("device_name")
        if i % 10 == 0:
            print(f"  {i}/{len(pending)}", file=sys.stderr)
        time.sleep(0.3)
    CACHE.write_text(json.dumps(acts, indent=2))
    print(f"Detalle añadido a {len(pending)} actividades.")


def matches(a, keep):
    hay = " ".join(
        str(a.get(k) or "") for k in ("external_id", "device_name", "name")
    ).lower()
    return keep.lower() in hay


def cmd_list(args):
    acts = load_cache()
    keep = [a for a in acts if matches(a, args.keep)]
    drop = [a for a in acts if not matches(a, args.keep)]
    print(f"Conservar (coinciden con {args.keep!r}): {len(keep)}")
    print(f"Borrar (no coinciden):                  {len(drop)}\n")
    out = Path(__file__).parent / "a_borrar.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "fecha", "nombre", "tipo", "origen", "url"])
        for a in sorted(drop, key=lambda x: x["start_date"]):
            w.writerow([
                a["id"], a["start_date"][:10], a["name"], a.get("type"),
                source_of(a), f"https://www.strava.com/activities/{a['id']}",
            ])
    for a in sorted(drop, key=lambda x: x["start_date"])[: args.head]:
        print(
            f"  {a['start_date'][:10]}  {a['name'][:40]:<40}  "
            f"https://www.strava.com/activities/{a['id']}"
        )
    if len(drop) > args.head:
        print(f"  ... y {len(drop) - args.head} mas")
    print(f"\nLista completa: {out}")
    print(
        "Para borrar: abre cada URL -> menu '...' -> Eliminar. "
        "La API v3 de Strava no expone borrado de actividades."
    )


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    sub.add_parser("sources").set_defaults(fn=cmd_sources)
    d = sub.add_parser("detail")
    d.add_argument("--sample", type=int, default=50)
    d.set_defaults(fn=cmd_detail)
    l = sub.add_parser("list")
    l.add_argument("--keep", required=True, help="texto que identifica a Keiser")
    l.add_argument("--head", type=int, default=25)
    l.set_defaults(fn=cmd_list)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
