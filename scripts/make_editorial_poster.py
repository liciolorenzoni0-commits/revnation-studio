#!/usr/bin/env python3
"""
Prototipo Editorial Suizo / Motorsport (Anti-AI-Slop) para @revnationmx
Cero cajas redondeadas, cero pills, cero cajas de leyenda:
  - Grilla editorial suiza con lineas de 1px y espacio negativo
  - Tipografia condensada de poster (Bebas Neue) + IBM Plex Sans/Mono
  - Grano analogico sutil sobre British Racing Green mate (#0D2017)
  - Etiquetas directas sobre las curvas (estilo FT / F1 TV Broadcast)
"""

import glob
import hashlib
import json
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "static", "fonts")
for _ttf in glob.glob(os.path.join(FONTS_DIR, "*.ttf")):
    fm.fontManager.addfont(_ttf)

CONFIG = {
    "session_key": 11420,
    "cache_dir": "/tmp/openf1_cache",
    "output_path": os.path.join(SCRIPT_DIR, "output", "editorial_01_ver_vs_rus.png"),
    # Paleta British Racing Green Editorial
    "bg": "#0D2017",
    "ink": "#F3EDE0",         # Hueso / Crema editorial
    "ink_soft": "#9CB0A3",    # Salvia apagado
    "hairline": "#2B4638",    # Lineas suizas 1px
    "red": "#E63935",         # Acento racing / incidente
    "ver_col": "#5B9BFF",     # Verstappen
    "rus_col": "#1AD6B8",     # Russell
    "ant_col": "#6F8A7B",     # Antonelli (contexto sutil)
    # Tipografias instaladas
    "font_display": "Bebas Neue",
    "font_sans": "IBM Plex Sans",
    "font_mono": "IBM Plex Mono",
}


