"""Deadlock Scouting — arranque con un solo comando:

    python app.py                      abre http://127.0.0.1:8000 y actualiza en segundo plano
    python app.py --sin-actualizar     no lanza la actualización automática
    python app.py --importar RUTA      importa campos manuales y snapshots de un scouting.db antiguo
    python app.py --calibrar           recalibra el minimapa con las partidas guardadas
"""
import argparse
import os
import sys
import threading
import webbrowser

if sys.version_info < (3, 9):
    sys.exit("Hace falta Python 3.9 o superior.")

from scouting import api, config, db, matches, minimap, summary, updater


def main():
    try:  # mensajes de terminal al momento aunque la salida no sea una consola
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Deadlock Scouting (local)")
    ap.add_argument("--puerto", type=int, help="puerto (por defecto 8000)")
    ap.add_argument("--sin-actualizar", action="store_true", help="no actualizar automáticamente")
    ap.add_argument("--no-abrir", action="store_true", help="no abrir el navegador")
    ap.add_argument("--importar", metavar="SCOUTING_DB", help="importar un scouting.db antiguo y salir")
    ap.add_argument("--calibrar", action="store_true", help="recalibrar el minimapa con las partidas guardadas y salir")
    args = ap.parse_args()

    cfg = config.load()
    os.makedirs(config.DATA_DIR, exist_ok=True)
    con = db.get()
    client = api.Client(cfg.get("api_key"))

    if args.importar:
        from scouting import importer
        print("Tablas encontradas:", importer.inspect(args.importar))
        rep = importer.import_db(con, args.importar)
        print("Importación terminada:", rep)
        return

    if args.calibrar:
        ids = [r[0] for r in con.execute("SELECT match_id FROM matches ORDER BY stored_at DESC LIMIT 30")]
        if not ids and os.path.exists("match_109084310.json"):
            with open("match_109084310.json", "rb") as f:
                ids = [matches.store_raw(con, f.read(), "fixture")]
        pts = minimap.alive_points([matches.load(i) for i in ids], step=5)
        fitted = minimap.fit(pts)
        print("Ajustada:", fitted)
        print("Comparación:", minimap.compare({"actual": minimap.load_calibration(), "oficial": minimap.OFFICIAL, "ajustada": fitted}, pts))
        print("La calibración NO se ha guardado. Guárdala desde la web (Partidas › Calibración) si mejora a la actual.")
        return

    if not os.path.exists(config.TEAMS_PATH):
        with open(config.TEAMS_PATH, "w", encoding="utf-8") as f:
            f.write("# Una línea por jugador: uno o varios IDs (cuentas del mismo jugador) y el nombre del equipo.\n"
                    "# IDs válidos: número (account_id), [U:1:N], steam64 o URL de perfil de Steam.\n"
                    "# 35187362 Buff Enjoyers\n# 483770846, 802747733 Buff Enjoyers\n")
        print(f"Creado {config.TEAMS_PATH} (vacío, con ejemplos comentados).")

    # equipos.txt se relee al arrancar (sin red)
    updater.sync_teams(con)
    summary.materialize(con)

    upd = updater.Updater(client)
    port = args.puerto or int(cfg["port"])
    from scouting import server
    app = server.App(client, upd, port)
    try:
        httpd = server.serve(app, "127.0.0.1", port)
    except OSError as e:
        sys.exit(f"No se pudo abrir el puerto {port}: {e}. ¿Ya está arrancado? Prueba con --puerto 8001")

    stop = threading.Event()
    if not args.sin_actualizar:
        threading.Thread(target=upd.scheduler, args=(stop,), daemon=True, name="planificador").start()
    url = f"http://127.0.0.1:{port}"
    print(f"Deadlock Scouting en {url}  (Ctrl+C para salir)")
    if cfg.get("open_browser", True) and not args.no_abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando…")
    finally:
        stop.set()
        httpd.server_close()


if __name__ == "__main__":
    main()
