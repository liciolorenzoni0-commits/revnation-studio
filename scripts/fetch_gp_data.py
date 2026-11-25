#!/usr/bin/env python3
"""
F1 Pit Wall Data Extractor (FastF1 + OpenF1)
Combina:
  - FastF1 (calendario oficial, clasificacion y resultados via jolpica-f1)
  - OpenF1 (telemetria gratuita sin login: velocidad, acelerador, freno, marchas, RPM, mapa X/Y, stints y clima)
"""

import hashlib
import json
import math
import os
import time
from datetime import datetime, timedelta

import fastf1
import numpy as np
import requests

CACHE_DIR = "/tmp/f1_cache"
OPENF1_CACHE_DIR = "/tmp/openf1_cache"
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OPENF1_CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)

OPENF1_BASE = "https://api.openf1.org/v1"
HTTP = requests.Session()


def openf1_get(endpoint: str, params: dict, retries: int = 6):
    """Peticion a OpenF1 con cache en disco y backoff respetuoso ante HTTP 429."""
    key_raw = endpoint + "?" + json.dumps(params, sort_keys=True)
    cache_path = os.path.join(OPENF1_CACHE_DIR, hashlib.md5(key_raw.encode()).hexdigest() + ".json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    url = f"{OPENF1_BASE}/{endpoint}"
    for attempt in range(retries):
        resp = HTTP.get(url, params=params, timeout=25)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else 4.0 * (attempt + 1)
            print(f"    [429 rate-limit en {endpoint}] esperando {wait:.1f}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        time.sleep(0.55)
        return data
    resp.raise_for_status()


def parse_iso(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def extract_telemetry_for_lap(session_key: int, driver_num: int, lap: dict, n_points: int = 220, fetch_loc: bool = False):
    """Descarga car_data (y opcionalmente location) de la vuelta rapida y re-muestrea en distancia uniforme."""
    t0_dt = datetime.fromisoformat(lap["date_start"].replace("Z", "+00:00"))
    dur = float(lap["lap_duration"])
    t0 = t0_dt.timestamp()
    t1_dt = t0_dt + timedelta(seconds=dur)

    # Ventana con 1.5s de margen para interpolar bordes limpiamente
    win_start = (t0_dt - timedelta(seconds=1.5)).isoformat()
    win_end = (t1_dt + timedelta(seconds=1.5)).isoformat()

    car = openf1_get(
        "car_data",
        {
            "session_key": session_key,
            "driver_number": driver_num,
            "date>": win_start,
            "date<": win_end,
        },
    )
    loc = []
    if fetch_loc:
        loc = openf1_get(
            "location",
            {
                "session_key": session_key,
                "driver_number": driver_num,
                "date>": win_start,
                "date<": win_end,
            },
        )

    if len(car) < 20:
        return None

    # Ordenar por tiempo relativo al inicio de la vuelta
    car.sort(key=lambda r: r["date"])
    ct = np.array([parse_iso(r["date"]) - t0 for r in car], dtype=float)
    spd = np.array([float(r.get("speed") or 0) for r in car], dtype=float)
    thr = np.array([float(r.get("throttle") or 0) for r in car], dtype=float)
    brk = np.array([100.0 if (r.get("brake") or 0) > 0 else 0.0 for r in car], dtype=float)
    gear = np.array([float(r.get("n_gear") or 0) for r in car], dtype=float)
    rpm = np.array([float(r.get("rpm") or 0) for r in car], dtype=float)

    # Deduplicar timestamps identicos
    _, uniq_idx = np.unique(ct, return_index=True)
    ct, spd, thr, brk, gear, rpm = ct[uniq_idx], spd[uniq_idx], thr[uniq_idx], brk[uniq_idx], gear[uniq_idx], rpm[uniq_idx]

    # Re-muestrear en tiempo denso [0, dur] e integrar velocidad -> distancia
    t_dense = np.linspace(0.0, dur, 900)
    spd_d = np.interp(t_dense, ct, spd)
    thr_d = np.interp(t_dense, ct, thr)
    brk_d = np.interp(t_dense, ct, brk)
    gear_d = np.round(np.interp(t_dense, ct, gear))
    rpm_d = np.interp(t_dense, ct, rpm)

    dt = np.diff(t_dense, prepend=0.0)
    dist_d = np.cumsum((spd_d / 3.6) * dt)
    total_dist = float(dist_d[-1]) if dist_d[-1] > 0 else 5000.0
    # Fraccion de vuelta [0..1] para alinear comparacion piloto vs piloto con gap exacto en meta
    frac_d = dist_d / total_dist

    frac_grid = np.linspace(0.0, 1.0, n_points)
    t_grid = np.interp(frac_grid, frac_d, t_dense)
    spd_grid = np.interp(frac_grid, frac_d, spd_d)
    thr_grid = np.interp(frac_grid, frac_d, thr_d)
    brk_grid = np.interp(frac_grid, frac_d, brk_d)
    gear_grid = np.round(np.interp(frac_grid, frac_d, gear_d))
    rpm_grid = np.interp(frac_grid, frac_d, rpm_d)

    xy = None
    if len(loc) >= 20:
        loc.sort(key=lambda r: r["date"])
        lt = np.array([parse_iso(r["date"]) - t0 for r in loc], dtype=float)
        lx = np.array([float(r["x"]) for r in loc], dtype=float)
        ly = np.array([float(r["y"]) for r in loc], dtype=float)
        _, l_uniq = np.unique(lt, return_index=True)
        lt, lx, ly = lt[l_uniq], lx[l_uniq], ly[l_uniq]
        x_grid = np.interp(t_grid, lt, lx)
        y_grid = np.interp(t_grid, lt, ly)
        xy = {
            "x": [round(float(v), 1) for v in x_grid],
            "y": [round(float(v), 1) for v in y_grid],
        }

    return {
        "lap_number": int(lap["lap_number"]),
        "lap_duration": round(dur, 3),
        "s1": round(float(lap["duration_sector_1"]), 3) if lap.get("duration_sector_1") else None,
        "s2": round(float(lap["duration_sector_2"]), 3) if lap.get("duration_sector_2") else None,
        "s3": round(float(lap["duration_sector_3"]), 3) if lap.get("duration_sector_3") else None,
        "speed_trap": int(lap["st_speed"]) if lap.get("st_speed") else int(round(float(np.max(spd_grid)))),
        "max_speed": int(round(float(np.max(spd_grid)))),
        "total_dist_m": round(total_dist, 1),
        "full_throttle_pct": round(float(np.mean(thr_d >= 95.0) * 100.0), 1),
        "braking_pct": round(float(np.mean(brk_d >= 50.0) * 100.0), 1),
        "t": [round(float(v), 3) for v in t_grid],
        "speed": [int(round(float(v))) for v in spd_grid],
        "throttle": [int(round(float(v))) for v in thr_grid],
        "brake": [1 if v >= 50 else 0 for v in brk_grid],
        "gear": [int(v) for v in gear_grid],
        "rpm": [int(round(float(v))) for v in rpm_grid],
        "xy": xy,
    }


def extract_gp(year: int, fastf1_name: str, openf1_query: dict, label_es: str):
    print(f"\n=== Extrayendo {label_es} ({year}) ===")

    # 1) FastF1: clasificacion y resultados oficiales (via jolpica-f1)
    ff_q = fastf1.get_session(year, fastf1_name, "Q")
    ff_q.load(telemetry=False, laps=False, weather=False, messages=False)
    ff_r = fastf1.get_session(year, fastf1_name, "R")
    ff_r.load(telemetry=False, laps=False, weather=False, messages=False)

    # 2) OpenF1: sesiones
    sessions = openf1_get("sessions", {"year": year, **openf1_query})
    q_sess = next(s for s in sessions if s["session_name"] == "Qualifying")
    r_sess = next(s for s in sessions if s["session_name"] == "Race")
    q_key = q_sess["session_key"]
    r_key = r_sess["session_key"]

    # Pilotos (OpenF1 incluye team_colour y acrónimo oficial)
    o_drivers = openf1_get("drivers", {"session_key": q_key})
    drv_map = {}
    for d in o_drivers:
        num = int(d["driver_number"])
        color = d.get("team_colour") or "94A3B8"
        if not color.startswith("#"):
            color = "#" + color
        drv_map[num] = {
            "number": num,
            "code": d["name_acronym"],
            "name": d["full_name"].title(),
            "team": d["team_name"],
            "color": color,
        }

    # Clima (media de Qualifying y Race)
    q_weather = openf1_get("weather", {"session_key": q_key})
    r_weather = openf1_get("weather", {"session_key": r_key})

    def summarize_weather(rows):
        if not rows:
            return None
        mid = rows[len(rows) // 2]
        return {
            "air_temp": round(float(mid["air_temperature"]), 1),
            "track_temp": round(float(mid["track_temperature"]), 1),
            "humidity": round(float(mid["humidity"]), 0),
            "wind_speed": round(float(mid["wind_speed"]), 1),
            "pressure": round(float(mid["pressure"]), 1),
            "rainfall": any((r.get("rainfall") or 0) > 0 for r in rows),
        }

    # Resultados de Qualy (FastF1)
    q_results = []
    for drv_num_str, row in ff_q.results.iterrows():
        num = int(drv_num_str)
        info = drv_map.get(
            num,
            {
                "number": num,
                "code": str(row["Abbreviation"]),
                "name": str(row["FullName"]),
                "team": str(row["TeamName"]),
                "color": "#94A3B8",
            },
        )

        def td_sec(val):
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return None
            try:
                sec = val.total_seconds()
                return None if math.isnan(sec) else round(sec, 3)
            except Exception:
                return None

        pos = int(row["Position"]) if not math.isnan(row["Position"]) else 99
        q_results.append(
            {
                "pos": pos,
                **info,
                "q1": td_sec(row.get("Q1")),
                "q2": td_sec(row.get("Q2")),
                "q3": td_sec(row.get("Q3")),
            }
        )
    q_results.sort(key=lambda x: x["pos"])

    # Descargar todas las vueltas de Qualifying en 1 sola peticion
    all_q_laps = openf1_get("laps", {"session_key": q_key})
    laps_by_drv = {}
    for l in all_q_laps:
        if l.get("lap_duration") and l.get("date_start") and not l.get("is_pit_out_lap"):
            dn = int(l["driver_number"])
            laps_by_drv.setdefault(dn, []).append(l)

    # Seleccionar Top 8 de Qualy + Checo (#11) y Colapinto (#43) si participaron y no estan en el Top 8
    selected_nums = [d["number"] for d in q_results[:8]]
    for extra in (11, 43):
        if extra in laps_by_drv and extra not in selected_nums and len(selected_nums) < 10:
            selected_nums.append(extra)

    telemetry = {}
    track_xy = None
    ref_track_dist = None
    for num in selected_nums:
        cand = laps_by_drv.get(num, [])
        if not cand:
            continue
        best_lap = min(cand, key=lambda l: float(l["lap_duration"]))
        code = drv_map[num]["code"]
        print(f"  -> Telemetria Q: {code} (#{num}), vuelta {best_lap['lap_number']} ({best_lap['lap_duration']}s)")
        tel = extract_telemetry_for_lap(q_key, num, best_lap, n_points=220, fetch_loc=(track_xy is None))
        if tel:
            if track_xy is None and tel["xy"] is not None:
                track_xy = tel["xy"]
                ref_track_dist = tel["total_dist_m"]
            # Quitar xy repetido para no inflar el JSON
            tel.pop("xy", None)
            telemetry[code] = tel

    # 3) Carrera: resultados oficiales (FastF1) + vueltas y stints (OpenF1)
    r_results = []
    for drv_num_str, row in ff_r.results.iterrows():
        num = int(drv_num_str)
        info = drv_map.get(
            num,
            {
                "number": num,
                "code": str(row["Abbreviation"]),
                "name": str(row["FullName"]),
                "team": str(row["TeamName"]),
                "color": "#94A3B8",
            },
        )
        pos = int(row["Position"]) if not math.isnan(row["Position"]) else 99
        grid = int(row["GridPosition"]) if not math.isnan(row["GridPosition"]) else 0
        pts = float(row["Points"]) if not math.isnan(row["Points"]) else 0.0
        r_results.append(
            {
                "pos": pos,
                "grid": grid,
                "gain": (grid - pos) if grid > 0 and pos < 99 else 0,
                "points": pts,
                "status": str(row["Status"]),
                **info,
            }
        )
    r_results.sort(key=lambda x: x["pos"])

    all_r_laps = openf1_get("laps", {"session_key": r_key})
    all_r_stints = openf1_get("stints", {"session_key": r_key})

    # Organizar stints y ritmo por piloto (Top 10 de carrera + Checo #11 si no esta en top 10)
    race_nums = [d["number"] for d in r_results[:10]]
    if 11 in drv_map and 11 not in race_nums:
        race_nums.append(11)

    stints_by_code = {}
    for num in race_nums:
        code = drv_map[num]["code"]
        ds = [s for s in all_r_stints if int(s["driver_number"]) == num]
        ds.sort(key=lambda s: int(s["stint_number"]))
        stints_by_code[code] = [
            {
                "stint": int(s["stint_number"]),
                "compound": (s.get("compound") or "UNKNOWN").upper(),
                "start": int(s["lap_start"]),
                "end": int(s["lap_end"]),
                "age": int(s.get("tyre_age_at_start") or 0),
            }
            for s in ds
            if s.get("lap_start") is not None and s.get("lap_end") is not None
        ]

    # Ritmo vuelta a vuelta (filtrando vueltas anormalmente lentas por SC/pits en el frontend, guardando todo limpio)
    race_laps_by_code = {}
    total_laps = 0
    for num in race_nums:
        code = drv_map[num]["code"]
        dl = [l for l in all_r_laps if int(l["driver_number"]) == num and l.get("lap_duration")]
        dl.sort(key=lambda l: int(l["lap_number"]))
        if dl:
            total_laps = max(total_laps, int(dl[-1]["lap_number"]))
        race_laps_by_code[code] = [
            {
                "lap": int(l["lap_number"]),
                "sec": round(float(l["lap_duration"]), 3),
                "pit_out": bool(l.get("is_pit_out_lap")),
            }
            for l in dl
        ]

    return {
        "id": fastf1_name.lower().replace(" ", "_"),
        "label": label_es,
        "year": year,
        "circuit": q_sess["circuit_short_name"],
        "country": q_sess["country_name"],
        "date_qualy": q_sess["date_start"][:10],
        "date_race": r_sess["date_start"][:10],
        "track_length_m": round(ref_track_dist or 5000.0, 0),
        "total_laps": total_laps,
        "weather_qualy": summarize_weather(q_weather),
        "weather_race": summarize_weather(r_weather),
        "track_xy": track_xy,
        "qualy_results": q_results,
        "telemetry": telemetry,
        "race_results": r_results,
        "race_stints": stints_by_code,
        "race_laps": race_laps_by_code,
    }


def main():
    gps = [
        extract_gp(2026, "Las Vegas", {"location": "Las Vegas"}, "GP de Las Vegas 2026"),
        extract_gp(2026, "Mexico City", {"country_name": "Mexico"}, "GP de la Ciudad de México 2026"),
    ]
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "gp_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.utcnow().isoformat() + "Z", "gps": gps}, f, ensure_ascii=False)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"\nGuardado {out_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
