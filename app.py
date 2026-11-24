#!/usr/bin/env python3
"""
Rev Nation MX · Editorial Studio Backend (FastAPI + OpenF1)
Ligero, sin login requerido, con cache persistente en disco (/app/cache).
"""

import hashlib
import json
import math
import os
import time
from datetime import datetime, timedelta
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

CACHE_DIR = os.environ.get("CACHE_DIR", "/app/cache")
os.makedirs(CACHE_DIR, exist_ok=True)

OPENF1_BASE = "https://api.openf1.org/v1"
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "RevNationMX-Studio/1.0"})

app = FastAPI(title="Rev Nation MX · Editorial Studio")


def parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def openf1_get(endpoint: str, params: dict, ttl_seconds: Optional[int] = None):
    """Consulta a OpenF1 con cache en disco y reintentos suaves ante HTTP 429."""
    key_raw = endpoint + "?" + json.dumps(params, sort_keys=True)
    cache_path = os.path.join(CACHE_DIR, hashlib.md5(key_raw.encode()).hexdigest() + ".json")

    if os.path.exists(cache_path):
        if ttl_seconds is None or (time.time() - os.path.getmtime(cache_path)) < ttl_seconds:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

    url = f"{OPENF1_BASE}/{endpoint}"
    last_err = None
    for attempt in range(5):
        try:
            resp = HTTP.get(url, params=params, timeout=25)
            if resp.status_code == 429:
                ra = resp.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else 2.5 * (attempt + 1)
                time.sleep(min(wait, 15.0))
                continue
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            time.sleep(0.28)
            return data if isinstance(data, list) else []
        except Exception as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))

    # Si falla la red pero existe cache viejo, devolverlo
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(status_code=502, detail=f"OpenF1 error en {endpoint}: {last_err}")


def interp_1d(xs, ys, target_xs):
    """Interpolacion lineal pura en Python (evita depender de numpy en la imagen Docker)."""
    out = []
    n = len(xs)
    j = 0
    for tx in target_xs:
        if tx <= xs[0]:
            out.append(ys[0])
            continue
        if tx >= xs[-1]:
            out.append(ys[-1])
            continue
        while j < n - 2 and xs[j + 1] < tx:
            j += 1
        span = xs[j + 1] - xs[j]
        frac = (tx - xs[j]) / span if span > 1e-9 else 0.0
        out.append(ys[j] + (ys[j + 1] - ys[j]) * frac)
    return out


@app.get("/api/health")
def health():
    return {"status": "ok", "cache_dir": CACHE_DIR}


@app.get("/api/meetings")
def list_meetings(year: int = Query(2026, ge=2023, le=2030)):
    """Devuelve los Grandes Premios del año con sus session_key de Qualifying y Race."""
    # TTL de 10 min para el año en curso para detectar Qatar / sesiones nuevas
    ttl = 600 if year >= datetime.utcnow().year else None
    sessions = openf1_get("sessions", {"year": year}, ttl_seconds=ttl)

    by_meeting = {}
    for s in sessions:
        if s.get("is_cancelled"):
            continue
        mk = s["meeting_key"]
        m = by_meeting.setdefault(
            mk,
            {
                "meeting_key": mk,
                "circuit": s.get("circuit_short_name") or s.get("location") or "GP",
                "country": s.get("country_name") or "",
                "location": s.get("location") or "",
                "date": (s.get("date_start") or "")[:10],
                "qualy_key": None,
                "race_key": None,
                "sprint_key": None,
            },
        )
        sname = (s.get("session_name") or "").lower()
        if sname == "qualifying":
            m["qualy_key"] = s["session_key"]
            m["date"] = (s.get("date_start") or m["date"])[:10]
        elif sname == "race":
            m["race_key"] = s["session_key"]
            m["date"] = (s.get("date_start") or m["date"])[:10]
        elif sname == "sprint":
            m["sprint_key"] = s["session_key"]

    meetings = [m for m in by_meeting.values() if m["race_key"] or m["qualy_key"]]
    meetings.sort(key=lambda x: x["date"], reverse=True)
    return {"year": year, "meetings": meetings}


