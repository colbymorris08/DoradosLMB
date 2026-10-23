#!/usr/bin/env python3
"""One recent 2026 LMB clip per Synergy camera angle for two clubs.

Writes:
  ~/Downloads/LMB video/<team>/<Last, First>/<Angle>.mp4

These leagues tag the two cameras AsLogged and Broadcast. A clip is saved
under LowHome or CF only when Synergy actually labels the track that way.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

SANTURCE = Path("/Users/colbymorris/Santurce2026")
sys.path.insert(0, str(SANTURCE))
sys.path.insert(0, "/Users/colbymorris/apexstats/pitch-tips/cv")

import build_advance_synergy as bas  # noqa: E402
from refresh_roster_synergy import Synergy  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = Path.home() / "Downloads" / "LMB video"
CKPT = ROOT / "runs" / "lmb_two_team_video_checkpoint.json"
TEAMS = {"MEX", "TIJ"}
LEAGUE_LMB = "616a0762c122029009e74144"
MAX_SCAN = int(os.environ.get("LMB_VIDEO_MAX_SCAN", "1600"))


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def last_first(name: str) -> str:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    particles = {"de", "del", "la", "los", "las", "da", "dos", "van", "von"}
    tail = []
    while parts and parts[-1].lower().rstrip(".") in suffixes:
        tail.insert(0, parts.pop())
    if not parts:
        return " ".join(tail)
    n = 1
    if len(parts) >= 3 and parts[-3].lower() in particles and parts[-2].lower() in particles:
        n = 3
    elif len(parts) >= 2 and parts[-2].lower() in particles:
        n = 2
    last = " ".join(parts[-n:] + tail)
    first = " ".join(parts[:-n])
    return f"{last}, {first}" if first else last


def safe(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", s).strip() or "player"


def track_angle(track: dict[str, Any]) -> str:
    return str(track.get("videoCameraAngle") or track.get("cameraAngle") or "").strip()


def first_clip(track: dict[str, Any]) -> tuple[str, str, str] | None:
    """Shortest logged segment for this camera (the pitch, not the long follow)."""
    best = None
    for seg in track.get("segments") or []:
        video = seg.get("video") or {}
        asset_id = str(video.get("id") or "")
        start = video.get("interestedMillisOffsetStart")
        end = video.get("interestedMillisOffsetEnd")
        try:
            span = int(end) - int(start)
        except (TypeError, ValueError):
            span = 10**9
        url = ""
        for var in video.get("videoVariants") or []:
            path = var.get("endpointRelativePath") or var.get("url")
            if path:
                url = str(path).replace("http://", "https://")
                break
        if not url and asset_id and (video.get("videoComponents") or []):
            url = f"https://asset.synergysportstech.com/{asset_id}/hls/master.m3u8"
        if not url:
            continue
        cand = (span, url, asset_id)
        if best is None or cand[0] < best[0]:
            best = cand
    if not best:
        return None
    return best[1], best[2], track_angle(track)


def is_lmb(ev: dict[str, Any]) -> bool:
    game = ev.get("game") or {}
    league = game.get("league") or {}
    lid = str(league.get("id") or game.get("leagueId") or "")
    if lid == LEAGUE_LMB:
        return True
    ab = str(league.get("nameAbbrev") or game.get("leagueName") or "").upper()
    return ab in {"LMB", "MEX", "LM"} or "MEXIC" in ab


def file_angle(angle: str) -> str:
    return safe(angle) or "angle"


def collect_angles(token: str, *, sid: str, pitcher: bool) -> tuple[dict[str, dict[str, Any]], int]:
    """Newest 2026 LMB clip per camera. Prefer a game whose angles are different files."""
    fallback: dict[str, dict[str, Any]] = {}
    unique: dict[str, dict[str, Any]] = {}
    skip = 0
    scanned = 0
    while scanned < MAX_SCAN and not unique:
        body = {
            "loggingPhases": [bas.LOGGING_PHASE_PITCH],
            "skip": skip,
            "take": 100,
            "pitcherId" if pitcher else "batterId": sid,
        }
        try:
            doc = bas.api_post(bas.EVENTS_FILTER_URL, token, body, timeout_s=90)
        except Exception as exc:  # noqa: BLE001
            log(f"  events stop skip={skip}: {exc}")
            break
        rows = doc.get("result") if isinstance(doc, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        years = [y for y in (bas.event_season_year(ev) for ev in rows) if y]
        if years and max(years) < 2026:
            break
        for ev in rows:
            if not is_lmb(ev):
                continue
            game = ev.get("game") or {}
            date = str(game.get("gameDate") or "")
            here: dict[str, dict[str, Any]] = {}
            for track in ((ev.get("videoGroup") or {}).get("videoTracks")) or []:
                got = first_clip(track)
                if not got:
                    continue
                url, asset, angle = got
                if not angle:
                    continue
                here[angle] = {
                    "url": url,
                    "asset_id": asset,
                    "angle": angle,
                    "game_date": date,
                    "league": str((game.get("league") or {}).get("nameAbbrev") or ""),
                    "event_id": str(ev.get("id") or ""),
                }
            assets = {c["asset_id"] for c in here.values() if c["asset_id"]}
            if len(here) >= 2 and len(assets) >= 2:
                unique = here
                break
            for angle, clip in here.items():
                fallback.setdefault(angle, clip)
        scanned += len(rows)
        skip += len(rows)
        total = int((doc or {}).get("totalRecords") or 0)
        if total and skip >= total:
            break
    chosen = unique or fallback
    seen: set[str] = set()
    distinct: dict[str, dict[str, Any]] = {}
    for angle, clip in chosen.items():
        asset = clip.get("asset_id") or clip["url"]
        if asset in seen:
            continue
        seen.add(asset)
        distinct[angle] = clip
    return distinct, scanned


def download(url: str, asset_id: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 10_000:
        return
    tmp = dest.with_suffix(".part.mp4")
    tmp.unlink(missing_ok=True)

    def hls(src: str) -> None:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", src, "-t", "12", "-c", "copy", "-movflags", "+faststart", str(tmp),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 10_000:
            raise RuntimeError((r.stderr or "hls failed")[-240:])

    try:
        if url.endswith(".m3u8") or "/hls/" in url:
            hls(url)
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "DoradosLMBVideo/1.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                tmp.write_bytes(resp.read())
            if tmp.stat().st_size < 10_000:
                raise RuntimeError("too small")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)


def load_players() -> list[dict[str, Any]]:
    card = json.loads((ROOT / "data" / "pregame_card_stats.json").read_text())
    rows = [p for p in card["players"] if p.get("team") in TEAMS]
    rows.sort(key=lambda p: (p["team"], p.get("last") or "", p["name"]))
    return rows


def load_ckpt() -> dict[str, Any]:
    if CKPT.is_file():
        return json.loads(CKPT.read_text())
    return {"done": {}}


def save_ckpt(ckpt: dict[str, Any]) -> None:
    CKPT.parent.mkdir(parents=True, exist_ok=True)
    CKPT.write_text(json.dumps(ckpt, indent=2) + "\n")


def main() -> int:
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "*"
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/Users/colbymorris/apexstats/pitch-tips/.pw-browsers")
    only = os.environ.get("LMB_VIDEO_ONLY", "").strip()
    limit = int(os.environ.get("LMB_VIDEO_LIMIT", "0") or "0")
    players = load_players()
    if only:
        players = [p for p in players if only.lower() in p["name"].lower()]
    if limit:
        players = players[:limit]
    ckpt = load_ckpt()
    syn = Synergy()
    log(f"players={len(players)} out={OUT}")
    ok = miss = 0
    for i, player in enumerate(players, 1):
        pid = str(player["id"])
        team_name = "Diablos Rojos del Mexico" if player["team"] == "MEX" else "Toros de Tijuana"
        folder = OUT / safe(team_name) / safe(last_first(player["name"]))
        prev = (ckpt.get("done") or {}).get(pid) or {}
        if prev.get("status") == "ok" and any(folder.glob("*.mp4")):
            log(f"[{i}/{len(players)}] skip {player['team']} {player['name']}")
            ok += 1
            continue
        log(f"[{i}/{len(players)}] {player['team']} {player['role']} {player['name']}")
        sid, row, rows = syn.search({"name": player["name"], "mlb_id": player["id"]})
        record = {
            "name": player["name"],
            "team": player["team"],
            "role": player["role"],
            "mlb_id": player["id"],
            "synergy_id": sid,
            "folder": str(folder),
            "angles": {},
        }
        if not sid:
            record["status"] = "no_synergy_id"
            record["candidates"] = [r.get("name") for r in (rows or [])[:6]]
            ckpt.setdefault("done", {})[pid] = record
            save_ckpt(ckpt)
            log(f"  no synergy id ({len(rows or [])} name hits)")
            miss += 1
            continue
        picked, scanned = collect_angles(syn.token, sid=sid, pitcher=player["role"] == "P")
        record["scanned"] = scanned
        if not picked:
            record["status"] = "no_video"
            ckpt.setdefault("done", {})[pid] = record
            save_ckpt(ckpt)
            log(f"  no 2026 LMB video in {scanned} events")
            miss += 1
            continue
        for angle, clip in picked.items():
            dest = folder / f"{file_angle(angle)}.mp4"
            try:
                download(clip["url"], clip["asset_id"], dest)
                record["angles"][angle] = {
                    "status": "ok",
                    "game_date": clip["game_date"],
                    "league": clip["league"],
                    "bytes": dest.stat().st_size,
                }
                log(f"  {angle} {clip['league']} {clip['game_date']} {dest.stat().st_size}")
            except Exception as exc:  # noqa: BLE001
                record["angles"][angle] = {"status": "fail", "error": str(exc)[:200]}
                log(f"  {angle} FAIL {exc}")
        got = [k for k, v in record["angles"].items() if v.get("status") == "ok"]
        record["status"] = "ok" if got else "no_video"
        ckpt.setdefault("done", {})[pid] = record
        save_ckpt(ckpt)
        if record["status"] == "ok":
            ok += 1
        else:
            miss += 1
    log(f"done ok={ok} incomplete={miss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
