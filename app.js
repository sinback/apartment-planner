(() => {
  const PX_PER_FT = 16;            // measured from the plan's labeled room sizes
  const PX = PX_PER_FT / 12;       // px per inch
  const W = 1194, H = 703;
  const COLORS = ['#2f6fd6', '#d9822b', '#3a9d5d', '#b4489b', '#c2412f', '#6b5bd2', '#7a8580'];
  const KEY = 'apt-furniture-layout-v1';

  const $ = id => document.getElementById(id);
  const svg = $('plan'), g = $('pieces');

  // ---- state ----
  let pieces = [], sel = null, zoom = 1, uid = 1;
  // Default space: the saved layout shown on a first visit and loaded by "Load default space".
  const DEFAULT_LAYOUT = {"app": "apartment-furniture-planner", "version": 1, "units": "inches; x/y are piece centers from the plan top-left", "pieces": [{"shape": "rect", "name": "TV + Stand", "w": 15.5, "d": 58, "rot": 0, "color": "#2f6fd6", "x": 94, "y": 169}, {"shape": "rect", "name": "Speaker R", "w": 13, "d": 6, "rot": 0, "color": "#2f6fd6", "x": 105, "y": 125}, {"shape": "rect", "name": "Kiwi Cage Table", "w": 29, "d": 43.5, "rot": 0, "color": "#d9822b", "x": 206, "y": 381}, {"shape": "rect", "name": "Speaker L", "w": 13, "d": 6, "rot": 0, "color": "#2f6fd6", "x": 104, "y": 214}, {"shape": "rect", "name": "Steel Kitchen Table", "w": 35, "d": 24, "rot": 0, "color": "#b4489b", "x": 352, "y": 324}, {"shape": "rect", "name": "Arched Bookcase", "w": 34.5, "d": 16, "rot": 90, "color": "#3a9d5d", "x": 629, "y": 230}, {"shape": "L", "w": 55, "d": 32, "a1": 24, "a2": 12, "mirror": true, "name": "Chris' Desk", "rot": 270, "color": "#7a8580", "x": 335, "y": 135}, {"shape": "rect", "name": "Sara's Desk", "w": 60, "d": 30, "rot": 0, "color": "#7a8580", "x": 323, "y": 222}, {"shape": "rect", "name": "Massage Table", "w": 30, "d": 83, "rot": 0, "color": "#b4489b", "x": 250, "y": 148}, {"shape": "text", "name": "Tea Zone", "size": 12, "rot": 0, "color": "#7a8580", "x": 797, "y": 247}, {"shape": "rect", "name": "Queen bed", "w": 60, "d": 80, "rot": 180, "color": "#2f6fd6", "x": 712, "y": 217}, {"shape": "rect", "name": "Table (Full)", "w": 41.5, "d": 63, "rot": 270, "color": "#6b5bd2", "x": 507, "y": 164}, {"shape": "rect", "name": "Chris Bookshelf (Storage)", "w": 40, "d": 12, "rot": 90, "color": "#3a9d5d", "x": 437, "y": 200}, {"shape": "rect", "name": "Chris Bookshelf (Here)", "w": 12, "d": 24, "rot": 180, "color": "#3a9d5d", "x": 437, "y": 241}, {"shape": "rect", "name": "Kitchen Storage #1", "w": 33, "d": 16, "rot": 90, "color": "#c2412f", "x": 411, "y": 263}, {"shape": "text", "name": "Jacket Hooks", "size": 9, "rot": 0, "color": "#7a8580", "x": 479, "y": 318}, {"shape": "rect", "name": "Table w/ 1 Leaf", "w": 32, "d": 63, "rot": 270, "color": "#b4489b", "x": 508, "y": 157}, {"shape": "text", "name": "Shelf Above Window", "size": 9, "rot": 90, "color": "#7a8580", "x": 773, "y": 371}, {"shape": "text", "name": "Weird Wall Lights", "size": 9, "rot": 0, "color": "#7a8580", "x": 284, "y": 233}, {"shape": "text", "name": "Weird Jacket Hooks", "size": 9, "rot": 0, "color": "#7a8580", "x": 140, "y": 397}, {"shape": "rect", "name": "Queen bed (example)", "w": 60, "d": 80, "x": 121, "y": 374, "rot": 90, "color": "#2f6fd6"}, {"shape": "text", "name": "Shelf Below Other Shelf", "size": 9, "rot": 0, "color": "#7a8580", "x": 726, "y": 400}, {"shape": "rect", "name": "Bike nook #2", "w": 35, "d": 18, "rot": 90, "color": "#c2412f", "x": 763, "y": 348}, {"shape": "rect", "name": "Bike nook #1", "w": 35, "d": 18, "rot": 180, "color": "#b4489b", "x": 728, "y": 340}, {"shape": "rect", "name": "Large Shoe Rack", "w": 29.5, "d": 12, "rot": 0, "color": "#3a9d5d", "x": 756, "y": 396}, {"shape": "rect", "name": "Small Shoe Rack #1", "w": 27.5, "d": 12, "rot": 180, "color": "#2f6fd6", "x": 722, "y": 397}, {"shape": "rect", "name": "Small Shoe Rack #2", "w": 27.5, "d": 12, "rot": 0, "color": "#d9822b", "x": 723, "y": 398}, {"shape": "L", "w": 38, "d": 28, "a1": 17, "a2": 20, "mirror": true, "name": "Vanity/toilet", "rot": 270, "color": "#c2412f", "x": 512, "y": 383}, {"shape": "rect", "name": "Kitchen Storage #2", "w": 31.5, "d": 16, "rot": 0, "color": "#c2412f", "x": 345, "y": 389}]};
  const sample = () => ([
    { shape: 'rect', name: 'Queen bed (example)', w: 60, d: 80, x: 290 * 12 / PX_PER_FT, y: 230 * 12 / PX_PER_FT, rot: 90, color: COLORS[0] },
    { shape: 'rect', name: 'Sofa (example)', w: 84, d: 36, x: 673 * 12 / PX_PER_FT, y: 395 * 12 / PX_PER_FT, rot: 0, color: COLORS[1] },
    { shape: 'circle', name: 'Round table (example)', r: 21, x: 465 * 12 / PX_PER_FT, y: 450 * 12 / PX_PER_FT, rot: 0, color: COLORS[2] },
  ]);
  // positions (x, y) are the piece's center in inches from the plan's top-left
  function load() {
    try { const s = JSON.parse(localStorage.getItem(KEY)); if (Array.isArray(s)) return s; } catch (e) {}
    return null;
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(pieces)); } catch (e) {} }
  // first visit (nothing saved in this browser): start from the default space
  const startPieces = () => { try { return sanitize(DEFAULT_LAYOUT); } catch (e) { return sample(); } };
  pieces = (load() || startPieces()).map(p => ({ ...p, id: uid++ }));

  // ---- formatting ----
  const fmt = inches => {
    const t = Math.round(inches * 4) / 4;
    let ft = Math.floor(t / 12), inch = +(t - ft * 12).toFixed(2);
    if (inch >= 12) { ft++; inch = 0; }
    return `${ft}′${inch}″`;
  };
  const dimsText = p => p.shape === 'text' ? 'label' : p.shape === 'rect' ? `${fmt(p.w)} × ${fmt(p.d)}`
    : p.shape === 'L' ? `${fmt(p.w)} × ${fmt(p.d)} · arms ${fmt(p.a1)} / ${fmt(p.a2)}`
    : `r ${fmt(p.r)} · ⌀ ${fmt(p.r * 2)}`;
  // L geometry: overall box w × d centered on (0,0); arm 1 runs along the width at the bottom (depth a1),
  // arm 2 runs along the length on the left (depth a2). Mirror flips it left/right.
  function lPoints(p, s = PX) {
    const w = p.w * s, d = p.d * s, t1 = p.a1 * s, t2 = p.a2 * s, m = p.mirror ? -1 : 1;
    const x0 = -w / 2, y0 = -d / 2, x1 = w / 2, y1 = d / 2;
    return [[x0, y0], [x0 + t2, y0], [x0 + t2, y1 - t1], [x1, y1 - t1], [x1, y1], [x0, y1]].map(([x, y]) => [m * x, y]);
  }
  // keep each arm at least 1 in shorter than the side it runs across, so the L never collapses into a rectangle
  function clampArms(p) {
    let capped = false;
    const maxA1 = Math.max(0.5, p.d - 1), maxA2 = Math.max(0.5, p.w - 1);
    if (p.a1 > maxA1) { p.a1 = maxA1; capped = true; }
    if (p.a2 > maxA2) { p.a2 = maxA2; capped = true; }
    p.a1 = Math.max(0.5, p.a1); p.a2 = Math.max(0.5, p.a2);
    return capped;
  }
  const toIn = (ft, inch) => (parseFloat(ft) || 0) * 12 + (parseFloat(inch) || 0);
  const splitIn = v => { const ft = Math.floor(v / 12); return [ft, +(v - ft * 12).toFixed(2)]; };

  // ---- rendering ----
  const NS = 'http://www.w3.org/2000/svg';
  function el(tag, attrs) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; }

  function render() {
    g.textContent = '';
    const ink = getComputedStyle(document.documentElement).getPropertyValue('--ink').trim();
    for (const p of pieces) {
      const grp = el('g', { class: 'piece', 'data-id': p.id, transform: `translate(${p.x * PX} ${p.y * PX}) rotate(${p.rot || 0})` });
      const on = sel === p.id;
      const common = { fill: p.color, 'fill-opacity': on ? 0.5 : 0.32, stroke: p.color, 'stroke-width': on ? 2.5 : 1.5 };
      if (p.shape === 'text') {
        // free-floating label: the text itself plus a near-invisible hit box so it can be grabbed
        const tx = el('text', { 'text-anchor': 'middle', 'dominant-baseline': 'middle', 'font-size': p.size || 12, 'font-weight': 600, fill: p.color });
        tx.textContent = p.name || 'Label';
        grp.appendChild(tx); g.appendChild(grp);
        let bb; try { bb = tx.getBBox(); } catch (e) { bb = null; }
        if (!bb || !bb.width) bb = { x: -24, y: -(p.size || 12) / 2, width: 48, height: p.size || 12 };
        grp.insertBefore(el('rect', { x: bb.x - 3, y: bb.y - 2, width: bb.width + 6, height: bb.height + 4, rx: 2, fill: p.color, 'fill-opacity': on ? 0.12 : 0.001, stroke: on ? p.color : 'none', 'stroke-dasharray': '4 3', 'stroke-width': 1 }), tx);
        continue;
      }
      let ww, hh;
      if (p.shape === 'rect') {
        ww = p.w * PX; hh = p.d * PX;
        grp.appendChild(el('rect', { ...common, x: -ww / 2, y: -hh / 2, width: ww, height: hh, rx: 1.5 }));
        // front-edge tick so rotation is readable
        grp.appendChild(el('line', { x1: -ww / 2 + 3, x2: ww / 2 - 3, y1: hh / 2 - 2.5, y2: hh / 2 - 2.5, stroke: p.color, 'stroke-width': 2, 'stroke-opacity': .8 }));
      } else if (p.shape === 'L') {
        ww = p.w * PX; hh = p.d * PX;
        grp.appendChild(el('polygon', { ...common, points: lPoints(p).map(q => q.join(',')).join(' '), 'stroke-linejoin': 'round' }));
        // arm 2 label, up the side arm (above the corner)
        const m = p.mirror ? -1 : 1, t1 = p.a1 * PX, t2 = p.a2 * PX;
        const afs = Math.max(6, Math.min(9, Math.min(t1, t2) / 2.4));
        const tg = el('g', { transform: `translate(${m * (-ww / 2 + t2 / 2)} ${-hh / 2 + (hh - t1) / 2}) rotate(${-(p.rot || 0)})` });
        const tx = el('text', { class: 'dims', 'text-anchor': 'middle', 'dominant-baseline': 'middle', 'font-size': afs, fill: ink, 'fill-opacity': .75 });
        tx.textContent = '② ' + fmt(p.a2);
        tg.appendChild(tx); grp.appendChild(tg);
      } else {
        ww = hh = p.r * 2 * PX;
        grp.appendChild(el('circle', { ...common, cx: 0, cy: 0, r: p.r * PX }));
      }
      if (on) grp.appendChild(el(p.shape !== 'circle' ? 'rect' : 'circle', p.shape !== 'circle'
        ? { x: -ww / 2 - 4, y: -hh / 2 - 4, width: ww + 8, height: hh + 8, fill: 'none', stroke: p.color, 'stroke-dasharray': '4 3', 'stroke-width': 1 }
        : { cx: 0, cy: 0, r: p.r * PX + 4, fill: 'none', stroke: p.color, 'stroke-dasharray': '4 3', 'stroke-width': 1 }));
      // label, counter-rotated so it stays upright
      const fs = Math.max(7, Math.min(11, (p.shape === 'L' ? Math.min(ww - p.a2 * PX, p.a1 * PX * 1.7) : Math.min(ww, hh)) / 3.2));
      // L: main label sits in arm 1, beside the corner
      const lx = p.shape === 'L' ? (p.mirror ? -1 : 1) * (p.a2 * PX / 2) : 0;
      const ly = p.shape === 'L' ? hh / 2 - p.a1 * PX / 2 - fs * 0.45 : 0;
      const t = el('g', { transform: `translate(${lx} ${ly}) rotate(${-(p.rot || 0)})` });
      const name = p.name.replace(/ \(example\)$/, '');
      const a = el('text', { class: 'lbl', 'text-anchor': 'middle', y: -1, 'font-size': fs, fill: ink }); a.textContent = name;
      const b = el('text', { class: 'dims', 'text-anchor': 'middle', y: fs, 'font-size': fs * .82, fill: ink, 'fill-opacity': .75 }); b.textContent = dimsText(p);
      if (p.shape === 'L') {
        b.textContent = `${fmt(p.w)} × ${fmt(p.d)}`;
        const c = el('text', { class: 'dims', 'text-anchor': 'middle', y: fs * 1.85, 'font-size': fs * .78, fill: ink, 'fill-opacity': .75 });
        c.textContent = '① ' + fmt(p.a1);
        t.append(a, b, c);
      } else t.append(a, b);
      grp.appendChild(t);
      g.appendChild(grp);
    }
    renderList(); renderInspector(); save();
  }

  function renderList() {
    const L = $('list'); L.textContent = '';
    if (!pieces.length) { const li = document.createElement('li'); li.className = 'empty'; li.textContent = 'No pieces yet. Add one above.'; L.appendChild(li); }
    for (const p of pieces) {
      const li = document.createElement('li'), b = document.createElement('button');
      b.type = 'button'; if (p.id === sel) b.className = 'on';
      b.innerHTML = `<span><span class="swatch" style="background:${p.color}"></span></span><span class="d"></span>`;
      b.firstChild.append(p.name); b.lastChild.textContent = dimsText(p);
      b.onclick = () => { sel = p.id; render(); };
      li.appendChild(b); L.appendChild(li);
    }
  }

  const cur = () => pieces.find(p => p.id === sel);
  function renderInspector() {
    const p = cur();
    $('noSel').hidden = !!p; $('selBody').hidden = !p;
    if (!p) return;
    const active = document.activeElement;
    const set = (id, v) => { if ($(id) !== active) $(id).value = v; };
    set('sName', p.name);
    const isT = p.shape === 'text';
    $('sNameLbl').textContent = isT ? 'Text' : 'Name';
    $('sSizeRow').hidden = !isT; if (isT) set('sSize', p.size || 12);
    $('sRectDims').hidden = p.shape === 'circle' || isT; $('sCircDims').hidden = p.shape !== 'circle'; $('sRotRow').hidden = p.shape === 'circle';
    if (isT) set('sRot', +(p.rot || 0).toFixed(1));
    $('sArmDims').hidden = p.shape !== 'L';
    if (p.shape === 'L') {
      const [a1f, a1i] = splitIn(p.a1), [a2f, a2i] = splitIn(p.a2);
      set('sA1ft', a1f); set('sA1in', a1i); set('sA2ft', a2f); set('sA2in', a2i);
      $('mirror').textContent = p.mirror ? 'Mirror (flipped)' : 'Mirror';
    }
    if (p.shape === 'rect' || p.shape === 'L') {
      const [wf, wi] = splitIn(p.w), [df, di] = splitIn(p.d);
      set('sWft', wf); set('sWin', wi); set('sDft', df); set('sDin', di); set('sRot', +(p.rot || 0).toFixed(1));
    } else { const [rf, ri] = splitIn(p.r); set('sRft', rf); set('sRin', ri); }
    const C = $('colors'); C.textContent = '';
    for (const c of COLORS) {
      const b = document.createElement('button'); b.type = 'button'; b.style.background = c; b.setAttribute('aria-label', 'Color ' + c);
      if (c === p.color) b.className = 'on';
      b.onclick = () => { p.color = c; render(); };
      C.appendChild(b);
    }
  }

  // ---- adding ----
  const center = () => {
    const st = $('stage'), r = svg.getBoundingClientRect(), sr = st.getBoundingClientRect();
    const cx = (sr.left + sr.width / 2 - r.left) / r.width * W, cy = (sr.top + sr.height / 2 - r.top) / r.height * H;
    return { x: Math.max(0, Math.min(W, cx)) / PX, y: Math.max(0, Math.min(H, cy)) / PX };
  };
  let ci = 3;
  $('addRect').onsubmit = e => {
    e.preventDefault();
    const w = toIn($('rWft').value, $('rWin').value), d = toIn($('rDft').value, $('rDin').value);
    if (w <= 0 || d <= 0) return;
    const p = { id: uid++, shape: 'rect', name: $('rName').value.trim() || 'Piece', w, d, rot: 0, color: COLORS[ci++ % COLORS.length], ...center() };
    pieces.push(p); sel = p.id; render();
  };
  $('addCirc').onsubmit = e => {
    e.preventDefault();
    const r = toIn($('cRft').value, $('cRin').value);
    if (r <= 0) return;
    const p = { id: uid++, shape: 'circle', name: $('cName').value.trim() || 'Piece', r, rot: 0, color: COLORS[ci++ % COLORS.length], ...center() };
    pieces.push(p); sel = p.id; render();
  };

  // ---- ft/in normalization: type any number of inches (e.g. 0 ft 35 in) and it is rolled up into feet + inches ----
  const normalizePair = (ftId, inId) => {
    const total = toIn($(ftId).value, $(inId).value);
    if (total < 0) return;
    const [f, i] = splitIn(total);
    $(ftId).value = f; $(inId).value = i;
  };
  [['rWft', 'rWin'], ['rDft', 'rDin'], ['cRft', 'cRin'], ['lWft', 'lWin'], ['lDft', 'lDin'], ['lA1ft', 'lA1in'], ['lA2ft', 'lA2in']].forEach(([a, b]) => {
    [a, b].forEach(id => $(id).addEventListener('change', () => normalizePair(a, b)));
  });
  // add forms: normalize right before adding too, so pressing Enter mid-typing works
  ['addRect', 'addCirc'].forEach(fid => $(fid).addEventListener('submit', () => {
    normalizePair('rWft', 'rWin'); normalizePair('rDft', 'rDin'); normalizePair('cRft', 'cRin');
  }));
  // inspector: once you leave a field, show the rolled-up value
  ['sWft', 'sWin', 'sDft', 'sDin', 'sRft', 'sRin', 'sA1ft', 'sA1in', 'sA2ft', 'sA2in'].forEach(id => $(id).addEventListener('blur', () => setTimeout(renderInspector, 0)));

  // ---- L-shape form: live preview + add ----
  const readL = () => ({
    shape: 'L', w: toIn($('lWft').value, $('lWin').value), d: toIn($('lDft').value, $('lDin').value),
    a1: toIn($('lA1ft').value, $('lA1in').value), a2: toIn($('lA2ft').value, $('lA2in').value), mirror: false
  });
  function drawLPrev() {
    const P = $('lPrev'); P.textContent = '';
    const p = readL();
    const warn = $('lWarn');
    if (p.w <= 0 || p.d <= 0 || p.a1 <= 0 || p.a2 <= 0) { warn.hidden = false; warn.textContent = 'Enter a size above zero for all four fields.'; return; }
    const capped = clampArms(p);
    warn.hidden = !capped;
    if (capped) warn.textContent = 'An arm was as deep as the whole piece, so it will be capped 1 in short of the full size.';
    const s = Math.min(60 / p.w, 46 / p.d);
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
    const ink = getComputedStyle(document.documentElement).getPropertyValue('--ink').trim();
    const gg = el('g', { transform: 'translate(36 29)' });
    gg.appendChild(el('polygon', { points: lPoints(p, s).map(q => q.join(',')).join(' '), fill: accent, 'fill-opacity': .3, stroke: accent, 'stroke-width': 1.2 }));
    const lab = (x, y, txt) => { const t = el('text', { x, y, 'text-anchor': 'middle', 'dominant-baseline': 'middle', 'font-size': 8, 'font-weight': 700, fill: ink }); t.textContent = txt; gg.appendChild(t); };
    lab(p.a2 * s / 2, p.d * s / 2 - p.a1 * s / 2, '1');
    lab(-p.w * s / 2 + p.a2 * s / 2, -p.d * s / 2 + (p.d - p.a1) * s / 2, '2');
    P.appendChild(gg);
  }
  ['lWft', 'lWin', 'lDft', 'lDin', 'lA1ft', 'lA1in', 'lA2ft', 'lA2in'].forEach(id => $(id).addEventListener('input', drawLPrev));
  $('addL').addEventListener('submit', e => {
    e.preventDefault();
    const p = readL();
    if (p.w <= 0 || p.d <= 0 || p.a1 <= 0 || p.a2 <= 0) return;
    clampArms(p);
    const q = { ...p, id: uid++, name: $('lName').value.trim() || 'L-shape', rot: 0, color: COLORS[ci++ % COLORS.length], ...center() };
    pieces.push(q); sel = q.id; render();
  });

  // ---- inspector edits ----
  const onIn = (ids, fn) => ids.forEach(id => $(id).addEventListener('input', () => { const p = cur(); if (p) { fn(p); render(); } }));
  onIn(['sName'], p => p.name = $('sName').value);
  onIn(['sWft', 'sWin'], p => { const v = toIn($('sWft').value, $('sWin').value); if (v > 0) { p.w = v; if (p.shape === 'L') clampArms(p); } });
  onIn(['sDft', 'sDin'], p => { const v = toIn($('sDft').value, $('sDin').value); if (v > 0) { p.d = v; if (p.shape === 'L') clampArms(p); } });
  onIn(['sA1ft', 'sA1in'], p => { const v = toIn($('sA1ft').value, $('sA1in').value); if (v > 0) { p.a1 = v; clampArms(p); } });
  onIn(['sA2ft', 'sA2in'], p => { const v = toIn($('sA2ft').value, $('sA2in').value); if (v > 0) { p.a2 = v; clampArms(p); } });
  const mirror = () => { const p = cur(); if (p && p.shape === 'L') { p.mirror = !p.mirror; render(); } };
  $('mirror').onclick = mirror;
  $('sSize').addEventListener('change', () => { const p = cur(); if (p && p.shape === 'text') { p.size = +$('sSize').value; render(); } });
  $('addText').addEventListener('submit', e => {
    e.preventDefault();
    const text = $('tText').value.trim(); if (!text) return;
    const p = { id: uid++, shape: 'text', name: text, size: +$('tSize').value, rot: 0, color: COLORS[6], ...center() };
    pieces.push(p); sel = p.id; render();
  });
  onIn(['sRft', 'sRin'], p => { const v = toIn($('sRft').value, $('sRin').value); if (v > 0) p.r = v; });
  onIn(['sRot'], p => { const v = parseFloat($('sRot').value); if (!isNaN(v)) p.rot = ((v % 360) + 360) % 360; });
  const rot90 = () => { const p = cur(); if (p && p.shape !== 'circle') { p.rot = ((p.rot || 0) + 90) % 360; render(); } };
  $('rot90').onclick = rot90;
  const del = () => { pieces = pieces.filter(p => p.id !== sel); sel = null; render(); };
  $('del').onclick = del;
  $('dup').onclick = () => { const p = cur(); if (!p) return; const q = { ...p, id: uid++, x: p.x + 12, y: p.y + 12 }; pieces.push(q); sel = q.id; render(); };

  // clear all with in-page confirm
  $('clearAll').onclick = () => {
    const w = $('clearWrap'); w.textContent = '';
    const s = document.createElement('span'); s.textContent = 'Remove every piece?';
    const y = document.createElement('button'); y.type = 'button'; y.className = 'danger'; y.textContent = 'Remove all';
    const n = document.createElement('button'); n.type = 'button'; n.textContent = 'Keep';
    y.onclick = () => { pieces = []; sel = null; render(); restore(); };
    n.onclick = () => restore();
    w.append(s, y, n);
  };
  const clearHandler = $('clearAll').onclick;
  function restore() {
    const w = $('clearWrap'); w.textContent = '';
    const b = document.createElement('button'); b.type = 'button'; b.className = 'danger'; b.id = 'clearAll'; b.textContent = 'Clear all';
    b.onclick = clearHandler; w.appendChild(b);
  }

  // ---- dragging ----
  const toSvg = (cx, cy) => { const pt = svg.createSVGPoint(); pt.x = cx; pt.y = cy; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
  let drag = null, pan = null;
  svg.addEventListener('pointerdown', e => {
    const gEl = e.target.closest('.piece');
    if (!gEl) {
      // empty floor: start panning; a click without movement still deselects
      const st = $('stage');
      pan = { pid: e.pointerId, sx: e.clientX, sy: e.clientY, sl: st.scrollLeft, stp: st.scrollTop, moved: false };
      svg.setPointerCapture(e.pointerId);
      svg.classList.add('panning');
      e.preventDefault();
      return;
    }
    const p = pieces.find(q => q.id === +gEl.dataset.id); if (!p) return;
    sel = p.id;
    // bring to front
    pieces = pieces.filter(q => q !== p).concat(p);
    const s = toSvg(e.clientX, e.clientY);
    drag = { p, ox: p.x - s.x / PX, oy: p.y - s.y / PX, pid: e.pointerId };
    svg.setPointerCapture(e.pointerId);
    render();
    e.preventDefault();
  });
  svg.addEventListener('pointermove', e => {
    if (pan && e.pointerId === pan.pid) {
      const dx = e.clientX - pan.sx, dy = e.clientY - pan.sy;
      if (Math.abs(dx) + Math.abs(dy) > 3) pan.moved = true;
      const st = $('stage');
      st.scrollLeft = pan.sl - dx; st.scrollTop = pan.stp - dy;
      return;
    }
    if (!drag || e.pointerId !== drag.pid) return;
    const s = toSvg(e.clientX, e.clientY);
    let x = s.x / PX + drag.ox, y = s.y / PX + drag.oy;
    if ($('snap').checked) { x = Math.round(x); y = Math.round(y); }
    drag.p.x = Math.max(0, Math.min(W / PX, x)); drag.p.y = Math.max(0, Math.min(H / PX, y));
    const gEl = g.querySelector(`[data-id="${drag.p.id}"]`);
    if (gEl) { gEl.setAttribute('transform', `translate(${drag.p.x * PX} ${drag.p.y * PX}) rotate(${drag.p.rot || 0})`); gEl.classList.add('dragging'); }
  });
  const endDrag = () => {
    if (pan) {
      const clicked = !pan.moved;
      pan = null; svg.classList.remove('panning');
      if (clicked && sel !== null) { sel = null; render(); }
      return;
    }
    if (drag) { drag = null; render(); }
  };
  svg.addEventListener('pointerup', endDrag); svg.addEventListener('pointercancel', endDrag);

  // ---- export / import ----
  const msg = (text, err = false) => { const m = $('ioMsg'); m.textContent = text; m.classList.toggle('err', err); };
  const layoutJSON = () => JSON.stringify({
    app: 'apartment-furniture-planner', version: 1, units: 'inches; x/y are piece centers from the plan top-left',
    pieces: pieces.map(({ id, ...rest }) => rest)
  }, null, 2);
  const stamp = () => { const d = new Date(), z = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}-${z(d.getHours())}${z(d.getMinutes())}`; };

  // plain browser download: wrap the JSON in a Blob and click a temporary <a download> link
  $('exportFile').onclick = () => {
    try {
      const url = URL.createObjectURL(new Blob([layoutJSON()], { type: 'application/json' }));
      const a = document.createElement('a');
      a.href = url; a.download = `furniture-layout-${stamp()}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      // revoke later, not immediately: some browsers start the download asynchronously
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      msg(`Downloaded ${pieces.length} piece${pieces.length === 1 ? '' : 's'} as a .json file.`);
    } catch (e) {
      msg('File export isn’t available in this browser. Use Copy JSON instead.', true);
    }
  };

  $('exportCopy').onclick = () => {
    const text = layoutJSON();
    const fallback = () => {
      $('pasteBox').hidden = false; $('ioText').value = text; $('ioText').focus(); $('ioText').select();
      msg('Copying was blocked here, so the layout is in the box below, selected. Copy it from there.');
    };
    try {
      navigator.clipboard.writeText(text).then(() => msg(`Copied ${pieces.length} piece${pieces.length === 1 ? '' : 's'} as JSON. Paste it into a message or a .json file.`), fallback);
    } catch (e) { fallback(); }
  };

  function sanitize(raw) {
    const arr = Array.isArray(raw) ? raw : (raw && Array.isArray(raw.pieces) ? raw.pieces : null);
    if (!arr) throw new Error('This doesn’t look like a layout: there’s no list of pieces in it.');
    const num = v => typeof v === 'number' && isFinite(v);
    const pos = v => num(v) && v > 0;
    return arr.map((p, i) => {
      const where = `Piece ${i + 1}${p && p.name ? ` (“${String(p.name).slice(0, 40)}”)` : ''}`;
      if (!p || !['rect', 'circle', 'L', 'text'].includes(p.shape)) throw new Error(`${where} has an unknown shape.`);
      const q = {
        shape: p.shape, name: String(p.name ?? 'Piece').slice(0, 80),
        x: num(p.x) ? p.x : W / PX / 2, y: num(p.y) ? p.y : H / PX / 2, rot: num(p.rot) ? p.rot : 0,
        color: /^#[0-9a-f]{6}$/i.test(p.color) ? p.color : COLORS[i % COLORS.length]
      };
      if (p.shape === 'text') {
        q.size = pos(p.size) ? Math.min(p.size, 72) : 12;
      } else if (p.shape === 'circle') {
        if (!pos(p.r)) throw new Error(`${where} is missing a valid radius.`);
        q.r = p.r;
      } else {
        if (!pos(p.w) || !pos(p.d)) throw new Error(`${where} is missing a valid width or length.`);
        q.w = p.w; q.d = p.d;
        if (p.shape === 'L') {
          if (!pos(p.a1) || !pos(p.a2)) throw new Error(`${where} is missing valid arm depths.`);
          q.a1 = p.a1; q.a2 = p.a2; q.mirror = !!p.mirror; clampArms(q);
        }
      }
      return q;
    });
  }

  function offerImport(text, source) {
    let incoming;
    try { incoming = sanitize(JSON.parse(text)); }
    catch (e) { msg(e instanceof SyntaxError ? `Couldn’t read ${source}: it isn’t valid JSON. Nothing was changed.` : `${e.message} Nothing was changed.`, true); return; }
    const apply = () => {
      pieces = incoming.map(p => ({ ...p, id: uid++ })); sel = null; render();
      $('ioConfirm').hidden = true; $('pasteBox').hidden = true; $('ioText').value = '';
      msg(`Loaded ${pieces.length} piece${pieces.length === 1 ? '' : 's'} from ${source}.`);
    };
    if (!pieces.length) { apply(); return; }
    const c = $('ioConfirm'); c.textContent = ''; c.hidden = false;
    const s = document.createElement('span');
    s.textContent = `Replace your ${pieces.length} piece${pieces.length === 1 ? '' : 's'} with ${incoming.length} from ${source}?`;
    const y = document.createElement('button'); y.type = 'button'; y.className = 'danger'; y.textContent = 'Replace';
    const n = document.createElement('button'); n.type = 'button'; n.textContent = 'Cancel';
    y.onclick = apply;
    n.onclick = () => { c.hidden = true; msg('Import cancelled. Your layout is unchanged.'); };
    c.append(s, y, n); msg('');
  }

  $('importFile').addEventListener('change', e => {
    const f = e.target.files && e.target.files[0]; if (!f) return;
    const r = new FileReader();
    r.onload = () => offerImport(String(r.result), `“${f.name}”`);
    r.onerror = () => msg('That file couldn’t be read. Try exporting it again.', true);
    r.readAsText(f);
    e.target.value = '';
  });
  $('pasteToggle').onclick = () => { const b = $('pasteBox'); b.hidden = !b.hidden; if (!b.hidden) $('ioText').focus(); };
  $('pasteLoad').onclick = () => { const t = $('ioText').value.trim(); if (!t) { msg('Paste a layout into the box first.', true); return; } offerImport(t, 'the pasted text'); };

  $('loadDefault').onclick = () => offerImport(JSON.stringify(DEFAULT_LAYOUT), 'the default space');

  // ---- keyboard ----
  document.addEventListener('keydown', e => {
    if (e.target.matches('input, select, textarea')) return;
    const p = cur(); if (!p) return;
    const step = e.shiftKey ? 6 : 1;
    const m = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (m) { p.x += m[0]; p.y += m[1]; render(); e.preventDefault(); }
    else if (e.key === 'Delete' || e.key === 'Backspace') { del(); e.preventDefault(); }
    else if (e.key === 'r' || e.key === 'R') { rot90(); }
    else if (e.key === 'm' || e.key === 'M') { mirror(); }
    else if (e.key === 'Escape') { sel = null; render(); }
  });

  // ---- zoom ----
  function applyZoom() {
    const st = $('stage');
    const base = st.clientWidth;
    svg.style.width = (base * zoom) + 'px';
    svg.style.height = (base * zoom * H / W) + 'px';
    $('zLbl').textContent = Math.round(zoom * 100) + '%';
  }
  $('zIn').onclick = () => { zoom = Math.min(4, zoom * 1.25); applyZoom(); };
  $('zOut').onclick = () => { zoom = Math.max(1, zoom / 1.25); applyZoom(); };
  $('zFit').onclick = () => { zoom = 1; applyZoom(); };
  window.addEventListener('resize', applyZoom);
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', render);
  new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  applyZoom(); render(); drawLPrev();
})();