@app.get("/api/race/{session_key}")
def get_race_bundle(session_key: int):
    """Descarga pilotos, vueltas, posiciones por vuelta, stints y Safety Cars de una carrera."""
    drivers_raw = openf1_get("drivers", {"session_key": session_key})
    laps_raw = openf1_get("laps", {"session_key": session_key})
    pos_raw = openf1_get("position", {"session_key": session_key})
    stints_raw = openf1_get("stints", {"session_key": session_key})
    rc_raw = openf1_get("race_control", {"session_key": session_key})

    if not drivers_raw or not laps_raw:
        raise HTTPException(status_code=404, detail="Todavía no hay datos de carrera disponibles para esta sesión.")

    # Mapa de pilotos
    drivers = {}
    for d in drivers_raw:
        dn = int(d["driver_number"])
        col = d.get("team_colour") or "94A3B8"
        if not col.startswith("#"):
            col = "#" + col
        drivers[dn] = {
            "number": dn,
            "code": d.get("name_acronym") or str(dn),
            "name": (d.get("full_name") or d.get("broadcast_name") or str(dn)).title(),
            "team": d.get("team_name") or "",
            "color": col,
        }

    # Historial de posiciones por timestamp
    pos_by_dn = {}
    for r in pos_raw:
        if r.get("date") and r.get("position") is not None:
            pos_by_dn.setdefault(int(r["driver_number"]), []).append((parse_ts(r["date"]), int(r["position"])))
    for dn in pos_by_dn:
        pos_by_dn[dn].sort()

    def pos_at(dn: int, ts_val: float):
        arr = pos_by_dn.get(dn)
        if not arr:
            return None
        lo, hi = 0, len(arr) - 1
        ans = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if arr[mid][0] <= ts_val:
                ans = arr[mid][1]
                lo = mid + 1
            else:
                hi = mid - 1
        return ans

    # Series vuelta a vuelta por codigo de piloto
    series = {}
    total_laps = 0
    for l in laps_raw:
        dn = int(l["driver_number"])
        if dn not in drivers or not l.get("date_start") or not l.get("lap_duration"):
            continue
        code = drivers[dn]["code"]
        lap_n = int(l["lap_number"])
        dur = float(l["lap_duration"])
        total_laps = max(total_laps, lap_n)
        p_end = pos_at(dn, parse_ts(l["date_start"]) + dur)
        series.setdefault(code, []).append([lap_n, p_end, round(dur, 3), 1 if l.get("is_pit_out_lap") else 0])

    for code in series:
        series[code].sort(key=lambda r: r[0])

    # Orden final aproximado segun ultima posicion registrada
    final_order = []
    for dn, info in drivers.items():
        code = info["code"]
        pts = series.get(code, [])
        last_pos = pts[-1][1] if (pts and pts[-1][1] is not None) else (pos_by_dn.get(dn, [(0, 99)])[-1][1])
        laps_done = pts[-1][0] if pts else 0
        final_order.append({**info, "pos": last_pos or 99, "laps": laps_done})
    final_order.sort(key=lambda x: (-x["laps"], x["pos"]))
    for idx, d in enumerate(final_order, 1):
        d["order"] = idx

    # Stints por codigo
    stints = {}
    for s in stints_raw:
        dn = int(s["driver_number"])
        if dn not in drivers or s.get("lap_start") is None or s.get("lap_end") is None:
            continue
        code = drivers[dn]["code"]
        stints.setdefault(code, []).append(
            {
                "stint": int(s["stint_number"]),
                "compound": (s.get("compound") or "UNKNOWN").upper(),
                "start": int(s["lap_start"]),
                "end": int(s["lap_end"]),
            }
        )
    for code in stints:
        stints[code].sort(key=lambda x: x["stint"])

    # Safety Cars y eventos destacados
    sc_laps = []
    sc_start = None
    incidents = []
    for m in rc_raw:
        msg = (m.get("message") or "").upper()
        lap = m.get("lap_number")
        if "SAFETY CAR DEPLOYED" in msg and lap:
            sc_start = int(lap)
        elif ("SAFETY CAR IN THIS LAP" in msg or "TRACK CLEAR" in msg) and sc_start is not None and lap:
            sc_laps.append([sc_start, int(lap)])
            sc_start = None
        if lap and any(k in msg for k in ("TIME PENALTY", "CAUSING A COLLISION", "SAFETY CAR DEPLOYED")):
            incidents.append({"lap": int(lap), "msg": m.get("message", "")})

    return {
        "session_key": session_key,
        "total_laps": total_laps,
        "drivers": final_order,
        "series": series,
        "stints": stints,
        "safety_cars": sc_laps,
        "incidents": incidents[:25],
    }


