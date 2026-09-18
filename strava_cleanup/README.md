# Limpieza de Strava: conservar solo Keiser M Series

La API v3 de Strava **no permite borrar actividades** (el endpoint `DELETE
/activities/{id}` fue retirado). Esta herramienta hace la parte dificil:
identificar con exactitud que actividades vienen de la app de Keiser M Series
y cuales no, y genera la lista de trabajo para borrarlas desde la web.

## 1. Token

En https://www.strava.com/settings/api crea una app y consigue un token con
scope `activity:read_all`.

    export STRAVA_ACCESS_TOKEN=xxxxx

## 2. Descargar el historial

    python3 strava_audit.py fetch

Guarda todo en `activities.json` para no volver a gastar cuota de API.

## 3. Ver de donde viene cada actividad

    python3 strava_audit.py sources

Agrupa por `external_id` / `device_name` y te dice cuantas hay de cada origen.
Ahi se ve cual es el prefijo de Keiser.

Si los origenes salen vagos (`sin external_id`), el `device_name` solo viene en
el detalle de cada actividad:

    python3 strava_audit.py detail --sample 50

Ojo con el rate limit de Strava: 100 peticiones cada 15 min, 1000 al dia.

## 4. Generar la lista a borrar

    python3 strava_audit.py list --keep keiser

Escribe `a_borrar.csv` con id, fecha, nombre, origen y URL de cada actividad
que **no** es de Keiser. Revisa el CSV antes de borrar nada.

## 5. Borrar

Cada URL del CSV -> menu `...` -> Eliminar. No hay borrado masivo oficial.
