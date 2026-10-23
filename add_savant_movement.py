#!/usr/bin/env python3
"""Attach Prospect Savant IVB/HB for LMB pitchers who pitched MLB or AAA.

Numbers come from the Prospect Savant stuff feed (Statcast pfx_x / pfx_z).
Nothing is invented. A pitcher with no tracked MLB/AAA season is left unchanged.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARSENAL = DATA / "pregame_pitcher_arsenals.json"
OUT = DATA / "savant_movement.json"
PS = "https://oriolebird.pythonanywhere.com/stuff"
UA = {"User-Agent": "DoradosLMB/1.0"}
YEARS = (2026, 2025, 2024, 2023, 2022)
SPORTS = ((1, "MLB"), (11, "AAA"))


def get_json(url: str, timeout: float = 25) -> dict | list:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


def num(value):
    if value in (None, "", ".---", "-.--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pack_rows(rows: list, season: int, level: str) -> list[dict]:
    pitches = []
    for row in rows:
        code = str(row.get("pitch_type") or "").strip().upper()
        pfx_x = num(row.get("pfx_x"))
        pfx_z = num(row.get("pfx_z"))
        if not code or pfx_x is None or pfx_z is None:
            continue
        ivb = round(pfx_z * 12.0, 2)
        hb_pitcher = round(-(pfx_x * 12.0), 2)
        pitches.append({
            "type": code,
            "code": code,
            "name": row.get("pitch_name") or code,
            "velo": None if num(row.get("release_speed")) is None else round(num(row.get("release_speed")), 1),
            "spin": None if num(row.get("release_spin_rate")) is None else int(round(num(row.get("release_spin_rate")))),
            "ivb": ivb,
            "hb_pitcher": hb_pitcher,
            "hb_hitter": round(pfx_x * 12.0, 2),
            "usage": None if num(row.get("usage")) is None else round(num(row.get("usage")), 1),
            "pitches": int(num(row.get("pitches")) or 0),
            "ps_stuff": None if num(row.get("psStuff")) is None else round(num(row.get("psStuff")), 1),
            "whiff": num(row.get("swing_miss_percent")),
            "level": level,
            "season": season,
        })
    pitches.sort(key=lambda pitch: -(pitch.get("pitches") or 0))
    return pitches


def appeared_bulk(ids: list[int]) -> dict[int, str]:
    """Map mlb id → MLB or AAA when that pitcher has a 2022–2026 season there."""
    qualified: dict[int, str] = {}
    clean = sorted({int(value) for value in ids if int(value) > 0})
    for year in YEARS:
        for sport_id, label in SPORTS:
            for start in range(0, len(clean), 40):
                chunk = clean[start:start + 40]
                hydrate = f"stats(group=[pitching],type=[season],season={year},sportId={sport_id})"
                url = (
                    "https://statsapi.mlb.com/api/v1/people?personIds="
                    + ",".join(str(value) for value in chunk)
                    + "&hydrate=" + hydrate
                )
                try:
                    payload = get_json(url, timeout=40)
                except Exception as exc:
                    print(f"  roster fail {year} {label}: {exc}", flush=True)
                    continue
                for person in payload.get("people") or []:
                    pid = int(person.get("id") or 0)
                    if not pid or qualified.get(pid) == "MLB":
                        continue
                    for stat in person.get("stats") or []:
                        for split in stat.get("splits") or []:
                            ip = (split.get("stat") or {}).get("inningsPitched")
                            games = (split.get("stat") or {}).get("gamesPitched")
                            if ip not in (None, "", "0.0", "0") or (games and int(games) > 0):
                                if label == "MLB" or pid not in qualified:
                                    qualified[pid] = label
                                break
                time.sleep(0.05)
        print(f"  after {year}: {len(qualified)} MLB/AAA arms", flush=True)
    return qualified


def fetch_movement(pid: int, level: str) -> dict | None:
    for season in YEARS:
        url = f"{PS}/{pid}/{season}"
        try:
            rows = get_json(url, timeout=20)
        except urllib.error.HTTPError:
            continue
        except Exception as exc:
            print(f"  savant fail {pid} {season}: {exc}", flush=True)
            time.sleep(0.2)
            continue
        pitches = pack_rows(rows, season, level) if isinstance(rows, list) else []
        if pitches:
            return {
                "mlb_id": pid,
                "level": level,
                "season": season,
                "source": f"Prospect Savant {season} {level}",
                "pitches": pitches,
            }
        time.sleep(0.05)
    return None


def apply_to_row(row: dict, pack: dict) -> bool:
    """Copy real IVB/HB onto matching pitch types. Add a Savant row when Synergy has none."""
    incoming = {pitch["type"]: pitch for pitch in pack.get("pitches") or []}
    if not incoming:
        return False
    arsenal = list(row.get("arsenal") or [])
    seen = set()
    changed = False
    for pitch in arsenal:
        code = str(pitch.get("code") or pitch.get("type") or "").upper()
        src = incoming.get(code)
        if not src:
            continue
        seen.add(code)
        for key in ("ivb", "hb_pitcher", "hb_hitter", "spin", "ps_stuff"):
            if src.get(key) is not None:
                pitch[key] = src[key]
        if pitch.get("velo") in (None, 0) and src.get("velo"):
            pitch["velo"] = src["velo"]
        pitch["code"] = pitch.get("code") or code
        pitch["type"] = pitch.get("type") or code
        changed = True
    for code, src in incoming.items():
        if code in seen:
            continue
        if arsenal and (src.get("usage") or 0) < 3 and (src.get("pitches") or 0) < 20:
            continue
        arsenal.append(dict(src))
        changed = True
    if not changed:
        return False
    row["arsenal"] = arsenal
    row["movement_source"] = pack.get("source")
    row["ps_season"] = pack.get("season")
    row["ps_source"] = "Prospect Savant"
    return True


def backfill_older() -> int:
    """Attach 2019–2021 MLB/AAA break for arms the 2022–2026 pass left empty.

    Writes the movement cache only. The Synergy filler copies it onto arsenals.
    """
    older = (2021, 2020, 2019)
    arsenal = json.loads(ARSENAL.read_text())
    pitchers = arsenal.get("pitchers") or []
    cache = json.loads(OUT.read_text()) if OUT.is_file() else {}
    need = []
    for row in pitchers:
        pid = int(row.get("player_id") or 0)
        if pid <= 0:
            continue
        cached = cache.get(str(pid)) or {}
        if cached.get("pitches"):
            continue
        need.append(pid)
    print(f"older-season check {len(need)}", flush=True)
    qualified: dict[int, str] = {}
    for year in older:
        for sport_id, label in SPORTS:
            for start in range(0, len(need), 40):
                chunk = need[start:start + 40]
                hydrate = f"stats(group=[pitching],type=[season],season={year},sportId={sport_id})"
                url = (
                    "https://statsapi.mlb.com/api/v1/people?personIds="
                    + ",".join(str(value) for value in chunk)
                    + "&hydrate=" + hydrate
                )
                try:
                    payload = get_json(url, timeout=40)
                except Exception as exc:
                    print(f"  roster fail {year} {label}: {exc}", flush=True)
                    continue
                for person in payload.get("people") or []:
                    pid = int(person.get("id") or 0)
                    if not pid or qualified.get(pid) == "MLB":
                        continue
                    for stat in person.get("stats") or []:
                        for split in stat.get("splits") or []:
                            ip = (split.get("stat") or {}).get("inningsPitched")
                            games = (split.get("stat") or {}).get("gamesPitched")
                            if ip not in (None, "", "0.0", "0") or (games and int(games) > 0):
                                if label == "MLB" or pid not in qualified:
                                    qualified[pid] = label
                                break
                time.sleep(0.05)
        print(f"  after {year}: {len(qualified)} extra MLB/AAA arms", flush=True)
    saved_years = YEARS
    filled = 0
    try:
        globals()["YEARS"] = older
        for index, pid in enumerate(sorted(qualified), 1):
            level = qualified[pid]
            print(f"[{index}/{len(qualified)}] {pid} {level}", flush=True)
            pack = fetch_movement(pid, level)
            if pack and pack.get("pitches"):
                cache[str(pid)] = pack
                filled += 1
            elif str(pid) not in cache:
                cache[str(pid)] = {"mlb_id": pid, "level": level, "pitches": []}
            if index % 10 == 0:
                tmp = OUT.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(cache, ensure_ascii=False))
                tmp.replace(OUT)
            time.sleep(0.05)
    finally:
        globals()["YEARS"] = saved_years
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False))
    tmp.replace(OUT)
    print(f"older movement rows {filled}", flush=True)
    return 0


def main() -> int:
    arsenal = json.loads(ARSENAL.read_text())
    pitchers = arsenal.get("pitchers") or []
    ids = [int(row["player_id"]) for row in pitchers if int(row.get("player_id") or 0) > 0]
    print(f"pitchers {len(ids)}", flush=True)
    qualified = appeared_bulk(ids)
    print(f"qualified {len(qualified)}", flush=True)
    cache = json.loads(OUT.read_text()) if OUT.is_file() else {}
    filled = 0
    for index, row in enumerate(pitchers, 1):
        pid = int(row.get("player_id") or 0)
        level = qualified.get(pid)
        if not level:
            continue
        cached = cache.get(str(pid))
        if not cached:
            print(f"[{index}/{len(pitchers)}] {row.get('team')} {row.get('name')} {level}", flush=True)
            cached = fetch_movement(pid, level)
            cache[str(pid)] = cached or {"mlb_id": pid, "level": level, "pitches": []}
            if index % 15 == 0:
                OUT.write_text(json.dumps(cache, ensure_ascii=False))
        if cached and cached.get("pitches") and apply_to_row(row, cached):
            filled += 1
    OUT.write_text(json.dumps(cache, ensure_ascii=False))
    ARSENAL.write_text(json.dumps(arsenal, ensure_ascii=False, separators=(",", ":")))
    print(f"movement rows {filled}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
