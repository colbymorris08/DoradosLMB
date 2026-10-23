#!/usr/bin/env python3
"""Fill Dorados advance charts from real Synergy pitches, and copy PR release photos.

Does not invent IVB/HB. Movement numbers are copied only when a Puerto Rico
packet already has them. Release photos are copied only for name matches in
~/Downloads/LBPRC SANTURCE ADVANCE PITCHER RELEASE PICTURES.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SANTURCE = Path("/Users/colbymorris/Santurce2026")
PICS = Path.home() / "Downloads" / "LBPRC SANTURCE ADVANCE PITCHER RELEASE PICTURES"
ASSETS = ROOT / "assets" / "advance"
DATA = ROOT / "data"
CKPT = ROOT / "runs" / "lmb_synergy_checkpoint.json"
LOCK_PATH = ROOT / "runs" / "lmb_synergy.lock"
USE_LEAGUE_FILTER = False
sys.path.insert(0, str(SANTURCE))

import build_advance_synergy as bas  # noqa: E402
from refresh_roster_synergy import Synergy  # noqa: E402

LEAGUE_LMB = bas.LEAGUE_LMB
MAX_SCAN = int(os.environ.get("LMB_SYN_MAX_SCAN", "2200"))
MAX_KEEP = int(os.environ.get("LMB_SYN_MAX_KEEP", "1400"))


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s.lower())


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s or "player"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def file_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("a")
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def unlock(handle) -> None:
    fcntl.flock(handle, fcntl.LOCK_UN)
    handle.close()


def is_lmb(ev: dict) -> bool:
    game = ev.get("game") or {}
    league = game.get("league") or {}
    if str(league.get("id") or "") == LEAGUE_LMB:
        return True
    ab = str(league.get("nameAbbrev") or league.get("name") or "").upper()
    return ab in {"LMB", "MEX", "LM"} or "MEXICAN LEAGUE" in ab


def date_year(ev: dict) -> int | None:
    raw = str((ev.get("game") or {}).get("gameDate") or "")
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw) or re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if not m:
        return None
    groups = [int(x) for x in m.groups()]
    return groups[2] if len(groups) == 3 and groups[2] > 1900 else groups[0]


def pctile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round((p / 100) * (len(xs) - 1)))))
    return round(xs[i], 1)


def copy_release_pics(by_id: dict[int, dict]) -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    by_name = {norm(p["name"]): p for p in by_id.values() if p["role"] == "P"}
    n = 0
    if not PICS.is_dir():
        return 0
    for folder in PICS.glob("*/*"):
        if not folder.is_dir():
            continue
        player = by_name.get(norm(folder.name))
        if not player:
            continue
        row = player["arsenal"]
        stem = f"{slug(player['name'])}_{player['id']}"
        for kind, field in (("delivery.jpg", "arm_slot_image"), ("movement.jpg", "arsenal_image")):
            src = folder / kind
            if not src.is_file():
                continue
            dest_name = f"{stem}_{'delivery' if kind.startswith('delivery') else 'movement'}.jpg"
            shutil.copy2(src, ASSETS / dest_name)
            row[field] = f"assets/advance/{dest_name}"
            n += 1
    return n


def seed_from_santurce(by_id: dict[int, dict]) -> dict[str, int]:
    """Copy real Puerto Rico packets onto the matching LMB player. Keeps the LMB team and season line."""
    counts = {"pitchers": 0, "hitters": 0, "heat": 0}
    ars = load_json(SANTURCE / "data" / "pregame_pitcher_arsenals.json")
    by_name_p: dict[str, dict] = {}
    for row in ars.get("pitchers") or []:
        if row.get("arsenal"):
            by_name_p.setdefault(norm(row.get("name")), row)
    hits = load_json(SANTURCE / "data" / "advance_opposing_hitters.json")
    by_name_h: dict[str, dict] = {}
    for row in hits.get("hitters") or []:
        if (row.get("overall") or {}).get("pitches") or row.get("spray_points"):
            by_name_h.setdefault(norm(row.get("name")), row)
    heat = load_json(SANTURCE / "data" / "advance_heatmaps.json")
    heat_by_name = {}
    for bag in (heat.get("pitchers") or {}, heat.get("hitters") or {}):
        for rec in bag.values():
            if rec and rec.get("name") and int(rec.get("located") or 0) > 0:
                heat_by_name.setdefault(norm(rec["name"]), rec)

    split_keys = [
        "overall", "by_pitch_type", "risp_by_pitch_type", "vs_r_by_pitch_type", "vs_l_by_pitch_type",
        "risp_vs_r_by_pitch_type", "risp_vs_l_by_pitch_type", "non_risp_vs_r_by_pitch_type",
        "non_risp_vs_l_by_pitch_type", "pre2k_vs_r_by_pitch_type", "pre2k_vs_l_by_pitch_type",
        "twok_vs_r_by_pitch_type", "twok_vs_l_by_pitch_type", "spray_points", "spray_splits",
        "synergy_id", "bats",
    ]
    for player in by_id.values():
        src = by_name_p.get(norm(player["name"])) if player["role"] == "P" else by_name_h.get(norm(player["name"]))
        if player["role"] == "P" and src:
            row = player["arsenal"]
            pitches = []
            for a in src.get("arsenal") or []:
                item = dict(a)
                item["code"] = item.get("code") or item.get("type")
                pitches.append(item)
            if pitches:
                row["arsenal"] = pitches
                for key in ("count_mix", "platoon", "count_hand_mix", "usage_by_count", "synergy_id", "throws"):
                    if src.get(key):
                        row[key] = src[key]
                row["synergy_source"] = "Puerto Rico advance packet"
                counts["pitchers"] += 1
        elif player["role"] == "H" and src:
            row = player["hitter"]
            for key in split_keys:
                if src.get(key) not in (None, [], {}):
                    row[key] = src[key]
            row["synergy_source"] = "Puerto Rico advance packet"
            counts["hitters"] += 1
        rec = heat_by_name.get(norm(player["name"]))
        if rec:
            copied = dict(rec)
            copied["team"] = player["team"]
            copied["mlb_id"] = player["id"]
            player["heat"] = copied
            counts["heat"] += 1
    return counts


def compact(ev: dict) -> dict:
    pitch = ev.get("pitch") or {}
    contact = ev.get("contact") or {}
    batter = ev.get("batter") or {}
    pitcher = ev.get("pitcher") or {}
    if not pitcher.get("id"):
        pitcher = (((ev.get("defense") or {}).get("lineup") or {}).get("pitcher")) or {}
    game = ev.get("game") or {}
    league = game.get("league") or {}
    return {
        "eventType": ev.get("eventType") or "Pitch",
        "inning": ev.get("inning"),
        "inningTop": ev.get("inningTop"),
        "inningPlateAppearanceNumber": ev.get("inningPlateAppearanceNumber"),
        "plateAppearanceResult": ev.get("plateAppearanceResult"),
        "count": ev.get("count") or {},
        "pitcherInfo": ev.get("pitcherInfo") or {},
        "batterInfo": ev.get("batterInfo") or {},
        "runners": ev.get("runners") or {},
        "batter": {"id": batter.get("id"), "nameFirst": batter.get("nameFirst"), "nameLast": batter.get("nameLast")},
        "pitcher": {"id": pitcher.get("id"), "nameFirst": pitcher.get("nameFirst") or pitcher.get("firstName"), "nameLast": pitcher.get("nameLast") or pitcher.get("lastName")},
        "defense": {"lineup": {"pitcher": {"id": pitcher.get("id"), "nameFirst": pitcher.get("nameFirst") or pitcher.get("firstName"), "nameLast": pitcher.get("nameLast") or pitcher.get("lastName")}}},
        "game": {
            "id": game.get("id"),
            "gameDate": game.get("gameDate"),
            "season": game.get("season"),
            "league": {"id": league.get("id"), "nameAbbrev": league.get("nameAbbrev")},
        },
        "pitch": {
            "px": pitch.get("px"),
            "pz": pitch.get("pz"),
            "pitchResult": pitch.get("pitchResult"),
            "pitchKind": pitch.get("pitchKind"),
            "pitchSpeedMph": pitch.get("pitchSpeedMph"),
            "strikeZoneInchesBottom": pitch.get("strikeZoneInchesBottom"),
            "strikeZoneInchesTop": pitch.get("strikeZoneInchesTop"),
        },
        "contact": {
            "landingLocationX": contact.get("landingLocationX"),
            "landingLocationY": contact.get("landingLocationY"),
            "fieldZone": contact.get("fieldZone"),
            "contactType": contact.get("contactType"),
        },
    }


def fetch_lmb(token: str, *, sid: str, pitcher: bool) -> tuple[list[dict], int, str]:
    kept: list[dict] = []
    skip = 0
    scanned = 0
    while scanned < MAX_SCAN and len(kept) < MAX_KEEP:
        body = {
            "loggingPhases": [bas.LOGGING_PHASE_PITCH],
            "skip": skip,
            "take": 200,
            "pitcherId" if pitcher else "batterId": sid,
        }
        if USE_LEAGUE_FILTER:
            body["leagueIds"] = [LEAGUE_LMB]
        try:
            doc = bas.api_post(bas.EVENTS_FILTER_URL, token, body, timeout_s=90)
        except Exception as exc:  # noqa: BLE001
            if "401" in str(exc):
                raise
            log(f"  events stop skip={skip}: {exc}")
            break
        rows = doc.get("result") if isinstance(doc, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        years = [y for y in (date_year(ev) for ev in rows) if y]
        if years and max(years) < 2026:
            break
        for ev in rows:
            if is_lmb(ev):
                kept.append(compact(ev))
        scanned += len(rows)
        skip += len(rows)
        total = int(doc.get("totalRecords") or 0)
        if total and skip >= total:
            break
    return kept, scanned, token


def hand_letter(raw: Any) -> str | None:
    s = str(raw or "").strip().upper()
    if s.startswith("L"):
        return "L"
    if s.startswith("R"):
        return "R"
    return None


def arsenal_from_events(events: list[dict], sid: str, previous: list[dict]) -> dict[str, Any]:
    packed = bas.aggregate_pitcher_count_mixes(events)
    mix = packed.get(sid) or (next(iter(packed.values())) if packed else None)
    if not mix:
        return {}
    speeds: dict[str, list[float]] = defaultdict(list)
    whiff: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    throws = None
    for ev in events:
        pitch = ev.get("pitch") or {}
        code = bas._pitch_code(pitch.get("pitchKind"))
        if not code or code in bas._CHART_SKIP_CODES:
            continue
        spd = pitch.get("pitchSpeedMph")
        try:
            if spd is not None:
                speeds[code].append(float(spd))
        except (TypeError, ValueError):
            pass
        result = pitch.get("pitchResult")
        if bas._is_swing(result):
            whiff[code][0] += 1
            if bas._is_whiff(result):
                whiff[code][1] += 1
        throws = throws or hand_letter((ev.get("pitcherInfo") or {}).get("pitchingSide"))
    old = {str(a.get("code") or a.get("type")): a for a in previous}
    lmap = {r["type"]: r for r in (mix.get("platoon") or {}).get("vs_LHB") or []}
    rmap = {r["type"]: r for r in (mix.get("platoon") or {}).get("vs_RHB") or []}
    arsenal = []
    for row in (mix.get("count_mix") or {}).get("overall") or []:
        code = row["type"]
        prev = old.get(code) or {}
        swings, misses = whiff[code]
        xs = speeds[code]
        arsenal.append({
            "type": code,
            "code": code,
            "name": code,
            "usage": row["usage"],
            "pitches": row["pitches"],
            "velo": round(sum(xs) / len(xs), 1) if xs else prev.get("velo"),
            "velo_p25": pctile(xs, 25) if xs else prev.get("velo_p25"),
            "velo_p75": pctile(xs, 75) if xs else prev.get("velo_p75"),
            "velo_p90": pctile(xs, 90) if xs else prev.get("velo_p90"),
            "velo_n": len(xs) or prev.get("velo_n"),
            "spin": prev.get("spin"),
            "ivb": prev.get("ivb"),
            "hb_pitcher": prev.get("hb_pitcher"),
            "hb_hitter": prev.get("hb_hitter"),
            "movement_n": prev.get("movement_n"),
            "movement_usage": prev.get("movement_usage"),
            "movement_season": prev.get("movement_season"),
            "movement_level": prev.get("movement_level"),
            "whiff": round(1000 * misses / swings) / 10 if swings else prev.get("whiff"),
            "usage_l": (lmap.get(code) or {}).get("usage", prev.get("usage_l")),
            "pitches_l": (lmap.get(code) or {}).get("pitches", prev.get("pitches_l")),
            "usage_r": (rmap.get(code) or {}).get("usage", prev.get("usage_r")),
            "pitches_r": (rmap.get(code) or {}).get("pitches", prev.get("pitches_r")),
        })
    hand = bas.hand_situation_mix(events)
    return {
        "arsenal": arsenal,
        "count_mix": mix.get("count_mix"),
        "platoon": mix.get("platoon"),
        "count_hand_mix": hand,
        "usage_vs_hand": {"vs_LHH": {"n": (mix.get("hand_n") or {}).get("vs_LHH")}, "vs_RHH": {"n": (mix.get("hand_n") or {}).get("vs_RHH")}},
        "throws": throws,
        "synergy_id": sid,
        "pitches_n": mix.get("pitches"),
        "synergy_source": "Synergy LMB 2026",
    }


def apply_hitter(player: dict, events: list[dict], sid: str) -> dict[str, Any]:
    raw = bas.aggregate_events(events, player["team"])
    # Force this batter's id even if the event batter id differs.
    if sid not in raw and raw:
        only = next(iter(raw.values()))
        raw = {sid: only}
        only["synergy_id"] = sid
        only["name"] = player["name"]
        only["team"] = player["team"]
    rows = bas.serialize_hitters(raw, {}, {norm(player["name"]): player["id"]})
    if not rows:
        return {}
    row = rows[0]
    row["mlb_id"] = player["id"]
    row["team"] = player["team"]
    row["name"] = player["name"]
    bats = None
    for ev in events:
        bats = bats or hand_letter((ev.get("batterInfo") or {}).get("battingSide"))
        if bats:
            break
    if bats:
        row["bats"] = bats
    row["synergy_source"] = "Synergy LMB 2026"
    summer = player["hitter"].get("summer_line")
    if summer:
        row["summer_line"] = summer
    return row


def reapply_savant(row: dict) -> None:
    path = DATA / "savant_movement.json"
    if not path.is_file() or row.get("player_id") is None:
        return
    try:
        cache = load_json(path)
    except Exception:
        return
    pack = cache.get(str(int(row["player_id"]))) or {}
    if not pack.get("pitches"):
        return
    import add_savant_movement as savant
    savant.apply_to_row(row, pack)


def write_outputs(by_id: dict[int, dict], dirty: set[int] | None = None) -> None:
    handle = file_lock()
    try:
        _write_outputs(by_id, dirty)
    finally:
        unlock(handle)


def _write_outputs(by_id: dict[int, dict], dirty: set[int] | None = None) -> None:
    arsenals = load_json(DATA / "pregame_pitcher_arsenals.json")
    hitters = load_json(DATA / "advance_opposing_hitters.json")
    heat_path = DATA / "advance_heatmaps.json"
    heat = load_json(heat_path) if heat_path.is_file() else {}
    heat["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    heat["source"] = "Synergy LMB 2026 px/pz"
    heat.setdefault("hitters", {})
    heat.setdefault("pitchers", {})
    spray_path = DATA / "pregame_spray_charts.json"
    spray_doc = load_json(spray_path) if spray_path.is_file() else {}
    spray_by = {}
    for row in spray_doc.get("synergy") or []:
        if row.get("player_id") is not None:
            spray_by[int(row["player_id"])] = row
    ars_by = {int(r["player_id"]): r for r in arsenals.get("pitchers") or []}
    hit_by = {int(r["mlb_id"]): r for r in hitters.get("hitters") or [] if r.get("mlb_id")}
    players = by_id.values() if dirty is None else [by_id[i] for i in dirty if i in by_id]
    for player in players:
        if player["role"] == "P":
            base = ars_by.get(player["id"])
            if base is None:
                continue
            extra = player["arsenal"]
            for key, val in extra.items():
                if key in {"player_id", "name", "team", "summer_line"}:
                    continue
                if val not in (None, [], {}):
                    base[key] = val
            reapply_savant(base)
        else:
            base = hit_by.get(player["id"])
            extra = player["hitter"]
            if base is None:
                continue
            for key, val in extra.items():
                if key in {"mlb_id", "name", "team", "summer_line"} and key in base and key != "synergy_id":
                    if key != "summer_line":
                        continue
                if val not in (None, [], {}):
                    base[key] = val
            pts = extra.get("spray_points") or []
            if pts:
                spray_by[player["id"]] = {
                    "name": player["name"],
                    "team": player["team"],
                    "player_id": player["id"],
                    "points": pts,
                    "source": extra.get("synergy_source") or "Synergy",
                }
        rec = player.get("heat")
        if rec and int(rec.get("located") or 0) > 0:
            bag = heat["pitchers"] if player["role"] == "P" else heat["hitters"]
            bag[str(player["id"])] = rec
            if rec.get("synergy_id"):
                bag[str(rec["synergy_id"])] = rec
    save_json(DATA / "pregame_pitcher_arsenals.json", arsenals)
    save_json(DATA / "advance_opposing_hitters.json", hitters)
    save_json(DATA / "advance_heatmaps.json", heat)
    save_json(DATA / "pregame_spray_charts.json", {
        "synergy_note": "2026 Mexican League Synergy landing spots. RISP and 2K flags come from the pitch log.",
        "synergy": list(spray_by.values()),
    })


def save_checkpoint(pid: int, record: dict) -> None:
    handle = file_lock()
    try:
        ckpt = load_json(CKPT) if CKPT.is_file() else {"done": {}}
        ckpt.setdefault("done", {})[str(pid)] = record
        save_json(CKPT, ckpt)
    finally:
        unlock(handle)


def index_players() -> dict[int, dict]:
    card = load_json(DATA / "pregame_card_stats.json")
    arsenals = load_json(DATA / "pregame_pitcher_arsenals.json")
    hitters = load_json(DATA / "advance_opposing_hitters.json")
    ars_by = {int(r["player_id"]): r for r in arsenals.get("pitchers") or []}
    hit_by = {int(r["mlb_id"]): r for r in hitters.get("hitters") or [] if r.get("mlb_id")}
    out = {}
    for p in card["players"]:
        pid = int(p["id"])
        out[pid] = {
            "id": pid,
            "name": p["name"],
            "team": p["team"],
            "role": p["role"],
            "arsenal": dict(ars_by.get(pid) or {}),
            "hitter": dict(hit_by.get(pid) or {}),
            "heat": None,
        }
    return out


def probe_league_filter(token: str) -> None:
    global USE_LEAGUE_FILTER
    body = {
        "loggingPhases": [bas.LOGGING_PHASE_PITCH],
        "skip": 0,
        "take": 5,
        "batterId": "573d7056080cc2cbe8bf2eb8",
        "leagueIds": [LEAGUE_LMB],
    }
    try:
        doc = bas.api_post(bas.EVENTS_FILTER_URL, token, body, timeout_s=40)
    except Exception as exc:  # noqa: BLE001
        log(f"league filter off: {exc}")
        return
    rows = doc.get("result") if isinstance(doc, dict) else None
    if isinstance(rows, list) and rows and all(is_lmb(ev) for ev in rows):
        USE_LEAGUE_FILTER = True
        log(f"league filter on total={doc.get('totalRecords')}")
    else:
        log("league filter ignored")


def main() -> int:
    global USE_LEAGUE_FILTER
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(k, None)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/Users/colbymorris/apexstats/pitch-tips/.pw-browsers")
    os.environ["NO_PROXY"] = "*"
    by_id = index_players()
    if os.environ.get("LMB_SYNERGY_SKIP_SEED") != "1":
        pics = copy_release_pics(by_id)
        seeded = seed_from_santurce(by_id)
        write_outputs(by_id)
        log(f"seed pics={pics} pitchers={seeded['pitchers']} hitters={seeded['hitters']} heat={seeded['heat']}")
    if os.environ.get("LMB_SYNERGY_SEED_ONLY") == "1":
        return 0
    ckpt = load_json(CKPT) if CKPT.is_file() else {"done": {}}
    syn = Synergy()
    probe_league_filter(syn.token)
    first = [t.strip() for t in os.environ.get("LMB_SYNERGY_TEAM_FIRST", "").split(",") if t.strip()]

    def sort_key(player: dict) -> tuple:
        try:
            rank = first.index(player["team"])
        except ValueError:
            rank = len(first) + 1
        return (rank, player["team"], player["role"], player["name"])

    players = sorted(by_id.values(), key=sort_key)
    only_teams = {t.strip() for t in os.environ.get("LMB_SYNERGY_TEAMS", "").split(",") if t.strip()}
    if only_teams:
        players = [p for p in players if p["team"] in only_teams]
    limit = int(os.environ.get("LMB_SYNERGY_LIMIT", "0") or "0")
    if limit:
        players = players[:limit]
    ok = miss = 0
    dirty: set[int] = set()
    for i, player in enumerate(players, 1):
        pid = str(player["id"])
        prev = (ckpt.get("done") or {}).get(pid) or {}
        if prev.get("status") == "ok" and int(prev.get("pitches") or 0) >= 20:
            ok += 1
            continue
        log(f"[{i}/{len(players)}] {player['team']} {player['role']} {player['name']}")
        sid, _row, rows = syn.search({"name": player["name"], "mlb_id": player["id"]})
        if not sid:
            record = {"status": "no_synergy_id", "candidates": [r.get("name") for r in (rows or [])[:5]]}
            ckpt.setdefault("done", {})[pid] = record
            save_checkpoint(player["id"], record)
            log(f"  no synergy id ({len(rows or [])})")
            miss += 1
            continue
        try:
            events, scanned, _tok = fetch_lmb(syn.token, sid=sid, pitcher=player["role"] == "P")
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None)
            if code == 401 or "401" in str(exc):
                syn.relogin()
                events, scanned, _tok = fetch_lmb(syn.token, sid=sid, pitcher=player["role"] == "P")
            else:
                raise
        record = {"status": "no_video", "synergy_id": sid, "scanned": scanned, "pitches": len(events)}
        if player["role"] == "P" and events:
            packed = arsenal_from_events(events, sid, player["arsenal"].get("arsenal") or [])
            if packed.get("arsenal"):
                player["arsenal"].update(packed)
                heat = bas.aggregate_location_heat(events, split="batter_hand")
                heat["name"] = player["name"]
                heat["team"] = player["team"]
                heat["mlb_id"] = player["id"]
                heat["synergy_id"] = sid
                heat["window_used"] = "LMB 2026"
                player["heat"] = heat
                record["status"] = "ok"
        elif player["role"] == "H" and events:
            packed = apply_hitter(player, events, sid)
            if packed:
                summer = player["hitter"].get("summer_line")
                player["hitter"].update(packed)
                if summer:
                    player["hitter"]["summer_line"] = summer
                heat = bas.aggregate_location_heat(events, split="pitcher_hand")
                heat["name"] = player["name"]
                heat["team"] = player["team"]
                heat["mlb_id"] = player["id"]
                heat["synergy_id"] = sid
                heat["window_used"] = "LMB 2026"
                player["heat"] = heat
                record["status"] = "ok"
                record["pitches"] = (packed.get("overall") or {}).get("pitches") or len(events)
        if record["status"] != "ok":
            record["status"] = "empty" if events else "no_lmb_events"
            miss += 1
            log(f"  empty scanned={scanned} kept={len(events)}")
        else:
            ok += 1
            log(f"  pitches={record['pitches']} scanned={scanned}")
        ckpt.setdefault("done", {})[pid] = record
        dirty.add(player["id"])
        if len(dirty) >= 4:
            write_outputs(by_id, dirty)
            for done_id in list(dirty):
                save_checkpoint(done_id, ckpt["done"][str(done_id)])
            dirty.clear()
    if dirty:
        write_outputs(by_id, dirty)
        for done_id in list(dirty):
            save_checkpoint(done_id, ckpt["done"][str(done_id)])
    log(f"done ok={ok} incomplete={miss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