def load_cached(ep, params):
    key = ep + "?" + json.dumps(params, sort_keys=True)
    path = os.path.join(CONFIG["cache_dir"], hashlib.md5(key.encode()).hexdigest() + ".json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_series():
    rk = CONFIG["session_key"]
    laps = load_cached("laps", {"session_key": rk})
    pos_rows = load_cached("position", {"session_key": rk})
    pos_by_drv = {}
    for r in pos_rows:
        pos_by_drv.setdefault(r["driver_number"], []).append((parse_ts(r["date"]), int(r["position"])))
    for dn in pos_by_drv:
        pos_by_drv[dn].sort()

    def pos_at(dn, t):
        cur = None
        for pt, pp in pos_by_drv.get(dn, []):
            if pt <= t:
                cur = pp
            else:
                break
        return cur

    series = {3: [], 63: [], 12: []}
    for l in laps:
        dn = l["driver_number"]
        if dn not in series or not l.get("date_start") or not l.get("lap_duration"):
            continue
        t_end = parse_ts(l["date_start"]) + float(l["lap_duration"])
        series[dn].append({"lap": int(l["lap_number"]), "sec": float(l["lap_duration"]), "pos": pos_at(dn, t_end)})
    for dn in series:
        series[dn].sort(key=lambda x: x["lap"])
    return series


def add_film_grain(img_path, strength=5.5):
    """Agrega grano analogico sutil para quitar el aspecto digital/plano."""
    img = Image.open(img_path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    rng = np.random.default_rng(2026)
    noise = rng.normal(0.0, strength, size=(arr.shape[0], arr.shape[1], 1))
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    Image.fromarray(arr).save(img_path, optimize=True)


def render():
    series = load_series()
    os.makedirs(os.path.dirname(CONFIG["output_path"]), exist_ok=True)

    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=CONFIG["bg"])
    ax = fig.add_axes([0, 0, 1, 1], facecolor=CONFIG["bg"])
    ax.set_xlim(0, 1080)
    ax.set_ylim(0, 1350)
    ax.axis("off")

    L, R = 72, 1008  # Margenes suizos estrictos

    # --- 1. MASTHEAD EDITORIAL ---
    ax.text(L, 1288, "GP DE LAS VEGAS 2026  ·  ANÁLISIS DE CARRERA", color=CONFIG["ink_soft"],
            fontsize=12.5, fontfamily=CONFIG["font_mono"], va="bottom", ha="left")
    ax.text(R, 1288, "REV NATION MX", color=CONFIG["ink"],
            fontsize=12.5, fontweight="bold", fontfamily=CONFIG["font_mono"], va="bottom", ha="right")

    ax.plot([L, R], [1274, 1274], color=CONFIG["hairline"], lw=1.2)
    ax.add_patch(patches.Rectangle((L, 1272.5), 42, 3.5, facecolor=CONFIG["red"], edgecolor="none"))

    # Titular condensado de revista/poster (2 lineas con control exacto de interlineado)
    ax.text(L, 1252, "6 CAMBIOS DE LÍDER.",
            color=CONFIG["ink"], fontsize=56, fontfamily=CONFIG["font_display"],
            va="top", ha="left")
    ax.text(L, 1180, "UNA VUELTA LO DEFINIÓ TODO.",
            color=CONFIG["ink"], fontsize=56, fontfamily=CONFIG["font_display"],
            va="top", ha="left")

    # Bajada limpia debajo del titular con aire editorial
    ax.text(L, 1084, "Verstappen y Russell pelearon el P1 tras el Safety Car — hasta la curva 5 en la V48.",
            color=CONFIG["ink_soft"], fontsize=14, fontfamily=CONFIG["font_sans"],
            va="top", ha="left")

    ax.plot([L, R], [1038, 1038], color=CONFIG["hairline"], lw=1.0)

    # --- 2. GRAFICA PRINCIPAL (SIN CAJAS, DIRECTA SOBRE EL LIENZO) ---
    ax.text(L, 1002, "POSICIÓN EN PISTA  ·  VUELTAS 26 A 50", color=CONFIG["ink_soft"],
            fontsize=11.5, fontfamily=CONFIG["font_mono"], va="top")

    ax1 = fig.add_axes([L / 1080, 0.435, (R - L - 68) / 1080, 0.290], facecolor="none")
    for sp in ("top", "right", "left"):
        ax1.spines[sp].set_visible(False)
    ax1.spines["bottom"].set_color(CONFIG["hairline"])
    ax1.spines["bottom"].set_linewidth(1.0)

    ax1.invert_yaxis()
    ax1.set_ylim(9.8, 0.5)
    ax1.set_xlim(25.6, 50.4)
    ax1.set_yticks([1, 3, 6, 9])
    ax1.set_yticklabels(["P1", "P3", "P6", "P9"], fontfamily=CONFIG["font_mono"], fontsize=11.5, color=CONFIG["ink_soft"])
    ax1.set_xticks([26, 30, 35, 40, 45, 50])
    ax1.set_xticklabels([])
    ax1.tick_params(axis="both", length=0, pad=10)
    ax1.grid(axis="y", color=CONFIG["hairline"], lw=0.8, alpha=0.55)

    # Linea vertical sutil en V48
    ax1.axvline(48, color=CONFIG["red"], lw=1.2, linestyle=":", alpha=0.75, zorder=1)

    # Antonelli (contexto sutil atras)
    ant_pts = [p for p in series[12] if p["lap"] >= 26]
    ax1.plot([p["lap"] for p in ant_pts], [p["pos"] for p in ant_pts],
             color=CONFIG["ant_col"], lw=1.8, linestyle="--", alpha=0.75, zorder=2)

    # Russell & Verstappen
    rus_pts = [p for p in series[63] if p["lap"] >= 26]
    ver_pts = [p for p in series[3] if p["lap"] >= 26]
    ax1.plot([p["lap"] for p in rus_pts], [p["pos"] for p in rus_pts],
             color=CONFIG["rus_col"], lw=3.6, solid_capstyle="round", zorder=3)
    ax1.plot([p["lap"] for p in ver_pts], [p["pos"] for p in ver_pts],
             color=CONFIG["ver_col"], lw=3.6, solid_capstyle="round", zorder=4)

    # Puntos discretos en cambios de liderato de RUS (V28, V31, V36)
    for l_lead in (28, 31, 36):
        ax1.scatter([l_lead], [1], s=42, color=CONFIG["rus_col"], edgecolor=CONFIG["bg"], linewidth=1.8, zorder=5)

    # Punto incidente V48
    ax1.scatter([48], [9], s=68, color=CONFIG["red"], edgecolor=CONFIG["ink"], linewidth=1.8, zorder=6)

    # Etiquetas directas al final de cada curva (ZERO legend box!)
    ax1.text(50.65, 1.0, "VER  P1", color=CONFIG["ver_col"], fontsize=12.5, fontweight="bold", fontfamily=CONFIG["font_mono"], va="center", clip_on=False)
    ax1.text(50.65, 4.0, "ANT  P4", color=CONFIG["ant_col"], fontsize=11.5, fontfamily=CONFIG["font_mono"], va="center", clip_on=False)
    ax1.text(50.65, 9.0, "RUS  P9", color=CONFIG["rus_col"], fontsize=12.5, fontweight="bold", fontfamily=CONFIG["font_mono"], va="center", clip_on=False)

    # Anotaciones tipograficas limpias SIN CAJAS
    ax1.text(28.0, 5.1, "RUS TOMA LA PUNTA", color=CONFIG["rus_col"], fontsize=11, fontweight="bold", fontfamily=CONFIG["font_mono"], va="top")
    ax1.text(28.0, 5.95, "V28 · V31 · V36–37", color=CONFIG["ink_soft"], fontsize=10.5, fontfamily=CONFIG["font_mono"], va="top")
    ax1.plot([30.8, 31.0], [4.5, 1.35], color=CONFIG["rus_col"], lw=0.9, alpha=0.55)

    ax1.text(47.2, 7.35, "V48 · CURVA 5", color=CONFIG["red"], fontsize=11.5, fontweight="bold", fontfamily=CONFIG["font_mono"], ha="right", va="bottom")
    ax1.text(47.2, 8.25, "+11.2 s  ·  P3 → P9", color=CONFIG["ink"], fontsize=11, fontfamily=CONFIG["font_mono"], ha="right", va="bottom")

    # --- 3. BANDA INFERIOR DE RITMO POR VUELTA (ALINEADA AL MISMO EJE X) ---
    ax.text(L, 544, "RITMO POR VUELTA (V26–V47)", color=CONFIG["ink_soft"], fontsize=11.5, fontfamily=CONFIG["font_mono"], va="center")
    ax.add_patch(patches.Rectangle((L + 334, 538), 11, 11, facecolor=CONFIG["ver_col"], edgecolor="none"))
    ax.text(L + 354, 544, "VER MÁS RÁPIDO (ARRIBA)", color=CONFIG["ver_col"], fontsize=11, fontweight="bold", fontfamily=CONFIG["font_mono"], va="center")
    ax.add_patch(patches.Rectangle((L + 616, 538), 11, 11, facecolor=CONFIG["rus_col"], edgecolor="none"))
    ax.text(L + 636, 544, "RUS MÁS RÁPIDO (ABAJO)", color=CONFIG["rus_col"], fontsize=11, fontweight="bold", fontfamily=CONFIG["font_mono"], va="center")

    ax2 = fig.add_axes([L / 1080, 0.245, (R - L - 68) / 1080, 0.142], facecolor="none")
    for sp in ("top", "right", "left"):
        ax2.spines[sp].set_visible(False)
    ax2.spines["bottom"].set_color(CONFIG["hairline"])
    ax2.spines["bottom"].set_linewidth(1.0)

    ver_map = {p["lap"]: p["sec"] for p in series[3]}
    rus_map = {p["lap"]: p["sec"] for p in series[63]}
    laps_cmp = [l for l in range(26, 48) if l in ver_map and l in rus_map]
    diffs = [rus_map[l] - ver_map[l] for l in laps_cmp]  # >0 VER mas rapido, <0 RUS mas rapido
    bar_cols = [CONFIG["ver_col"] if d >= 0 else CONFIG["rus_col"] for d in diffs]

    ax2.axhline(0, color=CONFIG["ink_soft"], lw=0.9, alpha=0.6)
    ax2.axvline(48, color=CONFIG["red"], lw=1.2, linestyle=":", alpha=0.75)
    ax2.bar(laps_cmp, diffs, color=bar_cols, width=0.58, alpha=0.92)
    ax2.set_xlim(25.6, 50.4)
    ax2.set_ylim(-0.9, 0.9)
    ax2.set_yticks([-0.5, 0, 0.5])
    ax2.set_yticklabels(["-0.5s", "0", "+0.5s"], fontfamily=CONFIG["font_mono"], fontsize=10.5, color=CONFIG["ink_soft"])
    ax2.set_xticks([26, 30, 35, 40, 45, 50])
    ax2.set_xticklabels(["V26", "V30", "V35", "V40", "V45", "V50"], fontfamily=CONFIG["font_mono"], fontsize=11.5, color=CONFIG["ink_soft"])
    ax2.tick_params(axis="both", length=0, pad=9)

    # --- 4. COLUMNAS DE DATOS SUIZAS (SIN CAJAS, SOLO SEPARADORES 1PX) ---
    ax.plot([L, R], [268, 268], color=CONFIG["hairline"], lw=1.2)
    stats = [
        ("3×", "VECES LÍDER RUSSELL", "V28, V31 y V36–37", CONFIG["rus_col"]),
        ("1:36.33", "RITMO RUS EN V47", "a 0.23s de ser el más rápido", CONFIG["ink"]),
        ("−6 POS", "CAÍDA EN VUELTA 48", "salida en curva 5 (+11.2s)", CONFIG["red"]),
    ]
    col_w = (R - L) / 3.0
    for idx, (num, title, sub, col) in enumerate(stats):
        x0 = L + idx * col_w
        if idx > 0:
            ax.plot([x0 - 18, x0 - 18], [132, 248], color=CONFIG["hairline"], lw=1.0)
        ax.text(x0, 246, num, color=col, fontsize=48, fontfamily=CONFIG["font_display"], va="top", ha="left")
        ax.text(x0, 174, title, color=CONFIG["ink"], fontsize=11.5, fontweight="bold", fontfamily=CONFIG["font_mono"], va="top", ha="left")
        ax.text(x0, 150, sub, color=CONFIG["ink_soft"], fontsize=12.5, fontfamily=CONFIG["font_sans"], va="top", ha="left")

    # --- 5. COLOFON MINIMAL ---
    ax.plot([L, R], [96, 96], color=CONFIG["hairline"], lw=1.0)
    ax.text(L, 62, "@revnationmx", color=CONFIG["ink"], fontsize=13, fontweight="bold", fontfamily=CONFIG["font_mono"], va="center", ha="left")
    ax.text(540, 62, "liciolorenzoni.tech/f1", color=CONFIG["ink_soft"], fontsize=12.5, fontfamily=CONFIG["font_mono"], va="center", ha="center")
    ax.text(R, 62, "DATOS: OPENF1 / FASTF1", color=CONFIG["ink_soft"], fontsize=11.5, fontfamily=CONFIG["font_mono"], va="center", ha="right")

    fig.savefig(CONFIG["output_path"], dpi=100)
    plt.close(fig)
    add_film_grain(CONFIG["output_path"], strength=4.8)
    print("Generado editorial:", CONFIG["output_path"])


if __name__ == "__main__":
    render()
