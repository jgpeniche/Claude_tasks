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

---

# Ruta alternativa: borrar la cuenta y rescatar solo lo de Keiser

Strava no permite borrado masivo de actividades conservando la cuenta. Si lo
que sobra es practicamente todo el historial, sale mas a cuenta resetear.

## A. Pedir el export (hazlo ANTES de borrar nada)

https://www.strava.com/settings/account -> "Descargar o eliminar tu cuenta"
-> Empezar -> **Paso 2, Solicitar tu archivo**. Llega por email un ZIP con
`activities.csv` y la carpeta `activities/` con los ficheros originales.

No toques el Paso 3 (eliminar cuenta) hasta tener el ZIP descargado.

## B. Localizar las de Keiser

Ojo: **los nombres en Strava no dicen "Keiser"** — salen como "Morning Ride",
"Evening Ride", etc. Asi que `--grep keiser` sobre el indice no encuentra nada.

La firma real esta DENTRO del fichero: la app Keiser Metrics sube `.tcx` con
`<Notes>Keiser M3i</Notes>`. Por eso `prune` busca en el contenido:

    python3 strava_export.py prune export.zip --match keiser --out solo_keiser.zip

Genera una copia del export con solo las actividades que coinciden. Mantiene
`activities.csv` filtrado y el resto de CSV de cuenta intactos. No modifica el
original.

## C. Extraer sus ficheros

    python3 strava_export.py extract export.zip --ids 9001,9003 --out rescatadas/

Los IDs son los de la columna "Id. de actividad", que NO coinciden con el
numero del nombre de fichero (ese es el id de subida).

Guarda los `.fit.gz` originales mas un `meta.json` con los nombres. Las
actividades creadas a mano en Strava no tienen fichero y no se pueden resubir.

## D. Borrar la cuenta y crear la nueva

Paso 3 de la misma pagina. Es irreversible: pierdes seguidores, kudos,
comentarios, clubes y PRs de segmentos.

## E. Resubir

Token de la cuenta **nueva** con scope `activity:write`:

    export STRAVA_ACCESS_TOKEN=xxxxx
    python3 strava_export.py upload rescatadas/ --dry-run   # comprueba primero
    python3 strava_export.py upload rescatadas/

Sube via `POST /uploads` y espera a que Strava procese cada fichero. Conserva
potencia, cadencia y pulso tal cual venian del original.
