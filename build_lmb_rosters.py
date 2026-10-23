#!/usr/bin/env python3
"""Build Dorados site data from the 2026 Mexican League season files.

Reads data/mexico_2026_hitting.json and data/mexico_2026_pitching.json
(MLB Stats API season lines). Writes roster, strategy-card, and advance
files. Does not invent pitch mix, plate location, bats, or throws.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SRC_H = DATA / "mexico_2026_hitting.json"
SRC_P = DATA / "mexico_2026_pitching.json"

# Dark enough for white type on the strategy card header.
TEAM_COLORS = {
    "CHI": "#6E1E2A",
    "MTY": "#0B3A6A",
    "DUR": "#8E2A2A",
    "JAL": "#3E2A1A",
    "QRO": "#4A1C6B",
    "MEX": "#9B1830",
    "VER": "#0E5A32",
    "OAX": "#8A3B12",
    "YUC": "#8A7010",
    "TAB": "#145C45",
    "PUE": "#1E6B48",
    "CAM": "#1C2833",
    "AGS": "#7A1A38",
    "SLW": "#6E2430",
    "LAR": "#0E4D2C",
    "TIG": "#8A4B00",
    "TIJ": "#7A1020",
    "MVA": "#2E3A48",
    "LAG": "#6E5410",
    "LEO": "#7A2424",
}


def num(v):
    if v is None or v == "" or v in (".---", "-.--"):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").strip()
    if s.startswith("."):
        s = "0" + s
    try:
        return float(s)
    except ValueError:
        return None


def pct(part, whole):
    if part is None or not whole:
        return None
    return round(1000 * part / whole) / 10


def ip_outs(ip) -> int:
    if ip is None:
        return 0
    s = str(ip).strip()
    if not s or s in (".---", "-.--"):
        return 0
    if "." in s:
        whole, frac = s.split(".", 1)
        return int(whole or 0) * 3 + int((frac[:1] or "0"))
    return int(float(s)) * 3


def per9(n, outs):
    if not outs or n is None:
        return None
    return round(n * 27 / outs, 1)


def last_name(full: str) -> str:
    parts = [p for p in re.split(r"\s+", (full or "").strip()) if p]
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    while parts and parts[-1].lower().rstrip(".") in suffixes:
        parts.pop()
    if not parts:
        return ""
    particles = {"de", "del", "la", "los", "las", "da", "dos", "van", "von"}
    raw = parts[-1]
    if len(parts) >= 2 and parts[-2].lower() in particles:
        raw = parts[-2] + " " + parts[-1]
    if len(parts) >= 3 and parts[-3].lower() in particles and parts[-2].lower() in particles:
        raw = " ".join(parts[-3:])
    nk = unicodedata.normalize("NFKD", raw)
    nk = "".join(c for c in nk if not unicodedata.combining(c))
    return nk.upper()


def teams_from(rows):
    found = {}
    for row in rows:
        ab = row.get("teamAbbrev")
        if not ab:
            continue
        found[ab] = {
            "id": int(row["teamId"]),
            "abbrev": ab,
            "name": row.get("teamName") or ab,
            "short": row.get("teamShortName") or ab,
        }
    ordered = sorted(found.values(), key=lambda t: (t["abbrev"] != "CHI", t["name"]))
    out = []
    for t in ordered:
        item = {
            "id": t["id"],
            "abbrev": t["abbrev"],
            "name": t["name"],
            "color": TEAM_COLORS.get(t["abbrev"], "#1C2833"),
            "logo": "assets/dorados-logo.svg" if t["abbrev"] == "CHI" else None,
        }
        out.append(item)
    return out


def hitter_line(row, team_name):
    pa = num(row.get("plateAppearances")) or 0
    so = num(row.get("strikeOuts")) or 0
    swings = num(row.get("totalSwings")) or 0
    whiffs = num(row.get("swingAndMisses")) or 0
    go = (num(row.get("groundOuts")) or 0) + (num(row.get("groundHits")) or 0)
    bip = num(row.get("ballsInPlay")) or 0
    sb = int(num(row.get("stolenBases")) or 0)
    cs = int(num(row.get("caughtStealing")) or 0)
    sac = int(num(row.get("sacBunts")) or 0)
    return {
        "pa": int(pa),
        "ab": int(num(row.get("atBats")) or 0),
        "k": pct(so, pa),
        "gb": pct(go, bip),
        "wh": pct(whiffs, swings),
        "avg": num(row.get("avg")),
        "ops": num(row.get("ops")),
        "src": "LMB 2026",
        "summer_sb": sb,
        "summer_cs": cs,
        "summer_sac": sac,
        "summer_levels": [{"league": "LMB", "sb": sb, "cs": cs, "sac": sac}],
        "summer_line": {
            "team": row.get("teamAbbrev"),
            "team_name": team_name,
            "season": "Summer 2026",
            "league": "LMB",
            "league_name": "Mexican League",
            "level": "LMB",
            "pa": int(pa),
            "ab": int(num(row.get("atBats")) or 0),
            "r": int(num(row.get("runs")) or 0),
            "h": int(num(row.get("hits")) or 0),
            "doubles": int(num(row.get("doubles")) or 0),
            "triples": int(num(row.get("triples")) or 0),
            "hr": int(num(row.get("homeRuns")) or 0),
            "rbi": int(num(row.get("rbi")) or 0),
            "sb": sb,
            "cs": cs,
            "bb": int(num(row.get("baseOnBalls")) or 0),
            "so": int(so),
            "ba": num(row.get("avg")),
            "obp": num(row.get("obp")),
            "slg": num(row.get("slg")),
            "ops": num(row.get("ops")),
            "source": "MLB Stats API 2026 Mexican League",
        },
        "overall": {
            "pa": int(pa),
            "ab": int(num(row.get("atBats")) or 0),
            "h": int(num(row.get("hits")) or 0),
            "games": int(num(row.get("gamesPlayed")) or 0),
            "swings": int(swings),
            "whiffs": int(whiffs),
            "ops": num(row.get("ops")),
            "whiff_pct": pct(whiffs, swings),
        },
    }


def pitcher_line(row, team_name):
    bf = num(row.get("battersFaced")) or 0
    so = num(row.get("strikeOuts")) or 0
    bb = num(row.get("baseOnBalls")) or 0
    go = num(row.get("groundOuts")) or 0
    ao = num(row.get("airOuts")) or 0
    outs = ip_outs(row.get("inningsPitched"))
    ip = row.get("inningsPitched")
    return {
        "bf": int(bf),
        "k": pct(so, bf),
        "gb": pct(go, go + ao),
        "bb": pct(bb, bf),
        "ops": num(row.get("ops")),
        "avg": num(row.get("avg")),
        "wh": None if num(row.get("whiffPercentage")) is None else round(num(row.get("whiffPercentage")) * 1000) / 10,
        "gs": int(num(row.get("gamesStarted")) or 0),
        "src": "LMB 2026",
        "summer_line": {
            "team": row.get("teamAbbrev"),
            "team_name": team_name,
            "season": "Summer 2026",
            "league": "LMB",
            "league_name": "Mexican League",
            "level": "LMB",
            "ip": ip,
            "g": int(num(row.get("gamesPitched")) or num(row.get("gamesPlayed")) or 0),
            "gs": int(num(row.get("gamesStarted")) or 0),
            "k": int(so),
            "bb": int(bb),
            "k9": per9(so, outs),
            "bb9": per9(bb, outs),
            "era": num(row.get("era")),
            "whip": num(row.get("whip")),
            "h": int(num(row.get("hits")) or 0),
            "hr": int(num(row.get("homeRuns")) or 0),
            "sb_allowed": int(num(row.get("stolenBases")) or 0),
            "cs_allowed": int(num(row.get("caughtStealing")) or 0),
            "source": "MLB Stats API 2026 Mexican League. FIP is not in this feed.",
        },
    }


def main():
    hitters = json.loads(SRC_H.read_text())
    pitchers = json.loads(SRC_P.read_text())
    teams = teams_from(hitters + pitchers)
    names = {t["abbrev"]: t["name"] for t in teams}

    hit_by = {int(r["playerId"]): r for r in hitters}
    pit_by = {int(r["playerId"]): r for r in pitchers}
    ids = sorted(set(hit_by) | set(pit_by))

    players = []
    advance_hitters = []
    arsenal_pitchers = []
    rosters = {str(t["id"]): {"teamName": t["name"], "players": []} for t in teams}
    id_to_abbrev = {t["id"]: t["abbrev"] for t in teams}

    for pid in ids:
        h = hit_by.get(pid)
        p = pit_by.get(pid)
        pa = num(h.get("plateAppearances")) if h else 0
        bf = num(p.get("battersFaced")) if p else 0
        role = "P" if p and (not h or (bf or 0) >= (pa or 0)) else "H"
        src = p if role == "P" else h
        name = src.get("playerFullName") or src.get("playerName")
        abbrev = src.get("teamAbbrev")
        team_name = names.get(abbrev, src.get("teamName") or abbrev)
        pos = "P" if role == "P" else (src.get("positionAbbrev") or src.get("primaryPositionAbbrev") or "")
        if role == "H":
            pack = hitter_line(h, team_name)
            hitter = {k: pack[k] for k in ("pa", "ab", "k", "gb", "wh", "avg", "ops", "src", "summer_sb", "summer_cs", "summer_sac", "summer_levels")}
            pitcher = None
            advance_hitters.append({
                "mlb_id": pid,
                "name": name,
                "team": abbrev,
                "bats": None,
                "overall": pack["overall"],
                "summer_line": pack["summer_line"],
                "summer_sb": pack["summer_sb"],
                "summer_cs": pack["summer_cs"],
                "summer_sac": pack["summer_sac"],
            })
        else:
            pack = pitcher_line(p, team_name)
            hitter = None
            pitcher = {k: pack[k] for k in ("bf", "k", "gb", "bb", "ops", "avg", "wh", "gs", "src")}
            arsenal_pitchers.append({
                "player_id": pid,
                "name": name,
                "team": abbrev,
                "throws": None,
                "arsenal": [],
                "summer_line": pack["summer_line"],
            })
        players.append({
            "id": pid,
            "name": name,
            "last": last_name(name),
            "team": abbrev,
            "roster_pos": pos,
            "role": role,
            "bats": None,
            "throws": None,
            "hitter": hitter,
            "pitcher": pitcher,
        })
        rid = str(src.get("teamId"))
        if rid in rosters:
            rosters[rid]["players"].append({"name": name, "position": pos, "jersey": ""})

    for bucket in rosters.values():
        bucket["players"].sort(key=lambda r: (r["position"] == "P", r["name"]))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    card = {
        "generated": now,
        "teams": [{"abbrev": t["abbrev"], "name": t["name"], "color": t["color"], "logo": t["logo"]} for t in teams],
        "players": players,
        "gaps": {
            "roster_source": "MLB Stats API 2026 Mexican League season. Players who did not appear are not in the feed.",
            "bats_throws": "The season feed has no bats or throws, so those stay blank.",
            "pitch_mix": "No pitch-type mix, velocity, or plate location in this feed. Usage charts and heat maps stay empty.",
            "platoon": "No vs-L / vs-R split. Both hands repeat the 2026 season line.",
            "two_way": "A player in both files is a pitcher when batters faced are at least his plate appearances.",
            "hitters": sum(1 for p in players if p["role"] == "H"),
            "pitchers": sum(1 for p in players if p["role"] == "P"),
        },
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "lmb_2026_rosters.json").write_text(json.dumps(rosters, ensure_ascii=False))
    (DATA / "pregame_card_stats.json").write_text(json.dumps(card, ensure_ascii=False, separators=(",", ":")))
    (DATA / "advance_opposing_hitters.json").write_text(json.dumps({
        "season": "2026",
        "league": "LMB",
        "hitters": advance_hitters,
    }, ensure_ascii=False, separators=(",", ":")))
    (DATA / "pregame_pitcher_arsenals.json").write_text(json.dumps({
        "season": "2026",
        "league": "LMB",
        "pitchers": arsenal_pitchers,
    }, ensure_ascii=False, separators=(",", ":")))
    (DATA / "lmb_teams.json").write_text(json.dumps(teams, ensure_ascii=False, indent=2))
    js = "window.LMB_TEAMS = " + json.dumps(teams, ensure_ascii=False) + ";\n"
    (ROOT / "lmb_teams.js").write_text(js)
    stubs = {
        "pregame_lineup_spots.json": [],
        "pregame_pitcher_vs_batter.json": [],
        "pregame_hitter_vs_pitcher.json": [],
        "pregame_baserunning_bunting.json": [],
        "pregame_spray_charts.json": {},
        "fps_cache.json": {},
        "advance_opposing_pitchers.json": {"pitchers": []},
        "advance_heatmaps.json": {"hitters": {}, "pitchers": {}},
        "pregame_tth_pop.json": {"players": [], "teams": []},
        "free_agent_pool.json": {
            "season": 2026,
            "pitchers": [],
            "hitters": [],
            "excluded_birth_countries": [],
            "generated": now,
        },
    }
    for name, payload in stubs.items():
        (DATA / name).write_text(json.dumps(payload))
    print(f"teams={len(teams)} players={len(players)} hitters={card['gaps']['hitters']} pitchers={card['gaps']['pitchers']}")
    print("home", next(t["name"] for t in teams if t["abbrev"] == "CHI"), "id", next(t["id"] for t in teams if t["abbrev"] == "CHI"))


if __name__ == "__main__":
    main()
