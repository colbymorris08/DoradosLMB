/* Strategy card + small-ball card.
   Lineup / pen state: localStorage dorados_strategy_lineup_v1
   Team notes: localStorage dorados_smallball_notes_v1
   Shape: { opponent, santurceHome, teams: { ABBR: { sp, pen: [id], lineup: [{id, pos}], bench: [{id, pos}] } } }
   Notes: { team, notes: { ABBR: "..." } }
*/
(function () {
  const HOME = 'CHI';
  const STRATEGY_KEY = 'dorados_strategy_lineup_v1';
  const NOTES_KEY = 'dorados_smallball_notes_v1';
  const POS = [
    ['1', 'P'], ['2', 'C'], ['3', '1B'], ['4', '2B'], ['5', '3B'],
    ['6', 'SS'], ['7', 'LF'], ['8', 'CF'], ['9', 'RF'], ['DH', 'DH'],
  ];
  const STARTER_POS = ['2', '3', '4', '5', '6', '7', '8', '9', 'DH'];
  const POS_LABEL = Object.fromEntries(POS);
  const DEFAULT_POS = { C: '2', '1B': '3', '2B': '4', '3B': '5', SS: '6', LF: '7', CF: '8', RF: '9', OF: '8', IF: '4', INF: '4', UTL: 'DH', DH: 'DH', P: '1' };

  let DATA = null;
  let byId = new Map();
  let advById = new Map();

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function es() { return (typeof getLang === 'function') && getLang() === 'es'; }
  function tr(en, sp) { return es() ? sp : en; }

  function loadStrategy() {
    let raw = {};
    try { raw = JSON.parse(localStorage.getItem(STRATEGY_KEY) || '{}') || {}; } catch (e) { raw = {}; }
    if (!raw.teams || typeof raw.teams !== 'object') raw.teams = {};
    if (!raw.opponent) raw.opponent = 'MTY';
    if (typeof raw.santurceHome !== 'boolean') raw.santurceHome = true;
    return raw;
  }
  function saveStrategy(state) {
    try { localStorage.setItem(STRATEGY_KEY, JSON.stringify(state)); } catch (e) {}
  }
  function loadNotes() {
    let raw = {};
    try { raw = JSON.parse(localStorage.getItem(NOTES_KEY) || '{}') || {}; } catch (e) { raw = {}; }
    if (!raw.notes || typeof raw.notes !== 'object') raw.notes = {};
    if (!raw.team) raw.team = 'MTY';
    return raw;
  }
  function saveNotesState(state) {
    try { localStorage.setItem(NOTES_KEY, JSON.stringify(state)); } catch (e) {}
  }

  function teamMeta(abbrev) {
    return (DATA.teams || []).find((t) => t.abbrev === abbrev) || { abbrev, name: abbrev, color: '#333', logo: null };
  }
  function normPersonName(s){
    return String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
  }
  function roster(abbrev) {
    const rows = (DATA.players || []).filter((p) => p.team === abbrev);
    const by = new Map();
    rows.forEach((p) => {
      const key = `${p.role || ''}|${normPersonName(p.name)}`;
      const prev = by.get(key);
      if (!prev || (!(Number(prev.id) > 0) && Number(p.id) > 0)) by.set(key, p);
    });
    return [...by.values()];
  }
  function ensureTeam(state, abbrev) {
    if (!state.teams[abbrev]) state.teams[abbrev] = { sp: null, pen: [], lineup: [], bench: [] };
    const st = state.teams[abbrev];
    const ids = new Set(roster(abbrev).map((p) => p.id));
    const keepRow = (r) => {
      if (!r || !ids.has(Number(r.id))) return null;
      const player = byId.get(Number(r.id));
      return { id: Number(r.id), pos: String(r.pos || (player ? defaultPos(player) : 'DH')) };
    };
    const slots = Array(9).fill(null);
    const lineupSeen = new Set();
    const used = new Set();
    const overflow = [];
    (st.lineup || []).forEach((row, i) => {
      const keptRow = keepRow(row);
      if (!keptRow || lineupSeen.has(keptRow.id)) return;
      let pos = STARTER_POS.includes(keptRow.pos) ? keptRow.pos : '';
      if (!pos || used.has(pos)) pos = STARTER_POS.find((code) => !used.has(code)) || '';
      if (!pos) { overflow.push(keptRow); return; }
      let idx = i < 9 && !slots[i] ? i : slots.findIndex((spot) => !spot);
      if (idx < 0) { overflow.push(keptRow); return; }
      used.add(pos);
      lineupSeen.add(keptRow.id);
      slots[idx] = { id: keptRow.id, pos };
    });
    st.lineup = slots;
    const benchSeen = new Set(st.lineup.filter(Boolean).map((r) => r.id));
    st.bench = (st.bench || []).map(keepRow).filter(Boolean).filter((r) => {
      if (benchSeen.has(r.id)) return false;
      benchSeen.add(r.id);
      return true;
    });
    overflow.forEach((row) => {
      if (!st.bench.some((b) => b.id === row.id)) st.bench.push(row);
    });
    st.pen = (st.pen || []).map(Number).filter((id) => ids.has(id) && id !== Number(st.sp));
    st.sp = st.sp != null && ids.has(Number(st.sp)) ? Number(st.sp) : null;
    return st;
  }

  function fmtPct(v) {
    if (v == null || !isFinite(Number(v))) return '';
    return Math.round(Number(v)) + '%';
  }
  function fmtAvg(v) {
    if (v == null || !isFinite(Number(v))) return '';
    const n = Number(v);
    const s = n.toFixed(3);
    return s.replace(/^(-?)0\./, '$1.');
  }
  function posName(code) { return POS_LABEL[code] || code || ''; }
  function defaultPos(player) { return DEFAULT_POS[player.roster_pos] || 'DH'; }
  function openStarterPos(lineup, prefer) {
    const used = new Set((lineup || []).filter(Boolean).map((r) => r.pos));
    if (prefer && STARTER_POS.includes(prefer) && !used.has(prefer)) return prefer;
    return STARTER_POS.find((pos) => !used.has(pos)) || '';
  }
  function cardLast(player, peers) {
    const same = peers.filter((p) => p.last === player.last && p.role === player.role);
    if (same.length < 2) return player.last;
    const ini = (player.name.split(/\s+/)[0] || '').slice(0, 1);
    return ini ? `${ini}. ${player.last}` : player.last;
  }
  function batsClass(player) {
    if (player.role === 'P') return player.throws === 'L' ? 'sc-lhb' : '';
    if (player.bats === 'L') return 'sc-lhb';
    if (player.bats === 'S') return 'sc-shb';
    return '';
  }

  function toneHitter(metric, val, sample) {
    if (val == null || sample == null || sample < 15) return '';
    const v = Number(val);
    if (metric === 'k' || metric === 'wh') {
      const g = 18, r = metric === 'k' ? 27 : 32;
      if (v <= g) return 'sc-good';
      if (v >= r) return 'sc-bad';
      return '';
    }
    if (metric === 'gb') {
      if (v >= 48) return 'sc-good';
      if (v <= 33) return 'sc-bad';
      return '';
    }
    if (metric === 'avg') {
      if (v >= 0.29) return 'sc-good';
      if (v <= 0.22) return 'sc-bad';
      return '';
    }
    if (metric === 'ops') {
      if (v >= 0.8) return 'sc-good';
      if (v <= 0.66) return 'sc-bad';
    }
    return '';
  }
  function tonePitcher(metric, val, sample) {
    if (val == null || sample == null || sample < 20) return '';
    const v = Number(val);
    if (metric === 'k') return v >= 24 ? 'sc-good' : (v <= 16 ? 'sc-bad' : '');
    if (metric === 'gb') return v >= 48 ? 'sc-good' : (v <= 36 ? 'sc-bad' : '');
    if (metric === 'wh') return v >= 28 ? 'sc-good' : (v <= 18 ? 'sc-bad' : '');
    if (metric === 'bb') return v <= 7.5 ? 'sc-good' : (v >= 12 ? 'sc-bad' : '');
    if (metric === 'ops') return v <= 0.68 ? 'sc-good' : (v >= 0.82 ? 'sc-bad' : '');
    return '';
  }

  function ttpFor(id) {
    try {
      const ov = (typeof TTH_OVERRIDES !== 'undefined' && TTH_OVERRIDES) || JSON.parse(localStorage.getItem('dorados_tth_pop_overrides_v1') || '{}');
      const row = ov[String(id)];
      if (row && row.time_to_home != null && String(row.time_to_home).trim() !== '') return String(row.time_to_home).trim();
    } catch (e) {}
    return '';
  }

  function sbRatio(sb, cs) {
    return `${sb || 0}/${(sb || 0) + (cs || 0)}`;
  }
  function summerSteal(h) {
    if (!h) return null;
    const levels = h.summer_levels || [];
    if (levels.length) {
      return {
        sb: levels.reduce((n, row) => n + (Number(row.sb) || 0), 0),
        cs: levels.reduce((n, row) => n + (Number(row.cs) || 0), 0),
      };
    }
    if (h.summer_sb || h.summer_cs) return { sb: Number(h.summer_sb) || 0, cs: Number(h.summer_cs) || 0 };
    return null;
  }
  function sbText(h) {
    const line = summerSteal(h);
    return line ? sbRatio(line.sb, line.cs) : '';
  }

  function aggWhiff(rows) {
    if (!rows || !rows.length) return null;
    let swings = 0, whiffs = 0, pa = 0;
    rows.forEach((r) => {
      swings += Number(r.swings) || 0;
      whiffs += Number(r.whiffs) || 0;
      pa += Number(r.pa) || 0;
    });
    if (!swings) return null;
    return { wh: Math.round((1000 * whiffs) / swings) / 10, pa };
  }

  function indexAdvance(payload) {
    advById = new Map();
    ((payload && payload.hitters) || []).forEach((h) => {
      const id = Number(h.mlb_id);
      if (!id) return;
      const overall = h.overall || {};
      advById.set(id, {
        wh: overall.whiff_pct != null ? Number(overall.whiff_pct) : null,
        L: aggWhiff(h.vs_l_by_pitch_type),
        R: aggWhiff(h.vs_r_by_pitch_type),
      });
    });
  }

  function sideWh(h, playerId, side) {
    const adv = playerId != null ? advById.get(Number(playerId)) : null;
    if (adv) {
      const hand = adv[side];
      if (hand && hand.wh != null) return { wh: hand.wh, pa: hand.pa, src: 'hand' };
      if (adv.wh != null) return { wh: adv.wh, pa: null, src: 'overall' };
    }
    const handWh = side === 'L' ? h.wh_l : h.wh_r;
    const handPa = side === 'L' ? h.wh_l_pa : h.wh_r_pa;
    if (handWh != null) return { wh: handWh, pa: handPa, src: 'hand' };
    const split = side === 'L' ? h.vs_l : h.vs_r;
    if (split && split.wh != null) return { wh: split.wh, pa: split.pa, src: 'hand' };
    if (h.wh != null) return { wh: h.wh, pa: null, src: 'overall' };
    return { wh: null, pa: null, src: null };
  }

  function sideLine(h, side, playerId) {
    const split = side === 'L' ? h.vs_l : h.vs_r;
    const whInfo = sideWh(h, playerId, side);
    return {
      k: h.k, gb: h.gb,
      wh: whInfo.wh,
      whSample: whInfo.src === 'hand' ? whInfo.pa : h.pa,
      whSrc: whInfo.src,
      whPa: whInfo.pa,
      avg: split && split.avg != null ? split.avg : h.avg,
      ops: split && split.ops != null ? split.ops : h.ops,
      sample: split ? split.pa : h.pa,
      split: !!split,
    };
  }

  function statCell(text, cls, title) {
    const t = title ? ` title="${esc(title)}"` : '';
    return `<td class="${cls}"${t}>${text}</td>`;
  }

  function hitterStatRows(player, whoHtml, sbHtml) {
    const h = player && player.hitter;
    if (!h) {
      return `<tr>${whoHtml}<td rowspan="2"></td><td>L</td><td></td><td></td><td></td><td></td><td></td></tr>
        <tr><td>R</td><td></td><td></td><td></td><td></td><td></td></tr>`;
    }
    const rows = ['L', 'R'].map((side, i) => {
      const line = sideLine(h, side, player.id);
      const sample = line.sample || 0;
      const seasonLabel = h.src || 'LBPRC 2025';
      const seasonTitle = tr(`${seasonLabel} season line (no platoon split)`, `Línea ${seasonLabel} (sin split de platoon)`);
      const splitTitle = tr(`Synergy vs ${side}HP · ${line.sample} PA`, `Synergy vs ${side}HP · ${line.sample} PA`);
      const whTitle = line.whSrc === 'hand'
        ? tr(`Synergy whiff vs ${side}HP · ${line.whPa} PA`, `Whiff Synergy vs ${side}HP · ${line.whPa} PA`)
        : (line.whSrc === 'overall'
          ? tr('Synergy overall whiff % (hitter advance)', 'Whiff general Synergy (advance de bateadores)')
          : tr('No whiff in the hitter advance file', 'Sin whiff en el archivo de advance'));
      const cells = [
        statCell(fmtPct(line.k), toneHitter('k', line.k, h.pa), seasonTitle),
        statCell(fmtPct(line.gb), toneHitter('gb', line.gb, h.pa), seasonTitle),
        statCell(fmtPct(line.wh), toneHitter('wh', line.wh, line.whSample), whTitle),
        statCell(fmtAvg(line.avg), toneHitter('avg', line.avg, line.split ? sample : h.pa), line.split ? splitTitle : seasonTitle),
        statCell(fmtAvg(line.ops), toneHitter('ops', line.ops, line.split ? sample : h.pa), line.split ? splitTitle : seasonTitle),
      ].join('');
      if (i === 0) return `<tr>${whoHtml}<td class="sc-sb" rowspan="2">${sbHtml}</td><td class="sc-vs">${side}</td>${cells}</tr>`;
      return `<tr><td class="sc-vs">${side}</td>${cells}</tr>`;
    });
    return rows.join('');
  }

  function starterStatRows(player, whoHtml) {
    const p = player && player.pitcher;
    if (!p) {
      return `<tr>${whoHtml}<td rowspan="2"></td><td>L</td><td></td><td></td><td></td><td></td><td></td></tr>
        <tr><td>R</td><td></td><td></td><td></td><td></td><td></td></tr>`;
    }
    const seasonLabel = p.src || '';
    const title = seasonLabel
      ? tr(`${seasonLabel} pitching line, repeated on L and R`, `Línea de pitcheo ${seasonLabel}, repetida en L y R`)
      : tr('Pitching line, repeated on L and R', 'Línea de pitcheo, repetida en L y R');
    const sample = p.bf || 0;
    const whFor = (side) => (side === 'L' && p.wh_l != null) ? p.wh_l : ((side === 'R' && p.wh_r != null) ? p.wh_r : p.wh);
    const avgTone = (v) => {
      if (v == null || sample < 20) return '';
      const n = Number(v);
      if (n <= 0.22) return 'sc-good';
      if (n >= 0.29) return 'sc-bad';
      return '';
    };
    const rowFor = (side) => [
      statCell(fmtPct(p.k), tonePitcher('k', p.k, sample), title),
      statCell(fmtPct(p.gb), tonePitcher('gb', p.gb, sample), title),
      statCell(fmtPct(whFor(side)), tonePitcher('wh', whFor(side), sample), whFor(side) == null ? tr('No whiff in the arsenal cache', 'Sin whiff en el caché de arsenal') : title),
      statCell(fmtAvg(p.avg), avgTone(p.avg), title),
      statCell(fmtAvg(p.ops), tonePitcher('ops', p.ops, sample), title),
    ].join('');
    return `<tr>${whoHtml}<td class="sc-sb" rowspan="2"></td><td class="sc-vs">L</td>${rowFor('L')}</tr><tr><td class="sc-vs">R</td>${rowFor('R')}</tr>`;
  }

  function pitcherStatRows(player, whoHtml) {
    const p = player && player.pitcher;
    const ttp = player ? esc(ttpFor(player.id)) : '';
    const ttpCell = `<td class="sc-ttp" rowspan="2">${ttp}</td>`;
    if (!p) {
      return `<tr>${whoHtml}${ttpCell}<td>L</td><td></td><td></td><td></td><td></td><td></td></tr>
        <tr><td>R</td><td></td><td></td><td></td><td></td><td></td></tr>`;
    }
    const seasonLabel = p.src || 'LBPRC 2025';
    const title = tr(`${seasonLabel} season line, repeated on L and R (no platoon split)`, `Línea ${seasonLabel}, repetida en L y R (sin split de platoon)`);
    const sample = p.bf || 0;
    const whFor = (side) => (side === 'L' && p.wh_l != null) ? p.wh_l : ((side === 'R' && p.wh_r != null) ? p.wh_r : p.wh);
    const rowFor = (side) => [
      statCell(fmtPct(p.k), tonePitcher('k', p.k, sample), title),
      statCell(fmtPct(p.gb), tonePitcher('gb', p.gb, sample), title),
      statCell(fmtPct(whFor(side)), tonePitcher('wh', whFor(side), sample), whFor(side) == null ? tr('No whiff in the arsenal cache', 'Sin whiff en el caché de arsenal') : title),
      statCell(fmtPct(p.bb), tonePitcher('bb', p.bb, sample), title),
      statCell(fmtAvg(p.ops), tonePitcher('ops', p.ops, sample), title),
    ].join('');
    return `<tr>${whoHtml}${ttpCell}<td class="sc-vs">L</td>${rowFor('L')}</tr><tr><td class="sc-vs">R</td>${rowFor('R')}</tr>`;
  }

  function whoCell(order, pos, last, bats, rowspan) {
    const bits = [];
    if (order) bits.push(`<span class="sc-ord">${esc(order)}</span>`);
    if (pos) bits.push(`<span class="sc-pos">${esc(pos)}</span>`);
    bits.push(`<span class="sc-last ${bats || ''}">${esc(last || '')}</span>`);
    return `<td class="sc-who" rowspan="${rowspan || 2}">${bits.join(' ')}</td>`;
  }

  function emptyHitterPair(order) {
    const who = whoCell(order, '', '', '');
    return `<tr>${who}<td rowspan="2"></td><td class="sc-vs">L</td><td></td><td></td><td></td><td></td><td></td></tr>
      <tr><td class="sc-vs">R</td><td></td><td></td><td></td><td></td><td></td></tr>`;
  }

  function gridCols() {
    return `<colgroup>
      <col class="sc-col-who"><col class="sc-col-sb"><col class="sc-col-vs">
      <col class="sc-col-stat"><col class="sc-col-stat"><col class="sc-col-stat"><col class="sc-col-stat"><col class="sc-col-stat">
    </colgroup>`;
  }
  function hitterTable(players, rowsHtml) {
    return `<table class="sc-grid">
      ${gridCols()}
      <thead><tr>
        <th>${tr('PLAYER', 'JUGADOR')}</th><th>SB/SBA</th><th>VS</th><th>K</th><th>GB</th><th>WH</th><th>AVG</th><th>OPS</th>
      </tr></thead>
      <tbody>${rowsHtml}</tbody>
    </table>`;
  }
  function pitcherTable(rowsHtml) {
    return `<table class="sc-grid">
      ${gridCols()}
      <thead><tr>
        <th>${tr('PLAYER', 'JUGADOR')}</th><th>TTP</th><th>VS</th><th>K</th><th>GB</th><th>WH</th><th>BB</th><th>OPS</th>
      </tr></thead>
      <tbody>${rowsHtml}</tbody>
    </table>`;
  }

  function sheetSide(abbrev, state) {
    const meta = teamMeta(abbrev);
    const people = roster(abbrev);
    const st = ensureTeam(state, abbrev);
    const hitters = people.filter((p) => p.role === 'H');
    const pitchers = people.filter((p) => p.role === 'P');
    const slots = (st.lineup || []).slice(0, 9);
    while (slots.length < 9) slots.push(null);
    const spotRows = slots.map((slot, i) => {
      if (!slot) return emptyHitterPair(String(i + 1));
      const player = byId.get(slot.id);
      if (!player) return emptyHitterPair(String(i + 1));
      const who = whoCell(String(i + 1), posName(slot.pos), cardLast(player, hitters), batsClass(player));
      return hitterStatRows(player, who, esc(sbText(player.hitter)));
    });
    const sp = st.sp ? byId.get(st.sp) : null;
    const pitcherWho = sp
      ? whoCell('', 'P', cardLast(sp, pitchers), batsClass(sp))
      : whoCell('', 'P', '—', '');
    const pitcherRow = starterStatRows(sp, pitcherWho);
    const dhAt = slots.findIndex((slot) => slot && slot.pos === 'DH');
    const hitterRows = dhAt >= 0
      ? spotRows.slice(0, dhAt + 1).join('') + pitcherRow + spotRows.slice(dhAt + 1).join('')
      : spotRows.join('') + pitcherRow;
    const benchSlots = st.bench.length ? st.bench : [null];
    const benchRows = benchSlots.map((slot) => {
      if (!slot) return emptyHitterPair('PH');
      const player = byId.get(slot.id);
      if (!player) return emptyHitterPair('PH');
      const who = whoCell('PH', posName(slot.pos), cardLast(player, hitters), batsClass(player));
      return hitterStatRows(player, who, esc(sbText(player.hitter)));
    }).join('');

    const penIds = st.pen.filter((id) => id !== st.sp);
    const pen = penIds.map((id) => byId.get(id)).filter(Boolean).sort((a, b) => a.last.localeCompare(b.last));
    let pitRows = '';
    if (sp) {
      const who = whoCell('SP', '', cardLast(sp, pitchers), batsClass(sp));
      pitRows += pitcherStatRows(sp, who);
    } else {
      pitRows += `<tr>${whoCell('SP', '', '—', '')}<td rowspan="2"></td><td class="sc-vs">L</td><td></td><td></td><td></td><td></td><td></td></tr><tr><td class="sc-vs">R</td><td></td><td></td><td></td><td></td><td></td></tr>`;
    }
    pitRows += `<tr class="sc-subhead"><td colspan="8">BULLPEN</td></tr>`;
    if (!pen.length) {
      pitRows += `<tr>${whoCell('RP', '', '', '')}<td rowspan="2"></td><td class="sc-vs">L</td><td></td><td></td><td></td><td></td><td></td></tr><tr><td class="sc-vs">R</td><td></td><td></td><td></td><td></td><td></td></tr>`;
    } else {
      pen.forEach((p) => {
        const who = whoCell('RP', '', cardLast(p, pitchers), batsClass(p));
        pitRows += pitcherStatRows(p, who);
      });
    }

    const logo = meta.logo
      ? `<img class="sc-logo" src="${esc(meta.logo)}" alt="">`
      : `<span class="sc-mono">${esc(meta.abbrev)}</span>`;
    const dateStr = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
    return `<section class="sc-side">
      <header class="sc-head" style="background:${esc(meta.color)}">
        <div class="sc-head-name">${esc(meta.name)}</div>
        ${logo}
      </header>
      <div class="sc-date">${esc(dateStr)}</div>
      <div class="sc-bar">HITTERS</div>
      ${hitterTable(hitters, hitterRows)}
      <div class="sc-bar">BENCH / PH</div>
      ${hitterTable(hitters, benchRows)}
      <div class="sc-bar">PITCHERS</div>
      ${pitcherTable(pitRows)}
    </section>`;
  }

  function posOptions(selected, taken) {
    const block = taken || new Set();
    return STARTER_POS.filter((code) => code === selected || !block.has(code)).map((code) => {
      const name = POS_LABEL[code] || code;
      const label = code === 'DH' ? 'DH' : code + ' ' + name;
      return `<option value="${code}"${code === selected ? ' selected' : ''}>${label}</option>`;
    }).join('');
  }

  const NAME_SUFFIXES = new Set(['jr', 'sr', 'ii', 'iii', 'iv', 'v']);
  const NAME_PARTICLES = new Set(['de', 'del', 'la', 'los', 'las', 'da', 'dos', 'van', 'von']);
  function lastComma(name) {
    const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    const suffix = [];
    while (parts.length && NAME_SUFFIXES.has(parts[parts.length - 1].toLowerCase().replace(/\./g, ''))) suffix.unshift(parts.pop());
    if (!parts.length) return suffix.join(' ');
    let n = 1;
    if (parts.length >= 3 && NAME_PARTICLES.has(parts[parts.length - 3].toLowerCase()) && NAME_PARTICLES.has(parts[parts.length - 2].toLowerCase())) n = 3;
    else if (parts.length >= 2 && NAME_PARTICLES.has(parts[parts.length - 2].toLowerCase())) n = 2;
    const last = parts.slice(-n).join(' ');
    const first = parts.slice(0, -n).join(' ');
    const lastBit = suffix.length ? `${last} ${suffix.join(' ')}`.trim() : last;
    return first ? `${lastBit}, ${first}` : lastBit;
  }

  function playerOptions(hitters, selectedId, blocked) {
    const blank = `<option value="">${tr('Select hitter', 'Elegir bateador')}</option>`;
    const opts = hitters.slice().sort((a, b) => a.last.localeCompare(b.last) || a.name.localeCompare(b.name)).map((p) => {
      if (blocked.has(p.id) && p.id !== selectedId) return '';
      return `<option value="${p.id}"${p.id === selectedId ? ' selected' : ''}>${esc(lastComma(p.name))}</option>`;
    }).join('');
    return blank + opts;
  }

  function hitterSlot(abbrev, listName, row, hitters, blocked, taken) {
    const selected = row ? row.id : '';
    const pos = row ? row.pos : 'DH';
    const drag = listName === 'lineup' && row
      ? `draggable="true" data-id="${row.id}" data-team="${esc(abbrev)}" ondragstart="CardApp.dragStart(event)" ondragover="CardApp.dragOver(event)" ondrop="CardApp.dropLineup(event)"`
      : '';
    return `<li ${drag}>
      ${listName === 'lineup' && row ? `<span class="sc-grip" title="${tr('Drag to reorder', 'Arrastra para ordenar')}">↕</span>` : ''}
      <select class="sc-pos-select" onmousedown="event.stopPropagation()" ${row ? '' : 'disabled'} onchange="CardApp.setPos('${esc(abbrev)}', '${listName}', ${row ? row.id : 0}, this.value)">${posOptions(pos, listName === 'lineup' ? taken : null)}</select>
      <select class="sc-name-select" onmousedown="event.stopPropagation()" onchange="CardApp.setRowPlayer('${esc(abbrev)}', '${listName}', ${row ? row.id : 0}, this.value)">${playerOptions(hitters, selected, blocked)}</select>
    </li>`;
  }

  function byLast(a, b) {
    return a.last.localeCompare(b.last) || a.name.localeCompare(b.name);
  }
  function editorSide(abbrev, state) {
    const st = ensureTeam(state, abbrev);
    const people = roster(abbrev);
    const hitters = people.filter((p) => p.role === 'H').slice().sort(byLast);
    const pitchers = people.filter((p) => p.role === 'P').slice().sort(byLast);
    const slots = (st.lineup || []).slice(0, 9);
    while (slots.length < 9) slots.push(null);
    const lineupIds = new Set(slots.filter(Boolean).map((r) => r.id));
    const benchIds = new Set(st.bench.map((r) => r.id));
    const lineupFull = lineupIds.size >= 9;
    const hitterChecks = hitters.map((p) => {
      const on = lineupIds.has(p.id);
      const dis = !on && lineupFull ? ' disabled' : '';
      return `<label class="sc-roster-row">
        <input type="checkbox" ${on ? 'checked' : ''}${dis} onchange="CardApp.toggleLineup('${esc(abbrev)}', ${p.id}, this.checked)">
        <span draggable="true" data-id="${p.id}" data-team="${esc(abbrev)}" ondragstart="CardApp.dragStart(event)">${esc(lastComma(p.name))}</span>
      </label>`;
    }).join('');
    const starterSelect = `<select class="sc-sp-select" onchange="CardApp.setSp('${esc(abbrev)}', this.value)">
      <option value="">${tr('Select starter', 'Elegir abridor')}</option>
      ${pitchers.map((p) => `<option value="${p.id}"${st.sp === p.id ? ' selected' : ''}>${esc(lastComma(p.name))}</option>`).join('')}
    </select>`;
    const spots = slots.map((row, i) => {
      const taken = new Set(slots.filter((other) => other && (!row || other.id !== row.id)).map((other) => other.pos));
      const player = row ? byId.get(row.id) : null;
      const body = player
        ? `<span class="sc-edit-name" draggable="true" data-id="${row.id}" data-team="${esc(abbrev)}" ondragstart="CardApp.dragStart(event)">${esc(lastComma(player.name))}</span>
           <select class="sc-pos-select" onmousedown="event.stopPropagation()" onchange="CardApp.setPos('${esc(abbrev)}', 'lineup', ${row.id}, this.value)">${posOptions(row.pos, taken)}</select>`
        : `<span class="sc-empty">${tr('Drop hitter', 'Suelta un bateador')}</span>`;
      return `<li class="sc-spot${player ? ' sc-filled' : ''}" data-slot="${i}" data-team="${esc(abbrev)}" ondragover="CardApp.dragOver(event)" ondrop="CardApp.dropOnSpot(event)">
        <span class="sc-spot-num">${i + 1}</span>
        ${body}
      </li>`;
    }).join('');
    const benchChecks = hitters.filter((p) => !lineupIds.has(p.id)).map((p) => {
      const on = benchIds.has(p.id);
      return `<label class="sc-roster-row">
        <input type="checkbox" ${on ? 'checked' : ''} onchange="CardApp.toggleBench('${esc(abbrev)}', ${p.id}, this.checked)">
        <span>${esc(lastComma(p.name))}</span>
      </label>`;
    }).join('') || `<div class="sc-empty">${tr('Every hitter is in the lineup.', 'Todos los bateadores están en la alineación.')}</div>`;
    const penChecks = pitchers.filter((p) => p.id !== st.sp).map((p) => {
      const on = st.pen.includes(p.id);
      return `<label class="sc-roster-row">
        <input type="checkbox" ${on ? 'checked' : ''} onchange="CardApp.togglePen('${esc(abbrev)}', ${p.id}, this.checked)">
        <span>${esc(lastComma(p.name))}</span>
      </label>`;
    }).join('') || `<div class="sc-empty">${tr('No other pitchers.', 'No hay más pitchers.')}</div>`;
    return `<div class="sc-editor">
      <div class="sc-editor-h">${esc(teamMeta(abbrev).abbrev)} · ${tr('Today\'s card', 'Carta de hoy')}</div>
      <div class="sc-editor-label">${tr('Lineup — check 9 hitters', 'Alineación — marca 9 bateadores')}</div>
      <div class="sc-roster-list">${hitterChecks}</div>
      <div class="sc-editor-label">${tr('Order — drag a name onto a spot, then pick a position', 'Orden — arrastra un nombre a un turno y elige posición')}</div>
      <ol class="sc-spots">${spots}</ol>
      <div class="sc-editor-label">${tr('Starter — one pitcher. Prints under the DH. Does not hit.', 'Abridor — un pitcher. Va debajo del DH. No batea.')}</div>
      <div class="sc-sp-wrap">${starterSelect}</div>
      <div class="sc-editor-label">${tr('Bench — hitters left off the lineup', 'Banca — bateadores fuera de la alineación')}</div>
      <div class="sc-roster-list">${benchChecks}</div>
      <div class="sc-editor-label">${tr('Bullpen — pitchers other than the starter', 'Bullpen — pitchers que no abren')}</div>
      <div class="sc-roster-list">${penChecks}</div>
      <div class="sc-editor-actions">
        <button type="button" onclick="CardApp.fillBench('${esc(abbrev)}')">${tr('Rest to bench', 'Resto a la banca')}</button>
        <button type="button" onclick="CardApp.checkAllPen('${esc(abbrev)}', true)">${tr('Rest to pen', 'Resto al bullpen')}</button>
        <button type="button" onclick="CardApp.clearLineup('${esc(abbrev)}')">${tr('Clear lineup', 'Vaciar alineación')}</button>
        <button type="button" onclick="CardApp.clearBench('${esc(abbrev)}')">${tr('Clear bench', 'Vaciar banca')}</button>
        <button type="button" onclick="CardApp.clearSp('${esc(abbrev)}')">${tr('Clear SP', 'Quitar abridor')}</button>
        <button type="button" onclick="CardApp.checkAllPen('${esc(abbrev)}', false)">${tr('Clear pen', 'Vaciar bullpen')}</button>
      </div>
    </div>`;
  }

  function renderStrategy() {
    const root = document.getElementById('strategy-root');
    if (!root) return;
    if (!DATA) {
      root.innerHTML = `<div class="note">${tr('Loading card rosters…', 'Cargando rosters…')}</div>`;
      return;
    }
    const state = loadStrategy();
    const opponents = (DATA.teams || []).filter((t) => t.abbrev !== HOME);
    if (!opponents.some((t) => t.abbrev === state.opponent)) state.opponent = opponents[0] ? opponents[0].abbrev : 'MTY';
    const left = state.santurceHome ? HOME : state.opponent;
    const right = state.santurceHome ? state.opponent : HOME;
    const oppOpts = opponents.map((t) => `<option value="${esc(t.abbrev)}"${t.abbrev === state.opponent ? ' selected' : ''}>${esc(t.name)}</option>`).join('');
    const gaps = DATA.gaps || {};
    root.innerHTML = `
      <div class="sc-toolbar">
        <div class="sc-home-toggle" role="group" aria-label="Dorados home or away">
          <span>${tr('Dorados', 'Dorados')}</span>
          <button type="button" class="${state.santurceHome ? 'on' : ''}" onclick="CardApp.setHome(true)">${tr('Home', 'Home')}</button>
          <button type="button" class="${state.santurceHome ? '' : 'on'}" onclick="CardApp.setHome(false)">${tr('Away', 'Visita')}</button>
        </div>
        <p class="sc-legend">${tr(
          'Green = a strength, red = a soft spot. K/GB/WH/AVG/OPS are the 2026 LMB season line, repeated on both hands. There is no platoon split in this feed. TTP is the time-to-home saved on the pop-times tab.',
          'Verde = fortaleza, rojo = punto débil. K/GB/WH/AVG/OPS son la línea LMB 2026, repetida en ambas manos. Este archivo no trae split de platoon. TTP es el tiempo al home guardado en la pestaña de pop times.'
        )}</p>
        <div class="sc-toolbar-right">
          <label>${tr('Home team', 'Equipo de home')}
            <select onchange="CardApp.setHomeTeam(this.value)">
              <option value="CHI"${state.santurceHome ? ' selected' : ''}>${esc(teamMeta('CHI').name)}</option>
              <option value="${esc(state.opponent)}"${state.santurceHome ? '' : ' selected'}>${esc(teamMeta(state.opponent).name)}</option>
            </select>
          </label>
          <label>${tr('Opponent', 'Rival')}
            <select onchange="CardApp.setOpponent(this.value)">${oppOpts}</select>
          </label>
          <button type="button" class="sc-export" onclick="CardApp.exportStrategy()">${tr('Export PDF', 'Exportar PDF')}</button>
        </div>
      </div>
      <p class="note sc-gap">${esc(gaps.pitcher_platoon || '')} ${esc(gaps.hitter_platoon_k_gb || '')}</p>
      <div class="sc-editors">
        ${editorSide(left, state)}
        ${editorSide(right, state)}
      </div>
      <div class="sc-pair" id="strategy-sheet">
        ${sheetSide(left, state)}
        ${sheetSide(right, state)}
      </div>`;
    saveStrategy(state);
  }

  function band(n) {
    if (n == null || !isFinite(Number(n))) return null;
    const v = Number(n);
    if (v > 5) return 'freq';
    if (v >= 2) return 'occ';
    return 'rare';
  }
  function bandWord(b) {
    if (b === 'freq') return tr('Frequent', 'Frecuente');
    if (b === 'occ') return tr('Occasional', 'Ocasional');
    if (b === 'rare') return tr('Rare', 'Raro');
    return '';
  }
  function sacTotal(h) {
    if (!h || (h.sac == null && !h.summer_sac)) return null;
    return (h.sac || 0) + (h.summer_sac || 0);
  }
  function stealScore(h) {
    const line = summerSteal(h);
    return line ? line.sb : 0;
  }
  function groupScore(h) {
    if (!h) return 0;
    return Math.max(stealScore(h), sacTotal(h) || 0, h.bunts || 0);
  }
  function skewed(a, b) {
    return a >= 3 && a >= 2 * Math.max(b, 0) && (a - b) >= 2;
  }

  function runNotes() {
    return { text: '', major: false };
  }

  function buntNotes(h) {
    if (!h) return { text: '', major: false };
    const bits = [];
    let major = false;
    if (h.in_synergy) {
      const risp = h.bunts_risp || 0;
      const other = Math.max(0, (h.bunts || 0) - risp);
      if (skewed(risp, other)) {
        major = true;
        bits.push(tr(
          `Bunches bunts with RISP (${risp}) much more than other situations (${other}).`,
          `Toque mucho más con corredores en posición de anotar (${risp}) que en otras situaciones (${other}).`
        ));
      } else if (skewed(other, risp)) {
        major = true;
        bits.push(tr(
          `Bunches bunts without RISP (${other}) much more than with RISP (${risp}).`,
          `Toque mucho más sin corredores en posición de anotar (${other}) que con ellos (${risp}).`
        ));
      }
      const vl = h.bunts_vl || 0;
      const vr = h.bunts_vr || 0;
      if (skewed(vl, vr)) {
        major = true;
        bits.push(tr(
          `Bunts much more vs LHP (${vl}) than vs RHP (${vr}).`,
          `Toque mucho más vs zurdos (${vl}) que vs derechos (${vr}).`
        ));
      } else if (skewed(vr, vl)) {
        major = true;
        bits.push(tr(
          `Bunts much more vs RHP (${vr}) than vs LHP (${vl}).`,
          `Toque mucho más vs derechos (${vr}) que vs zurdos (${vl}).`
        ));
      }
    }
    if (h.sac != null || h.summer_sac || (h.summer_levels || []).some((row) => row.sac)) {
      const parts = [];
      if (h.sac != null) parts.push(`LBPRC: ${h.sac}`);
      const levels = (h.summer_levels || []).filter((row) => row.sac);
      if (levels.length) levels.forEach((row) => parts.push(`${row.league}: ${row.sac}`));
      else if (h.summer_sac) {
        const src = (h.summer_sources || []).filter((s) => s && s !== 'confirmed').join('/') || '2026';
        parts.push(`${src}: ${h.summer_sac}`);
      }
      bits.push(tr(`Sac bunts ${parts.join(' ')}.`, `Toques de sacrificio ${parts.join(' ')}.`));
    }
    if (h.in_synergy && h.bunts != null && !major) {
      bits.push(tr(`Synergy bunt attempts: ${h.bunts}.`, `Intentos de toque Synergy: ${h.bunts}.`));
    }
    return { text: bits.join(' '), major };
  }

  function aggLabel(h) {
    const line = summerSteal(h);
    if (!line) return '';
    const att = line.sb + line.cs;
    const pct = att ? line.sb / att : 0;
    if (att >= 8 && pct >= 0.7) return 'AGG';
    if (att >= 2) return tr('Will pick his spot', 'Elige el momento');
    return tr('Not', 'No');
  }

  function countCell(n, extra, title) {
    const b = band(n);
    if (b == null) return `<td title="${esc(title || '')}">—</td>`;
    const extraHtml = extra ? `<small class="sb-extra">${extra}</small>` : '';
    return `<td class="sb-${b}" title="${esc(title || bandWord(b))}"><b>${esc(String(n))}</b><small>${esc(bandWord(b))}</small>${extraHtml}</td>`;
  }

  function sbCells(h) {
    const text = sbText(h);
    if (!text) return '<td colspan="2">—</td>';
    const b = band(stealScore(h));
    const cls = b ? `sb-${b}` : '';
    const title = tr('2026 summer stolen bases / attempts', 'Bases robadas / intentos, verano 2026');
    return `<td class="${cls}" colspan="2" title="${esc(title)}"><b>${esc(text)}</b></td>`;
  }

  function sacText(h) {
    if (!h) return '';
    const bits = [];
    if (h.sac != null) bits.push(`LBPRC: ${h.sac}`);
    const levels = (h.summer_levels || []).filter((row) => row.sac);
    if (levels.length) levels.forEach((row) => bits.push(`${row.league}: ${row.sac}`));
    else if (h.summer_sac) {
      const src = (h.summer_sources || []).filter((s) => s && s !== 'confirmed').join('/') || '2026';
      bits.push(`${src}: ${h.summer_sac}`);
    }
    return bits.join(' ');
  }
  function sacCell(h) {
    const text = sacText(h);
    if (!text) return '<td>—</td>';
    const n = sacTotal(h);
    const b = band(n);
    const cls = b ? `sb-${b}` : '';
    const title = tr(
      'Sacrifice bunts. LBPRC is the winter line. The other label is the league: MLB, AAA, AA, A+, A, LMB, or Indy.',
      'Toques de sacrificio. LBPRC es la línea de invierno. La otra etiqueta es la liga: MLB, AAA, AA, A+, A, LMB o Indy.'
    );
    const lines = [`<b>${esc(text)}</b>`];
    if (b) lines.push(`<small>${esc(bandWord(b))}</small>`);
    return `<td class="${cls}" title="${esc(title)}">${lines.join('')}</td>`;
  }
  function hitCell(h) {
    if (!h || !h.in_synergy || h.bunts == null) {
      return `<td title="${esc(tr('Bunt-for-hit is not split out. Synergy bunt attempts show here when the player is in the advance file.', 'El toque de hit no está separado. Los intentos Synergy aparecen aquí si el jugador está en el archivo de advance.'))}">—</td>`;
    }
    return countCell(h.bunts, '', tr('Synergy bunt attempts (sac vs hit is not separated)', 'Intentos de toque Synergy (sacrificio vs hit no está separado)'));
  }

  function renderSmallBall() {
    const root = document.getElementById('smallball-root');
    if (!root) return;
    if (!DATA) {
      root.innerHTML = `<div class="note">${tr('Loading card rosters…', 'Cargando rosters…')}</div>`;
      return;
    }
    const notesState = loadNotes();
    const teams = DATA.teams || [];
    if (!teams.some((t) => t.abbrev === notesState.team)) notesState.team = teams[0] ? teams[0].abbrev : 'CHI';
    const abbrev = notesState.team;
    const meta = teamMeta(abbrev);
    const hitters = roster(abbrev).filter((p) => p.role === 'H').map((p) => ({ p, score: groupScore(p.hitter), band: band(groupScore(p.hitter)) || 'rare' }));
    const groups = [
      ['freq', tr('FREQUENT  >5', 'FRECUENTE  >5')],
      ['occ', tr('OCCASIONAL  2–5', 'OCASIONAL  2–5')],
      ['rare', tr('RARE / NONE  <2', 'RARO / NADA  <2')],
    ];
    let body = '';
    groups.forEach(([key, label]) => {
      const rows = hitters.filter((r) => r.band === key).sort((a, b) => b.score - a.score || a.p.last.localeCompare(b.p.last));
      if (!rows.length) return;
      body += `<tr class="sb-group sb-${key}"><td colspan="9">${esc(label)}</td></tr>`;
      rows.forEach((r, i) => {
        const h = r.p.hitter;
        const run = runNotes(h);
        const bunt = buntNotes(h);
        const stripe = i % 2 ? 'sb-alt' : '';
        body += `<tr class="${stripe}">
          <td class="sb-player">${esc(r.p.name)}</td>
          <td class="sb-spd" title="${esc(tr('No sprint speed in the cache', 'No hay velocidad de sprint en el caché'))}"></td>
          ${sbCells(h)}
          <td class="sb-agg">${esc(aggLabel(h))}</td>
          <td class="sb-note${run.major ? ' sb-major' : ''}">${esc(run.text)}</td>
          ${sacCell(h)}
          ${hitCell(h)}
          <td class="sb-note${bunt.major ? ' sb-major' : ''}">${esc(bunt.text)}</td>
        </tr>`;
      });
    });
    const opts = teams.map((t) => `<option value="${esc(t.abbrev)}"${t.abbrev === abbrev ? ' selected' : ''}>${esc(t.name)}</option>`).join('');
    const logo = meta.logo ? `<img src="${esc(meta.logo)}" alt="">` : `<span class="sc-mono">${esc(meta.abbrev)}</span>`;
    const dateStr = new Date().toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' });
    const noteVal = notesState.notes[abbrev] || '';
    root.innerHTML = `
      <div class="sc-toolbar">
        <p class="sc-legend">${tr(
          'SB/SBA is the 2026 summer line only, stolen bases over attempts. SAC = sacrifice bunts. Frequent >5 green, occasional 2–5 white, rare <2 red. A bunt note turns red when one situation is much more common than the other.',
          'BR/INT es solo la línea de verano 2026, bases robadas sobre intentos. SAC = toques de sacrificio. Frecuente >5 verde, ocasional 2–5 blanco, raro <2 rojo. La nota de toque se pone roja cuando una situación es mucho más común que la otra.'
        )}</p>
        <div class="sc-toolbar-right">
          <label>${tr('Team', 'Equipo')}
            <select onchange="CardApp.setSbTeam(this.value)">${opts}</select>
          </label>
          <button type="button" class="sc-export" onclick="CardApp.exportSmallBall()">${tr('Export PDF', 'Exportar PDF')}</button>
        </div>
      </div>
      <div id="smallball-sheet" class="sb-sheet">
        <div class="sb-top">
          <div class="sb-teamhead" style="background:${esc(meta.color)}">
            ${logo}
            <div>
              <div class="sb-teamname">${esc(meta.name)}</div>
              <div class="sb-date">${esc(dateStr)}</div>
            </div>
          </div>
          <div class="sb-title">SMALL BALL</div>
        </div>
        <table class="sb-table">
          <thead>
            <tr class="sb-band">
              <th colspan="6">BASERUNNING</th>
              <th colspan="3">BUNTING</th>
            </tr>
            <tr class="sb-cols">
              <th>Player</th><th>SPD</th><th colspan="2">SB/SBA</th><th>AGG</th><th>NOTES</th><th>SAC</th><th>HIT</th><th>NOTES</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
          <tfoot>
            <tr class="sb-teamnotes">
              <th>TEAM NOTES</th>
              <td colspan="8"><textarea rows="3" oninput="CardApp.saveTeamNotes('${esc(abbrev)}', this.value)">${esc(noteVal)}</textarea></td>
            </tr>
          </tfoot>
        </table>
      </div>`;
  }

  function refresh() {
    if (document.getElementById('panel-strategy')?.classList.contains('active')) renderStrategy();
    if (document.getElementById('panel-br')?.classList.contains('active')) renderSmallBall();
  }

  function withStrategy(fn) {
    const x = window.scrollX;
    const y = window.scrollY;
    const editors = [...document.querySelectorAll('.sc-editor')].map((el) => el.scrollTop);
    const state = loadStrategy();
    fn(state);
    saveStrategy(state);
    renderStrategy();
    const restore = () => {
      window.scrollTo(x, y);
      document.querySelectorAll('.sc-editor').forEach((el, i) => { el.scrollTop = editors[i] || 0; });
    };
    restore();
    requestAnimationFrame(restore);
  }

  const CARD_CSS = `
    html,body{margin:0;background:#fff;color:#111}
    body{font-family:Arial,Helvetica,sans-serif}
    .sc-pair{display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:start}
    .sc-side{background:#fff;color:#111;border:1px solid #c5c9d0}
    .sc-head{display:flex;align-items:center;justify-content:space-between;color:#fff;padding:6px 10px;min-height:42px}
    .sc-head-name{font-weight:800;font-size:15px;letter-spacing:.01em}
    .sc-logo{width:34px;height:34px;object-fit:contain;background:#fff;border-radius:50%}
    .sc-mono{font-weight:800;font-size:12px;border:1px solid rgba(255,255,255,.7);border-radius:50%;width:34px;height:34px;display:flex;align-items:center;justify-content:center}
    .sc-date{text-align:center;font-size:11px;color:#444;padding:3px 0 4px}
    .sc-bar{background:#d5d8de;color:#222;text-align:center;font-weight:800;font-size:11px;letter-spacing:.08em;padding:3px 0;border-top:1px solid #b7bcc6;border-bottom:1px solid #b7bcc6}
    .sc-pair{min-width:0}
    .sc-side{min-width:0;overflow:hidden}
    .sc-grid{width:100%;border-collapse:collapse;font-size:8px;line-height:1.15;table-layout:fixed}
    .sc-col-who{width:34%}
    .sc-col-sb{width:11%}
    .sc-col-vs{width:6%}
    .sc-col-stat{width:9.8%}
    .sc-grid th{background:#e6e8ec;color:#222;font-weight:700;font-size:7px;letter-spacing:.02em;padding:2px 1px;border:1px solid #c5c9d0;text-align:center;overflow:hidden}
    .sc-grid td{border:1px solid #e1e4ea;padding:1px 2px;text-align:center;background:#fff;white-space:nowrap;overflow:hidden}
    .sc-who{text-align:left !important;white-space:nowrap;font-weight:700;color:#111;overflow:hidden}
    .sc-sb{overflow:hidden}
    .sc-ord,.sc-pos{display:inline-block;min-width:1em;margin-right:2px;font-weight:800}
    .sc-last{font-weight:800}
    .sc-lhb{color:#c0392b}
    .sc-shb{color:#1a5276}
    .sc-vs{font-weight:700;color:#333}
    .sc-good{background:#2e9e4f !important;color:#fff !important;font-weight:800}
    .sc-bad{background:#e04b4b !important;color:#fff !important;font-weight:800}
    .sc-subhead td{background:#eceff3 !important;text-align:left !important;font-weight:800;letter-spacing:.06em;font-size:9px}
    .sb-sheet{background:#fff;color:#111;border:1px solid #c5c9d0}
    .sb-top{display:grid;grid-template-columns:1.1fr 1fr}
    .sb-teamhead{display:flex;gap:8px;align-items:center;color:#fff;padding:8px 10px}
    .sb-teamhead img{width:36px;height:36px;object-fit:contain;background:#fff;border-radius:50%}
    .sb-teamname{font-weight:800;font-size:16px}
    .sb-date{font-size:12px;opacity:.9}
    .sb-title{background:#111;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;letter-spacing:.14em;font-size:18px}
    .sb-table{width:100%;border-collapse:collapse;font-size:10px;table-layout:fixed}
    .sb-table th,.sb-table td{border:1px solid #d5d8de;padding:3px 4px;vertical-align:middle;text-align:center}
    .sb-band th{background:#b42318;color:#fff;letter-spacing:.08em;font-size:11px}
    .sb-cols th{background:#c0392b;color:#fff;font-size:10px}
    .sb-player{text-align:left !important;font-weight:700}
    .sb-alt td{background:#f3f7fb}
    .sb-group td{font-weight:800;letter-spacing:.06em;text-align:left !important}
    .sb-freq,.sb-group.sb-freq td{background:#1e8f45 !important;color:#fff !important}
    .sb-occ{background:#fff !important;color:#111 !important}
    .sb-group.sb-occ td{background:#f4f4f4 !important;color:#111 !important}
    .sb-rare,.sb-group.sb-rare td{background:#d64545 !important;color:#fff !important}
    .sb-major{background:#c0392b !important;color:#fff !important;font-weight:700}
    .sb-note{text-align:left !important;font-size:9px;line-height:1.25;white-space:normal !important}
    .sb-spd{background:#eef2f6}
    .sb-table small{display:block;font-size:8px;font-weight:700;letter-spacing:.02em}
    .sb-extra{font-weight:600 !important}
    .sb-agg{font-size:9px}
    .sb-teamnotes th{background:#f6e27a;color:#111;font-weight:800;letter-spacing:.04em}
    .sb-teamnotes td{background:#fff8e8;text-align:left !important}
    .sb-teamnotes textarea{width:100%;border:none;background:transparent;font:inherit;font-size:11px;resize:vertical;color:#111}
    @media print { .sc-good,.sc-bad,.sb-freq,.sb-rare,.sb-major,.sb-band th,.sb-cols th,.sc-head,.sb-teamhead,.sb-title,.sb-teamnotes th{-webkit-print-color-adjust:exact;print-color-adjust:exact} }
  `;

  function openPrint(title, inner, orientation, extraCss) {
    const w = window.open('', '_blank');
    if (!w) {
      alert(tr('Pop-up blocked — allow pop-ups to export PDF.', 'El navegador bloqueó la ventana. Permite pop-ups para exportar el PDF.'));
      return;
    }
    const portrait = orientation === 'portrait';
    const page = portrait ? 'letter portrait' : 'letter landscape';
    const wide = portrait ? '8.0in' : '10.7in';
    const tallIn = portrait ? 10.15 : 7.55;
    w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
      <style>
        @page { size: ${page}; margin: 0.22in; }
        ${CARD_CSS}
        ${extraCss || ''}
        #fit{width:${wide};transform-origin:top left}
      </style></head><body><div id="fit">${inner}</div></body></html>`);
    w.document.close();
    const fit = () => {
      const el = w.document.getElementById('fit');
      if (!el) return;
      const avail = tallIn * 96;
      const h = el.scrollHeight || el.getBoundingClientRect().height;
      if (h > avail) {
        const z = Math.max(0.42, avail / h);
        el.style.zoom = String(z);
      }
      setTimeout(() => { try { w.focus(); w.print(); } catch (e) {} }, 250);
    };
    setTimeout(fit, 60);
  }

  const CardApp = {
    boot(payload, advance) {
      DATA = payload;
      byId = new Map(((payload && payload.players) || []).map((p) => [p.id, p]));
      indexAdvance(advance);
    },
    renderStrategy,
    renderSmallBall,
    refresh,
    setOpponent(v) { withStrategy((s) => { s.opponent = v; }); },
    setHome(flag) { withStrategy((s) => { s.santurceHome = !!flag; }); },
    setHomeTeam(abbrev) { withStrategy((s) => { s.santurceHome = abbrev === HOME; }); },
    toggleLineup(team, id, on) {
      withStrategy((s) => {
        const st = ensureTeam(s, team);
        const pid = Number(id);
        const slots = st.lineup;
        if (on) {
          if (slots.some((r) => r && r.id === pid)) return;
          const idx = slots.findIndex((r) => !r);
          if (idx < 0) return;
          const player = byId.get(pid);
          const pos = openStarterPos(slots, player ? defaultPos(player) : 'DH');
          if (!pos) return;
          slots[idx] = { id: pid, pos };
          st.bench = st.bench.filter((b) => b.id !== pid);
        } else {
          st.lineup = slots.map((r) => (r && r.id === pid ? null : r));
        }
      });
    },
    toggleBench(team, id, on) {
      withStrategy((s) => {
        const st = ensureTeam(s, team);
        const pid = Number(id);
        if (on) {
          st.lineup = st.lineup.map((r) => (r && r.id === pid ? null : r));
          if (!st.bench.some((b) => b.id === pid)) {
            const player = byId.get(pid);
            st.bench.push({ id: pid, pos: player ? defaultPos(player) : 'DH' });
          }
        } else {
          st.bench = st.bench.filter((b) => b.id !== pid);
        }
      });
    },
    fillBench(team) {
      withStrategy((s) => {
        const st = ensureTeam(s, team);
        const inLine = new Set(st.lineup.filter(Boolean).map((r) => r.id));
        roster(team).filter((p) => p.role === 'H' && !inLine.has(p.id)).forEach((p) => {
          if (!st.bench.some((b) => b.id === p.id)) st.bench.push({ id: p.id, pos: defaultPos(p) });
        });
      });
    },
    setPos(team, listName, id, pos) {
      withStrategy((s) => {
        const st = ensureTeam(s, team);
        const list = listName === 'bench' ? st.bench : st.lineup;
        const row = list.find((r) => r && r.id === Number(id));
        if (!row) return;
        if (listName !== 'bench' && (pos === '1' || !STARTER_POS.includes(pos) || list.some((other) => other && other.id !== row.id && other.pos === pos))) return;
        row.pos = pos;
      });
    },
    setRowPlayer(team, listName, oldId, newId) {
      withStrategy((s) => {
        const st = ensureTeam(s, team);
        const list = listName === 'bench' ? st.bench : st.lineup;
        const other = listName === 'bench' ? st.lineup : st.bench;
        const pid = Number(newId);
        const previous = Number(oldId);
        if (!pid) {
          if (listName === 'bench') st.bench = list.filter((r) => r && r.id !== previous);
          else st.lineup = list.filter((r) => r && r.id !== previous);
          return;
        }
        if (list.some((r) => r && r.id === pid) || other.some((r) => r && r.id === pid)) return;
        const player = byId.get(pid);
        const row = list.find((r) => r && r.id === previous);
        const others = listName === 'bench' ? [] : st.lineup.filter((r) => r && (!row || r.id !== row.id));
        const pos = listName === 'bench'
          ? (player ? defaultPos(player) : 'DH')
          : openStarterPos(others, player ? defaultPos(player) : 'DH');
        if (listName !== 'bench' && !pos) return;
        if (row) {
          row.id = pid;
          row.pos = pos;
        } else if (listName === 'bench') st.bench.push({ id: pid, pos });
        else if (st.lineup.length < 9) st.lineup.push({ id: pid, pos });
      });
    },
    clearLineup(team) { withStrategy((s) => { ensureTeam(s, team).lineup = []; }); },
    clearBench(team) { withStrategy((s) => { ensureTeam(s, team).bench = []; }); },
    clearSp(team) { withStrategy((s) => { ensureTeam(s, team).sp = null; }); },
    setSp(team, id) {
      withStrategy((s) => {
        const st = ensureTeam(s, team);
        const pid = Number(id);
        if (!pid) { st.sp = null; return; }
        const player = byId.get(pid);
        if (!player || player.role !== 'P' || player.team !== team) return;
        st.sp = player.id;
        st.pen = st.pen.filter((x) => x !== st.sp);
      });
    },
    togglePen(team, id, on) {
      withStrategy((s) => {
        const st = ensureTeam(s, team);
        const pid = Number(id);
        if (pid === st.sp) return;
        if (on) { if (!st.pen.includes(pid)) st.pen.push(pid); }
        else st.pen = st.pen.filter((x) => x !== pid);
      });
    },
    checkAllPen(team, on) {
      withStrategy((s) => {
        const st = ensureTeam(s, team);
        if (!on) { st.pen = []; return; }
        st.pen = roster(team).filter((p) => p.role === 'P' && p.id !== st.sp).map((p) => p.id);
      });
    },
    dragStart(e) {
      e.dataTransfer.setData('text/plain', e.currentTarget.dataset.id);
      e.dataTransfer.effectAllowed = 'move';
    },
    dragOver(e) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; },
    dropOnSpot(e) {
      e.preventDefault();
      const id = Number(e.dataTransfer.getData('text/plain'));
      const team = e.currentTarget.dataset.team;
      const slot = Number(e.currentTarget.dataset.slot);
      if (!id || !(slot >= 0 && slot < 9)) return;
      const player = byId.get(id);
      if (!player || player.role !== 'H' || player.team !== team) return;
      withStrategy((s) => {
        const st = ensureTeam(s, team);
        const slots = st.lineup.slice(0, 9);
        while (slots.length < 9) slots.push(null);
        const from = slots.findIndex((r) => r && r.id === id);
        if (from === slot) return;
        const target = slots[slot];
        if (from >= 0) {
          slots[slot] = slots[from];
          slots[from] = target;
        } else {
          const pos = (target && target.pos) || openStarterPos(slots.map((r, i) => (i === slot ? null : r)), defaultPos(player));
          if (!pos) return;
          slots[slot] = { id, pos };
          st.bench = st.bench.filter((b) => b.id !== id);
        }
        st.lineup = slots;
      });
    },
    dropLineup(e) { CardApp.dropOnSpot(e); },
    setSbTeam(v) {
      const state = loadNotes();
      state.team = v;
      saveNotesState(state);
      renderSmallBall();
    },
    saveTeamNotes(team, text) {
      const state = loadNotes();
      state.notes[team] = text;
      saveNotesState(state);
    },
    exportStrategy() {
      const el = document.getElementById('strategy-sheet');
      if (!el) return;
      openPrint('Strategy card', el.outerHTML, 'portrait', `
        .sc-pair{gap:6px}
        .sc-grid{font-size:8px}
        .sc-grid th{font-size:7px}
        .sc-head{min-height:36px;padding:4px 8px}
        .sc-head-name{font-size:13px}
        .sc-who{font-size:8px}
        .sc-bar{font-size:10px;padding:2px 0}
      `);
    },
    exportSmallBall() {
      const el = document.getElementById('smallball-sheet');
      if (!el) return;
      const clone = el.cloneNode(true);
      clone.querySelectorAll('textarea').forEach((ta) => {
        const div = document.createElement('div');
        div.textContent = ta.value;
        div.style.whiteSpace = 'pre-wrap';
        div.style.minHeight = '36px';
        ta.replaceWith(div);
      });
      openPrint('Small ball', clone.outerHTML, 'landscape');
    },
  };
  window.CardApp = CardApp;
})();