@app.get("/api/qualy_drivers/{session_key}")
def get_qualy_drivers(session_key: int):
    """Lista los pilotos ordenados por su mejor vuelta de Qualifying."""
    drivers_raw = openf1_get("drivers", {"session_key": session_key})
    laps_raw = openf1_get("laps", {"session_key": session_key})
    if not drivers_raw or not laps_raw:
        raise HTTPException(status_code=404, detail="Todavía no hay vueltas de Qualifying para esta sesión.")

    best_by_dn = {}
    for l in laps_raw:
        if not l.get("lap_duration") or not l.get("date_start") or l.get("is_pit_out_lap"):
            continue
        dn = int(l["driver_number"])
        dur = float(l["lap_duration"])
        if dn not in best_by_dn or dur < best_by_dn[dn]["lap_duration"]:
            best_by_dn[dn] = l

    out = []
    for d in drivers_raw:
        dn = int(d["driver_number"])
        best = best_by_dn.get(dn)
        if not best:
            continue
        col = d.get("team_colour") or "94A3B8"
        if not col.startswith("#"):
            col = "#" + col
        out.append(
            {
                "number": dn,
                "code": d.get("name_acronym") or str(dn),
                "name": (d.get("full_name") or str(dn)).title(),
                "team": d.get("team_name") or "",
                "color": col,
                "best_lap": round(float(best["lap_duration"]), 3),
                "lap_number": int(best["lap_number"]),
            }
        )
    out.sort(key=lambda x: x["best_lap"])
    for idx, d in enumerate(out, 1):
        d["pos"] = idx
    return {"session_key": session_key, "drivers": out}


