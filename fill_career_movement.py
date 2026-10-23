#!/usr/bin/env python3
"""Attach real pitch shapes from the fullest tracked season.

Order for each pitch type: newest full MLB season, then other MLB seasons,
then MLB spring training, then the Prospect Savant row already on file.
Nothing is invented. A pitch with no tracked break stays blank.
"""

from __future__ import annotations

import csv
import os
import fcntl
import io
import json
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RUNS = ROOT / "runs"
BOARD_DIR = RUNS / "mlb_movement"
SPRING_DIR = RUNS / "spring_statcast"
LOCK_PATH = RUNS / "lmb_synergy.lock"
ARSENAL = DATA / "pregame_pitcher_arsenals.json"
SAVANT = DATA / "savant_movement.json"
OUT = DATA / "career_movement.json"
UA = {"User-Agent": "Mozilla/5.0"}
PITCH_TYPES = ("FF", "SI", "FC", "SL", "ST", "SV", "CU", "KC", "CH", "FS", "FO", "SC")
MLB_YEARS = tuple(range(2026, 2014, -1))
SPRING_YEARS = tuple(range(2026, 2018, -1))
MIN_PITCHES = 8


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch(url: str, timeout: float = 60) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(path)


def download_boards() -> dict[int, dict[int, list[dict]]]:
    """mlb id → year → pitch rows from the Baseball Savant movement leaderboard."""
    seasons: dict[int, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    BOARD_DIR.mkdir(parents=True, exist_ok=True)
    for year in MLB_YEARS:
        for code in PITCH_TYPES:
            path = BOARD_DIR / f"{year}_{code}.csv"
            if path.is_file() and path.stat().st_size > 200:
                text = path.read_text()
            else:
                url = (
                    "https://baseballsavant.mlb.com/leaderboard/pitch-movement"
                    f"?year={year}&team=&min=1&pitch_type={code}&sort=11&sortDir=desc&csv=true"
                )
                try:
                    text = fetch(url)
                except Exception as exc:
                    log(f"  board skip {year} {code}: {exc}")
                    continue
                if "pitcher_id" not in text.splitlines()[0]:
                    log(f"  board empty {year} {code}")
                    continue
                path.write_text(text)
                time.sleep(0.15)
            count = 0
            for row in csv.DictReader(io.StringIO(text)):
                pid = int(num(row.get("pitcher_id")) or 0)
                pitches = int(num(row.get("pitches_thrown")) or 0)
                ivb = num(row.get("pitcher_break_z_induced"))
                hb = num(row.get("pitcher_break_x"))
                if not pid or pitches < 1 or ivb is None or hb is None:
                    continue
                seasons[pid][year].append({
                    "type": code,
                    "code": code,
                    "velo": None if num(row.get("avg_speed")) is None else round(num(row.get("avg_speed")), 1),
                    "ivb": round(ivb, 2),
                    "hb_pitcher": round(hb, 2),
                    "hb_hitter": round(-hb, 2),
                    "pitches": pitches,
                    "level": "MLB",
                    "season": year,
                    "throws": (row.get("pitch_hand") or "").strip().upper()[:1] or None,
                })
                count += 1
            log(f"  MLB {year} {code} {count}")
    return seasons


def season_total(pitches: list[dict]) -> int:
    return sum(int(pitch.get("pitches") or 0) for pitch in pitches)


def choose_primary(seasons: dict[int, list[dict]]) -> tuple[int | None, str | None]:
    full = [year for year, pitches in seasons.items() if season_total(pitches) >= 200]
    if full:
        return max(full), "MLB"
    decent = [year for year, pitches in seasons.items() if season_total(pitches) >= 80]
    if decent:
        return max(decent), "MLB"
    return None, None


def shapes_from_seasons(seasons: dict[int, list[dict]], level: str) -> dict[str, dict]:
    """One shape per pitch. Newest full season first, then fill missing types."""
    chosen: dict[str, dict] = {}
    primary, _level = choose_primary(seasons) if level == "MLB" else (None, None)
    years = sorted(seasons, reverse=True)
    if primary is not None:
        years = [primary] + [year for year in years if year != primary]
    for year in years:
        total = season_total(seasons[year]) or 1
        for pitch in seasons[year]:
            code = pitch["type"]
            if int(pitch["pitches"]) < MIN_PITCHES:
                continue
            pitch = dict(pitch)
            pitch["usage"] = round(1000 * pitch["pitches"] / total) / 10
            pitch["movement_n"] = pitch["pitches"]
            pitch["movement_usage"] = pitch["usage"]
            pitch["movement_season"] = year
            pitch["movement_level"] = level
            have = chosen.get(code)
            if have is None:
                chosen[code] = pitch
            elif year == primary and have.get("movement_season") != primary:
                chosen[code] = pitch
    return chosen


def spring_csv(pid: int, year: int) -> str:
    path = SPRING_DIR / f"{pid}_{year}.csv"
    if path.is_file():
        return path.read_text()
    url = (
        "https://baseballsavant.mlb.com/statcast_search/csv?all=true&player_type=pitcher"
        f"&pitchers_lookup[]={pid}&hfGT=S|&hfSea={year}|&min_pitches=0&min_results=0"
        "&group_by=name&sort_col=pitches&player_event_sort=api_p_release_speed"
        "&sort_order=desc&min_pas=0&type=details"
        f"&game_date_gt={year}-02-01&game_date_lt={year}-04-15"
    )
    try:
        text = fetch(url, timeout=45)
    except Exception as exc:
        return f"error {exc}"
    SPRING_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def aggregate_spring(text: str, year: int) -> list[dict]:
    if "pitch_type" not in text[:400]:
        return []
    bags: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(text)):
        code = str(row.get("pitch_type") or "").strip().upper()
        pfx_x = num(row.get("pfx_x"))
        pfx_z = num(row.get("pfx_z"))
        if not code or pfx_x is None or pfx_z is None:
            continue
        bag = bags.setdefault(code, {"n": 0, "pfx_x": 0.0, "pfx_z": 0.0, "velo": 0.0, "velo_n": 0, "spin": 0.0, "spin_n": 0})
        bag["n"] += 1
        bag["pfx_x"] += pfx_x
        bag["pfx_z"] += pfx_z
        speed = num(row.get("release_speed"))
        spin = num(row.get("release_spin_rate"))
        if speed is not None:
            bag["velo"] += speed
            bag["velo_n"] += 1
        if spin is not None:
            bag["spin"] += spin
            bag["spin_n"] += 1
    pitches = []
    for code, bag in bags.items():
        if bag["n"] < MIN_PITCHES:
            continue
        hb = round(-(bag["pfx_x"] / bag["n"]) * 12.0, 2)
        pitches.append({
            "type": code,
            "code": code,
            "velo": round(bag["velo"] / bag["velo_n"], 1) if bag["velo_n"] else None,
            "spin": int(round(bag["spin"] / bag["spin_n"])) if bag["spin_n"] else None,
            "ivb": round((bag["pfx_z"] / bag["n"]) * 12.0, 2),
            "hb_pitcher": hb,
            "hb_hitter": round(-hb, 2),
            "pitches": bag["n"],
            "level": "MLB spring",
            "season": year,
        })
    return pitches


def download_spring(ids: list[int]) -> dict[int, dict[int, list[dict]]]:
    seasons: dict[int, dict[int, list[dict]]] = defaultdict(dict)
    jobs = [(pid, year) for pid in ids for year in SPRING_YEARS]
    log(f"spring lookups {len(jobs)}")

    def one(job):
        pid, year = job
        text = spring_csv(pid, year)
        return pid, year, aggregate_spring(text, year)

    done = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, job) for job in jobs]
        for future in as_completed(futures):
            pid, year, pitches = future.result()
            done += 1
            if pitches:
                seasons[pid][year] = pitches
            if done % 200 == 0:
                log(f"  spring {done}/{len(jobs)} pitchers-with-data {len(seasons)}")
    log(f"spring pitchers {len(seasons)}")
    return seasons


def stuff_shapes(cache: dict) -> dict[int, dict[str, dict]]:
    out = {}
    for key, pack in cache.items():
        shapes = {}
        total = sum(int(pitch.get("pitches") or 0) for pitch in pack.get("pitches") or []) or 1
        for pitch in pack.get("pitches") or []:
            if pitch.get("ivb") is None or pitch.get("hb_pitcher") is None:
                continue
            n = int(pitch.get("pitches") or 0)
            if n < MIN_PITCHES:
                continue
            code = str(pitch.get("type") or pitch.get("code") or "").upper()
            if not code:
                continue
            item = dict(pitch)
            item["movement_n"] = n
            item["movement_usage"] = pitch.get("usage") if pitch.get("usage") is not None else round(1000 * n / total) / 10
            item["movement_season"] = pack.get("season")
            item["movement_level"] = pack.get("level") or "Savant"
            shapes[code] = item
        if shapes:
            out[int(key)] = shapes
    return out


def merge_shapes(*layers: dict[str, dict]) -> dict[str, dict]:
    """Earlier layers win. Later layers only fill pitch types still missing."""
    chosen: dict[str, dict] = {}
    for layer in layers:
        for code, pitch in layer.items():
            if code not in chosen:
                chosen[code] = pitch
    return chosen