@app.get("/api/qualy_compare/{session_key}")
def compare_qualy(session_key: int, driver_a: int, driver_b: int):
    """Descarga telemetria real de la vuelta rapida de 2 pilotos + mapa X/Y del circuito."""
    laps_raw = openf1_get("laps", {"session_key": session_key})
    drivers_raw = openf1_get("drivers", {"session_key": session_key})
    drv_map = {}
    for d in drivers_raw:
        dn = int(d["driver_number"])
        col = d.get("team_colour") or "94A3B8"
        if not col.startswith("#"):
            col = "#" + col
        drv_map[dn] = {
            "number": dn,
            "code": d.get("name_acronym") or str(dn),
            "name": (d.get("full_name") or str(dn)).title(),
            "team": d.get("team_name") or "",
            "color": col,
        }

    def best_lap_for(dn: int):
        cands = [
            l for l in laps_raw
            if int(l["driver_number"]) == dn and l.get("lap_duration") and l.get("date_start") and not l.get("is_pit_out_lap")
        ]
        if not cands:
            raise HTTPException(status_code=404, detail=f"Sin vuelta válida para piloto #{dn}")
        return min(cands, key=lambda l: float(l["lap_duration"]))

    def fetch_lap_tel(dn: int, lap: dict, fetch_loc: bool):
        t0_dt = datetime.fromisoformat(lap["date_start"].replace("Z", "+00:00"))
        dur = float(lap["lap_duration"])
        t0 = t0_dt.timestamp()
        win_s = (t0_dt - timedelta(seconds=1.5)).isoformat()
        win_e = (t0_dt + timedelta(seconds=dur + 1.5)).isoformat()

        car = openf1_get("car_data", {"session_key": session_key, "driver_number": dn, "date>": win_s, "date<": win_e})
        if len(car) < 15:
            raise HTTPException(status_code=404, detail=f"Sin telemetría car_data para #{dn}")
        car.sort(key=lambda r: r["date"])

        # Deduplicar tiempos
        ct, spd, thr, brk = [], [], [], []
        last_t = None
        for r in car:
            rt = parse_ts(r["date"]) - t0
            if last_t is not None and rt <= last_t + 1e-6:
                continue
            last_t = rt
            ct.append(rt)
            spd.append(float(r.get("speed") or 0))
            thr.append(float(r.get("throttle") or 0))
            brk.append(1.0 if (r.get("brake") or 0) > 0 else 0.0)

        # Grilla densa de tiempo -> integrar distancia
        n_dense = 600
        t_dense = [dur * i / (n_dense - 1) for i in range(n_dense)]
        spd_d = interp_1d(ct, spd, t_dense)
        thr_d = interp_1d(ct, thr, t_dense)
        brk_d = interp_1d(ct, brk, t_dense)

        dist_d = [0.0]
        dt = dur / (n_dense - 1)
        for i in range(1, n_dense):
            dist_d.append(dist_d[-1] + (spd_d[i] / 3.6) * dt)
        total_dist = dist_d[-1] if dist_d[-1] > 100 else 5000.0
        frac_d = [d / total_dist for d in dist_d]

        n_pts = 200
        f_grid = [i / (n_pts - 1) for i in range(n_pts)]
        t_grid = interp_1d(frac_d, t_dense, f_grid)
        spd_grid = interp_1d(frac_d, spd_d, f_grid)
        thr_grid = interp_1d(frac_d, thr_d, f_grid)

        xy = None
        if fetch_loc:
            loc = openf1_get("location", {"session_key": session_key, "driver_number": dn, "date>": win_s, "date<": win_e})
            if len(loc) >= 15:
                loc.sort(key=lambda r: r["date"])
                lt, lx, ly = [], [], []
                last_lt = None
                for r in loc:
                    rt = parse_ts(r["date"]) - t0
                    if last_lt is not None and rt <= last_lt + 1e-6:
                        continue
                    last_lt = rt
                    lt.append(rt)
                    lx.append(float(r["x"]))
                    ly.append(float(r["y"]))
                xy = {
                    "x": [round(v, 1) for v in interp_1d(lt, lx, t_grid)],
                    "y": [round(v, 1) for v in interp_1d(lt, ly, t_grid)],
                }

        full_thr = round(sum(1 for v in thr_d if v >= 95.0) * 100.0 / len(thr_d), 1)
        return {
            "driver": drv_map[dn],
            "lap_number": int(lap["lap_number"]),
            "lap_duration": round(dur, 3),
            "s1": round(float(lap["duration_sector_1"]), 3) if lap.get("duration_sector_1") else None,
            "s2": round(float(lap["duration_sector_2"]), 3) if lap.get("duration_sector_2") else None,
            "s3": round(float(lap["duration_sector_3"]), 3) if lap.get("duration_sector_3") else None,
            "max_speed": int(round(max(spd_grid))),
            "full_throttle_pct": full_thr,
            "total_dist_m": round(total_dist, 0),
            "t": [round(v, 3) for v in t_grid],
            "speed": [int(round(v)) for v in spd_grid],
            "throttle": [int(round(v)) for v in thr_grid],
            "xy": xy,
        }

    la = best_lap_for(driver_a)
    lb = best_lap_for(driver_b)
    ta = fetch_lap_tel(driver_a, la, fetch_loc=True)
    tb = fetch_lap_tel(driver_b, lb, fetch_loc=False)
    xy = ta.pop("xy", None)
    tb.pop("xy", None)
    return {"track_xy": xy, "track_length_m": ta["total_dist_m"], "a": ta, "b": tb}


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