def apply_locked(career: dict[str, dict]) -> tuple[int, int]:
    handle = LOCK_PATH.open("a")
    fcntl.flock(handle, fcntl.LOCK_EX)
    try:
        arsenal = json.loads(ARSENAL.read_text())
        pitchers = 0
        pitches = 0
        for row in arsenal.get("pitchers") or []:
            pack = career.get(str(row.get("player_id")))
            if not pack or not pack.get("pitches"):
                continue
            by_code = {pitch["type"]: pitch for pitch in pack["pitches"]}
            rows = list(row.get("arsenal") or [])
            stamped = 0
            if rows:
                for pitch in rows:
                    code = str(pitch.get("code") or pitch.get("type") or "").upper()
                    src = by_code.get(code)
                    if not src:
                        continue
                    for key in ("ivb", "hb_pitcher", "hb_hitter", "movement_n", "movement_usage", "movement_season", "movement_level"):
                        if src.get(key) is not None:
                            pitch[key] = src[key]
                    if pitch.get("spin") in (None, 0) and src.get("spin"):
                        pitch["spin"] = src["spin"]
                    if pitch.get("velo") in (None, 0) and src.get("velo"):
                        pitch["velo"] = src["velo"]
                    pitch["code"] = pitch.get("code") or code
                    pitch["type"] = pitch.get("type") or code
                    stamped += 1
            else:
                rows = [dict(pitch) for pitch in pack["pitches"] if (pitch.get("movement_n") or 0) >= MIN_PITCHES]
                stamped = len(rows)
            if not stamped:
                continue
            row["arsenal"] = rows
            row["movement_source"] = pack.get("source")
            row["movement_season"] = pack.get("season")
            row["movement_level"] = pack.get("level")
            if not row.get("throws") and pack.get("throws"):
                row["throws"] = pack["throws"]
            pitchers += 1
            pitches += stamped
        save_json(ARSENAL, arsenal)
        cache = json.loads(SAVANT.read_text()) if SAVANT.is_file() else {}
        for key, pack in career.items():
            cache[key] = {
                "mlb_id": int(key),
                "level": pack.get("level"),
                "season": pack.get("season"),
                "source": pack.get("source"),
                "pitches": pack.get("pitches") or [],
            }
        save_json(SAVANT, cache)
        return pitchers, pitches
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def main() -> int:
    if os.environ.get("CAREER_APPLY_ONLY") == "1":
        career = json.loads(OUT.read_text())
        pitchers, pitches = apply_locked(career)
        log(f"stamped pitchers {pitchers} pitches {pitches}")
        return 0
    log("download MLB movement boards")
    mlb = download_boards()
    log(f"MLB pitchers on the board {len(mlb)}")
    roster = json.loads(ARSENAL.read_text()).get("pitchers") or []
    ids = [int(row["player_id"]) for row in roster if int(row.get("player_id") or 0) > 0]
    need_spring = []
    for pid in ids:
        seasons = mlb.get(pid) or {}
        shapes = shapes_from_seasons(seasons, "MLB") if seasons else {}
        if len(shapes) < 3:
            need_spring.append(pid)
    log(f"need spring or another source {len(need_spring)}")
    spring = download_spring(need_spring)
    stuff = stuff_shapes(json.loads(SAVANT.read_text()) if SAVANT.is_file() else {})
    career = {}
    for row in roster:
        pid = int(row.get("player_id") or 0)
        if pid <= 0:
            continue
        mlb_shapes = shapes_from_seasons(mlb.get(pid) or {}, "MLB")
        spring_shapes = {}
        for year in sorted(spring.get(pid) or {}, reverse=True):
            total = season_total(spring[pid][year]) or 1
            for pitch in spring[pid][year]:
                if pitch["type"] in spring_shapes:
                    continue
                item = dict(pitch)
                item["usage"] = round(1000 * pitch["pitches"] / total) / 10
                item["movement_n"] = pitch["pitches"]
                item["movement_usage"] = item["usage"]
                item["movement_season"] = year
                item["movement_level"] = "MLB spring"
                spring_shapes[pitch["type"]] = item
        merged = merge_shapes(mlb_shapes, spring_shapes, stuff.get(pid) or {})
        if not merged:
            continue
        primary_year = None
        primary_level = None
        seasons = mlb.get(pid) or {}
        primary_year, primary_level = choose_primary(seasons)
        if primary_year is None and spring.get(pid):
            primary_year = max(spring[pid])
            primary_level = "MLB spring"
        if primary_year is None:
            sample = next(iter(merged.values()))
            primary_year = sample.get("movement_season")
            primary_level = sample.get("movement_level")
        throws = next((pitch.get("throws") for year in seasons.values() for pitch in year if pitch.get("throws")), None)
        career[str(pid)] = {
            "mlb_id": pid,
            "season": primary_year,
            "level": primary_level,
            "source": f"{primary_level} {primary_year} movement",
            "throws": throws,
            "pitches": list(merged.values()),
        }
    save_json(OUT, career)
    log(f"career packs {len(career)}")
    if os.environ.get("CAREER_APPLY", "1") != "1":
        log("saved packs, apply skipped")
        return 0
    pitchers, pitches = apply_locked(career)
    log(f"stamped pitchers {pitchers} pitches {pitches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
