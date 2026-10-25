// Generates the Fankata GUI mockups as SVG + PNG.
// Usage: NODE_PATH=<dir with @resvg/resvg-js> node screenshots/src/render.js
const fs = require('fs');
const path = require('path');
const { Resvg } = require('@resvg/resvg-js');

const OUT = path.resolve(__dirname, '..');
let W = 1280, H = 800;   // window size; a screen may ask for another (13-fans-wide)
const PAD = 40;
const SANS = 'Cantarell', MONO = 'DejaVu Sans Mono';

const THEMES = {
  light: {
    backdrop: ['#dfe6f3', '#eee7f6'], bg: '#f5f6fa', side: '#eff1f6', surface: '#ffffff',
    border: '#e4e7ef', borderStrong: '#d4d8e3', text: '#1b1f2b', muted: '#6a7084', faint: '#a0a6b6',
    accent: '#5a67f2', accentSoft: '#eceefe', ok: '#0f9f6c', okSoft: '#e2f6ed', warn: '#c26a04',
    warnSoft: '#fdf1dc', err: '#e0445a', errSoft: '#fde8eb', track: '#eceef4', illusA: '#edf2ff',
    illusB: '#f5eeff', illusOff: '#f2f3f7', grid: '#edeff4', input: '#f7f8fb', shadow: 0.07,
    frame: '#2b2f3b', frameHi: '#454b5b', hole: '#1a1d25', plate: '#d6dbe5', dark: false,
  },
  dark: {
    backdrop: ['#0b0d13', '#1d1633'], bg: '#15171e', side: '#1a1c24', surface: '#1f222b',
    border: '#2c303c', borderStrong: '#3a3f4d', text: '#eceef4', muted: '#9aa0b3', faint: '#686d80',
    accent: '#8089ff', accentSoft: '#2a2d52', ok: '#34d399', okSoft: '#133a2d', warn: '#fbbf24',
    warnSoft: '#3a2e12', err: '#fb7185', errSoft: '#3d1a22', track: '#2c303c', illusA: '#222739',
    illusB: '#2a2442', illusOff: '#1b1e26', grid: '#2a2e39', input: '#1a1d25', shadow: 0.45,
    frame: '#343947', frameHi: '#4f5567', hole: '#111318', plate: '#434959', dark: true,
  },
};

const HEAT = [[0, '#38bdf8'], [0.45, '#8b7cf6'], [0.72, '#fb923c'], [1, '#f43f5e']];

// ---------------------------------------------------------------- helpers
let defs = [], uid = 0;
const nid = (p = 'i') => `${p}${uid++}`;
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const f1 = n => n.toFixed(1);
const fmt = n => n.toLocaleString('en-US');
const tw = (s, size, o = {}) => String(s).length * size * (o.mono ? 0.602 : o.bold ? 0.52 : 0.47);

function text(x, y, s, o = {}) {
  const { size = 14, weight = 400, fill, anchor = 'start', mono = false, ls, op, rot } = o;
  return `<text x="${x}" y="${y}" font-family="${mono ? MONO : SANS}" font-size="${size}" font-weight="${weight}"` +
    ` fill="${fill}" text-anchor="${anchor}"${ls != null ? ` letter-spacing="${ls}"` : ''}` +
    `${op != null ? ` opacity="${op}"` : ''}${rot ? ` transform="rotate(${rot} ${x} ${y})"` : ''}>${esc(s)}</text>`;
}
function rect(x, y, w, h, r, fill, o = {}) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}"` +
    `${o.stroke ? ` stroke="${o.stroke}" stroke-width="${o.sw || 1}"` : ''}` +
    `${o.dash ? ` stroke-dasharray="${o.dash}"` : ''}${o.op != null ? ` opacity="${o.op}"` : ''}` +
    `${o.filter ? ` filter="url(#${o.filter})"` : ''}/>`;
}
function lerpHex(a, b, t) {
  const pa = [1, 3, 5].map(i => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map(i => parseInt(b.slice(i, i + 2), 16));
  return '#' + pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, '0')).join('');
}
function heat(v) {
  const t = Math.max(0, Math.min(1, v / 100));
  for (let i = 1; i < HEAT.length; i++) {
    if (t <= HEAT[i][0]) return lerpHex(HEAT[i - 1][1], HEAT[i][1], (t - HEAT[i - 1][0]) / (HEAT[i][0] - HEAT[i - 1][0]));
  }
  return HEAT[HEAT.length - 1][1];
}
function heatGrad(x1, x2, y = 0) {
  const id = nid('hg');
  defs.push(`<linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="${x1}" y1="${y}" x2="${x2}" y2="${y}">` +
    HEAT.map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join('') + '</linearGradient>');
  return id;
}
function linGrad(stops, x2 = 1, y2 = 0) {
  const id = nid('lg');
  defs.push(`<linearGradient id="${id}" x1="0" y1="0" x2="${x2}" y2="${y2}">` +
    stops.map(([o, c, a = 1]) => `<stop offset="${o}" stop-color="${c}" stop-opacity="${a}"/>`).join('') + '</linearGradient>');
  return id;
}

// Monotone cubic (Fritsch–Carlson / PCHIP) — the same evaluator the app uses.
function pchip(P) {
  const n = P.length, xs = P.map(p => p[0]), ys = P.map(p => p[1]);
  const h = [], d = [], m = new Array(n);
  for (let i = 0; i < n - 1; i++) { h[i] = xs[i + 1] - xs[i]; d[i] = (ys[i + 1] - ys[i]) / h[i]; }
  const end = (h0, h1, d0, d1) => {
    let v = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1);
    if (Math.sign(v) !== Math.sign(d0)) v = 0;
    else if (Math.sign(d0) !== Math.sign(d1) && Math.abs(v) > Math.abs(3 * d0)) v = 3 * d0;
    return v;
  };
  if (n === 2) { m[0] = m[1] = d[0]; } else {
    for (let i = 1; i < n - 1; i++) {
      if (d[i - 1] * d[i] <= 0) m[i] = 0;
      else { const w1 = 2 * h[i] + h[i - 1], w2 = h[i] + 2 * h[i - 1]; m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i]); }
    }
    m[0] = end(h[0], h[1], d[0], d[1]);
    m[n - 1] = end(h[n - 2], h[n - 3], d[n - 2], d[n - 3]);
  }
  return x => {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n - 1]) return ys[n - 1];
    let i = 0; while (x > xs[i + 1]) i++;
    const t = (x - xs[i]) / h[i], t2 = t * t, t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i] +
      (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1];
  };
}

// ---------------------------------------------------------------- data
const CURVES = [
  { name: 'Quiet', pts: [[20, 20], [40, 25], [55, 35], [70, 60], [85, 100]] },
  { name: 'Balanced', pts: [[20, 25], [40, 30], [60, 45], [75, 75], [85, 100]] },
  { name: 'Performance', pts: [[20, 40], [45, 55], [60, 75], [75, 100]] },
  { name: 'Pump steady', pts: [[20, 60], [40, 70], [60, 85], [70, 100]] },
  { name: 'Silent night', allowZero: true, pts: [[30, 0], [50, 10], [65, 30], [80, 70], [90, 100]] },
  { name: 'Full blast', pts: [[0, 100], [100, 100]] },
];
const curve = n => CURVES.find(c => c.name === n);

const SYS_PROBES = [
  { name: 'sys.cpu', desc: 'CPU package · k10temp', val: 54.2, seed: 1 },
  { name: 'sys.gpu', desc: 'GPU edge · amdgpu', val: 48.0, seed: 2 },
  { name: 'sys.nvme', desc: 'Composite · nvme0', val: 41.5, seed: 3 },
  { name: 'sys.chipset', desc: 'Chipset · nct6798', val: 45.0, seed: 4 },
  { name: 'sys.coolant', desc: 'Liquid · nzxt-kraken3', val: 33.9, seed: 5 },
  { name: 'sys.vrm', desc: 'VRM · nct6798', val: 52.3, seed: 6 },
];
const USER_PROBES = [
  { name: 'blend', expr: 'sys.cpu * .9 + sys.gpu / 10', val: 53.6, seed: 7 },
  { name: 'loop', expr: '(sys.coolant - 25) * 2 + 25', val: 42.8, seed: 8 },
];

const FLOOR = 20; // minimum speed % unless a curve allows zero
const MAXRPM = { case: 2000, aio: 2200, pump: 3600 };
const FANS = [
  { name: 'CPU Fan', driver: 'nct6798 · fan2', type: 'case', curve: 'Quiet', probe: 'sys.cpu', val: 54.2, rot: 8 },
  { name: 'AIO Pump', driver: 'nzxt-kraken3 · pump', type: 'pump', curve: 'Pump steady', probe: 'loop', val: 42.8 },
  { name: 'Radiator Fan', driver: 'nzxt-kraken3 · fan1', type: 'aio', curve: 'Balanced', probe: 'loop', val: 42.8, rot: 20 },
  { name: 'Front Intake', driver: 'nct6798 · fan3', type: 'case', duty: 30, rot: 33 },
  { name: 'Rear Exhaust', driver: 'nct6798 · fan4', type: 'case', curve: 'Balanced', probe: 'sys.cpu', val: 54.2, rot: 45 },
  { name: 'nct6798 · pwm6', driver: 'nct6798 · pwm6 · no tach', type: 'generic', unknown: true },
];
for (const f of FANS) {
  f.managed = !!f.curve;
  if (f.managed) f.duty = Math.round(pchip(curve(f.curve).pts)(f.val));
  if (!f.unknown) f.rpm = Math.round(MAXRPM[f.type] * (0.12 + 0.88 * f.duty / 100) / 10) * 10;
}
const fansUsing = n => FANS.filter(f => f.curve === n);

function spark(seed, n = 40) {
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push(Math.sin(i * 0.31 + seed) * 0.5 + Math.sin(i * 0.77 + seed * 2.3) * 0.3 + Math.sin(i * 1.9 + seed * 0.7) * 0.15);
  }
  return out;
}
function sparkline(x, y, w, h, seed, color, sw = 1.6, area = false, T) {
  const d = spark(seed), mn = Math.min(...d), mx = Math.max(...d);
  const P = d.map((v, i) => [x + i / (d.length - 1) * w, y + h - (v - mn) / (mx - mn) * h]);
  const line = 'M' + P.map(p => `${f1(p[0])},${f1(p[1])}`).join(' L');
  let s = '';
  if (area) {
    const g = linGrad([[0, color, 0.28], [1, color, 0]], 0, 1);
    s += `<path d="${line} L${x + w},${y + h} L${x},${y + h} Z" fill="url(#${g})"/>`;
  }
  const last = P[P.length - 1];
  return s + `<path d="${line}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linejoin="round" stroke-linecap="round"/>` +
    `<circle cx="${f1(last[0])}" cy="${f1(last[1])}" r="${sw + 1}" fill="${color}"/>`;
}

// ---------------------------------------------------------------- icons (16-unit grid)
const ICONS = {
  fan: '<path d="M8 8C8 4.2 9.6 2 11.6 2.6C13.2 3.6 11.8 6.6 8 8Z"/><path d="M8 8C4.7 9.9 2 9.6 2 7.5C2.5 5.8 5.7 5.3 8 8Z"/><path d="M8 8C11.3 9.9 12.1 12.4 10.4 13.7C8.5 14.2 7.1 11.2 8 8Z"/>',
  curve: '<path d="M2 2V14H14"/><path d="M4 12C8 12 8.5 5 13.5 4"/>',
  thermo: '<path d="M6.5 9.3V3.6a1.5 1.5 0 0 1 3 0V9.3"/><circle cx="8" cy="11.6" r="2.6"/>',
  chevDown: '<path d="M4 6L8 10L12 6"/>', chevRight: '<path d="M6 4L10 8L6 12"/>', chevLeft: '<path d="M10 4L6 8L10 12"/>',
  plus: '<path d="M8 3V13M3 8H13"/>', x: '<path d="M4 4L12 12M12 4L4 12"/>',
  pencil: '<path d="M10.5 2.5L13.5 5.5L5.5 13.5H2.5V10.5Z"/>',
  dots: '<circle cx="8" cy="3" r="1.2" fill="currentColor"/><circle cx="8" cy="8" r="1.2" fill="currentColor"/><circle cx="8" cy="13" r="1.2" fill="currentColor"/>',
  panel: '<rect x="1.8" y="2.8" width="12.4" height="10.4" rx="2"/><path d="M10 3V13"/>',
  check: '<path d="M3 8.5L6.5 12L13 4.5"/>',
  warn: '<path d="M8 2L14.5 13.5H1.5Z"/><path d="M8 6.3V9.3"/><circle cx="8" cy="11.5" r=".6" fill="currentColor"/>',
  trash: '<path d="M3 4.5H13M6 4.5V2.8H10V4.5M4.5 4.5L5.3 13.5H10.7L11.5 4.5"/>',
  copy: '<rect x="5" y="5" width="9" height="9" rx="1.6"/><path d="M3 11V3.6A1.6 1.6 0 0 1 4.6 2H11"/>',
  refresh: '<path d="M13 8A5 5 0 1 1 11.5 4.4"/><path d="M11.8 1.8V4.8H8.8"/>',
  search: '<circle cx="7" cy="7" r="4.5"/><path d="M10.4 10.4L14 14"/>',
  more: '<circle cx="3" cy="8" r="1.3" fill="currentColor"/><circle cx="8" cy="8" r="1.3" fill="currentColor"/><circle cx="13" cy="8" r="1.3" fill="currentColor"/>',
  pulse: '<path d="M1.5 11H4.5V5H8V11H11.5V5H14.5"/>',
  lifebuoy: '<circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2.6"/><path d="M3.8 3.8L6.2 6.2M12.2 3.8L9.8 6.2M3.8 12.2L6.2 9.8M12.2 12.2L9.8 9.8"/>',
  lock: '<rect x="3" y="7" width="10" height="7" rx="1.6"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0V7"/>',
  info: '<circle cx="8" cy="8" r="6"/><path d="M8 7.2V11"/><circle cx="8" cy="5" r=".6" fill="currentColor"/>',
  bang: '<path d="M8 3.5V9"/><circle cx="8" cy="12" r=".7" fill="currentColor"/>',
  link: '<path d="M9 3H13V7M13 3L7.5 8.5M11 9.5V13H3V5H6.5"/>',
  grip: '<circle cx="6" cy="4" r=".9" fill="currentColor"/><circle cx="10" cy="4" r=".9" fill="currentColor"/><circle cx="6" cy="8" r=".9" fill="currentColor"/><circle cx="10" cy="8" r=".9" fill="currentColor"/><circle cx="6" cy="12" r=".9" fill="currentColor"/><circle cx="10" cy="12" r=".9" fill="currentColor"/>',
};
function icon(name, x, y, size, color, sw = 1.6) {
  const k = size / 16;
  return `<g transform="translate(${x} ${y}) scale(${k})" fill="none" stroke="${color}" color="${color}" stroke-width="${sw / k}"` +
    ` stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</g>`;
}

// ---------------------------------------------------------------- fan illustrations
function blades(cx, cy, R, n, rot, fill) {
  const P = (r, a) => { const t = (a + rot) * Math.PI / 180; return `${f1(cx + r * Math.cos(t))},${f1(cy + r * Math.sin(t))}`; };
  let s = '';
  for (let k = 0; k < n; k++) {
    const a = k * 360 / n, ri = R * 0.3, ro = R;
    s += `<path d="M${P(ri, a - 6)} Q${P(R * 0.66, a - 2)} ${P(ro, a + 18)} A${ro} ${ro} 0 0 1 ${P(ro, a + 46)}` +
      ` Q${P(R * 0.6, a + 40)} ${P(ri, a + 26)} Z" fill="${fill}"/>`;
  }
  return s;
}
function caseFan(cx, cy, S, T, o = {}) {
  const r = S / 2, rot = o.rot || 0;
  const fg = linGrad([[0, T.frameHi], [1, T.frame]], 0, 1);
  const bg = nid('bl');
  defs.push(`<radialGradient id="${bg}" gradientUnits="userSpaceOnUse" cx="${cx}" cy="${cy}" r="${S * 0.45}">` +
    `<stop offset="0.3" stop-color="${T.dark ? '#4b5264' : '#434a5b'}"/><stop offset="1" stop-color="${T.dark ? '#8a93aa' : '#7b8499'}"/></radialGradient>`);
  const ring = o.active ? linGrad([[0, '#38bdf8'], [1, '#a78bfa']], 1, 1) : linGrad([[0, '#8b91a1'], [1, '#6b7181']], 1, 1);
  // o.part: 'base' (frame only) or 'rotor' (blades + hub) for the app's animated layers
  let s = '';
  if (o.part !== 'rotor') {
    s += rect(cx - r, cy - r, S, S, S * 0.17, `url(#${fg})`);
    s += rect(cx - r + 1, cy - r + 1, S - 2, S - 2, S * 0.17, 'none', { stroke: '#ffffff', sw: 1, op: 0.08 });
    for (const [dx, dy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      s += `<circle cx="${cx + dx * r * 0.78}" cy="${cy + dy * r * 0.78}" r="${S * 0.04}" fill="${T.hole}"/>`;
    }
    s += `<circle cx="${cx}" cy="${cy}" r="${S * 0.455}" fill="${T.hole}"/>`;
  }
  if (o.part === 'base') return s;
  s += blades(cx, cy, S * 0.43, 7, rot, `url(#${bg})`);
  s += `<circle cx="${cx}" cy="${cy}" r="${S * 0.15}" fill="${T.frame}"/>`;
  s += `<circle cx="${cx}" cy="${cy}" r="${S * 0.13}" fill="none" stroke="url(#${ring})" stroke-width="${S * 0.028}"/>`;
  s += `<circle cx="${cx}" cy="${cy}" r="${S * 0.055}" fill="${T.frameHi}"/>`;
  return s;
}
function hose(d, S, T) {
  return `<path d="${d}" fill="none" stroke="${T.frame}" stroke-width="${S * 0.1}" stroke-linecap="round"/>` +
    `<path d="${d}" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="${S * 0.025}" stroke-linecap="round"/>`;
}
function aioFan(cx, cy, S, T, o = {}) {
  const rw = S * 1.24, rh = S * 0.9, rx = cx - rw / 2 - S * 0.08, ry = cy - rh / 2;
  if (o.part === 'rotor') return caseFan(cx - S * 0.08, cy, S * 0.84, T, o);
  let s = '';
  const hx = rx + rw;
  s += hose(`M${hx - 4},${ry + rh * 0.22} C${hx + S * 0.3},${ry + rh * 0.22} ${hx + S * 0.18},${cy - S * 0.62} ${hx + S * 0.5},${cy - S * 0.7}`, S, T);
  s += hose(`M${hx - 4},${ry + rh * 0.44} C${hx + S * 0.44},${ry + rh * 0.44} ${hx + S * 0.34},${cy - S * 0.5} ${hx + S * 0.64},${cy - S * 0.56}`, S, T);
  s += rect(rx, ry, rw, rh, S * 0.05, T.dark ? '#3c4252' : '#3a3f4d');
  for (let fx = rx + S * 0.14; fx < rx + rw - S * 0.12; fx += S * 0.032) {
    s += `<path d="M${f1(fx)},${ry + 3} V${ry + rh - 3}" stroke="${T.frame}" stroke-width="1.1"/>`;
  }
  s += rect(rx, ry, S * 0.12, rh, S * 0.04, T.frame) + rect(rx + rw - S * 0.12, ry, S * 0.12, rh, S * 0.04, T.frame);
  s += caseFan(cx - S * 0.08, cy, S * 0.84, T, o);
  return s;
}
function pump(cx, cy, S, T, o = {}) {
  let s = '';
  s += hose(`M${cx + S * 0.2},${cy - S * 0.26} C${cx + S * 0.34},${cy - S * 0.5} ${cx + S * 0.52},${cy - S * 0.46} ${cx + S * 0.78},${cy - S * 0.6}`, S, T);
  s += hose(`M${cx + S * 0.28},${cy - S * 0.08} C${cx + S * 0.52},${cy - S * 0.2} ${cx + S * 0.68},${cy - S * 0.28} ${cx + S * 0.92},${cy - S * 0.34}`, S, T);
  const pw = S * 0.86;
  s += rect(cx - pw / 2, cy - pw / 2, pw, pw, S * 0.12, T.plate);
  for (const [dx, dy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
    s += `<circle cx="${cx + dx * pw * 0.38}" cy="${cy + dy * pw * 0.38}" r="${S * 0.035}" fill="${T.dark ? '#2b2f3b' : '#aab1c0'}"/>`;
  }
  const body = linGrad([[0, T.frameHi], [1, T.frame]], 0.6, 1);
  s += `<circle cx="${cx}" cy="${cy}" r="${S * 0.36}" fill="url(#${body})"/>`;
  const ring = o.active ? linGrad([[0, '#38bdf8'], [0.5, '#8b7cf6'], [1, '#f472b6']], 1, 1) : linGrad([[0, '#8b91a1'], [1, '#6b7181']], 1, 1);
  const ringSvg = `<circle cx="${cx}" cy="${cy}" r="${S * 0.27}" fill="none" stroke="url(#${ring})" stroke-width="${S * 0.04}"/>`;
  if (o.part === 'ring') return ringSvg;
  if (o.active && !o.part) s += `<circle cx="${cx}" cy="${cy}" r="${S * 0.27}" fill="none" stroke="url(#${ring})" stroke-width="${S * 0.07}" filter="url(#glow)" opacity="0.8"/>`;
  if (!o.part) s += ringSvg;
  const cap = linGrad([[0, '#242832'], [1, '#3c4250']], 0, 1);
  s += `<circle cx="${cx}" cy="${cy}" r="${S * 0.22}" fill="url(#${cap})"/>`;
  const k = S * 0.0045;
  s += `<path transform="translate(${cx} ${cy}) scale(${k})" d="M0,-22 C8,-10 14,-2 14,7 A14,14 0 0 1 -14,7 C-14,-2 -8,-10 0,-22Z" fill="#ffffff" opacity="0.85"/>`;
  return s;
}
function generic(cx, cy, S, T) {
  const r = S / 2;
  let s = rect(cx - r, cy - r, S, S, S * 0.17, 'none', { stroke: T.faint, sw: 2, dash: '6 5' });
  s += `<circle cx="${cx}" cy="${cy}" r="${S * 0.42}" fill="none" stroke="${T.faint}" stroke-width="1.5" opacity="0.6"/>`;
  s += `<g opacity="0.55">${blades(cx, cy, S * 0.4, 7, 12, 'none').replace(/fill="none"/g, `fill="none" stroke="${T.faint}" stroke-width="1.3"`)}</g>`;
  s += text(cx, cy + S * 0.1, '?', { size: S * 0.28, weight: 700, fill: T.faint, anchor: 'middle' });
  // 4-pin PWM connector with its wires
  const px = cx + S * 0.2, py = cy + S * 0.22;
  const wires = ['#1f2229', '#f2c230', '#3fb56b', '#3b82f6'];
  wires.forEach((c, i) => {
    s += `<path d="M${px + 7 + i * 9},${py + 18} C${px + 7 + i * 9},${py + 34} ${px + 40 + i * 4},${py + 30} ${px + 52},${py + 30 + i * 3}" fill="none" stroke="${c}" stroke-width="3"/>`;
  });
  s += rect(px, py, 40, 20, 3, T.frame);
  for (let i = 0; i < 4; i++) s += rect(px + 4 + i * 9, py + 6, 5, 8, 1, '#e8b64c');
  return s;
}
function fanArt(cx, cy, S, f, T) {
  const o = { active: f.managed, rot: f.rot || 0 };
  if (f.type === 'aio') return aioFan(cx, cy, S, T, o);
  if (f.type === 'pump') return pump(cx, cy, S, T, o);
  if (f.type === 'generic') return generic(cx, cy, S, T);
  return caseFan(cx, cy, S, T, o);
}

// ---------------------------------------------------------------- widgets
function pill(x, y, label, o) {
  const { bg, fg, dot, size = 12, h = 24, mono = false, bold = true, stroke, anchor = 'start' } = o;
  const w = tw(label, size, { mono, bold }) + (dot ? 30 : 20);
  const x0 = anchor === 'end' ? x - w : x;
  let s = rect(x0, y, w, h, h / 2, bg, stroke ? { stroke } : {});
  if (dot) s += `<circle cx="${x0 + 13}" cy="${y + h / 2}" r="3.5" fill="${dot}"/>`;
  s += text(x0 + (dot ? 22 : 10), y + h / 2 + size * 0.36, label, { size, weight: bold ? 700 : 400, fill: fg, mono });
  return { s, w };
}
function button(x, y, label, T, o = {}) {
  const { primary, ic, h = 34, disabled, anchor = 'start', danger } = o;
  const w = (label ? tw(label, 13, { bold: true }) + 28 : 0) + (ic ? (label ? 20 : 34) : 0);
  const x0 = anchor === 'end' ? x - w : x;
  const fill = primary ? T.accent : T.surface;
  const fg = disabled ? T.faint : primary ? '#ffffff' : danger ? T.err : T.text;
  let s = rect(x0, y, w, h, 10, fill, primary ? {} : { stroke: T.border });
  let tx = x0 + 14;
  if (ic) { s += icon(ic, label ? x0 + 12 : x0 + (w - 16) / 2, y + (h - 16) / 2, 16, fg); tx += 20; }
  if (label) s += text(tx, y + h / 2 + 4.7, label, { size: 13, weight: 700, fill: fg });
  return { s, w };
}
// Speed ring (requirement 5.2.3). The colour runs along the dial like a
// tachometer — green, yellow, orange, then red only near full speed — so a
// ring never "starts red". Unmanaged fans use the same colours, softened.
const DUTY = [[0, '#22c55e'], [0.45, '#facc15'], [0.7, '#fb923c'], [0.9, '#ef4444'], [1, '#ef4444']];
const BANDS = [[0, 45, 'Calm'], [45, 70, 'Working'], [70, 90, 'Busy'], [90, 100, 'Red line']];
function dutyColor(p) {
  const t = Math.max(0, Math.min(1, p));
  for (let i = 1; i < DUTY.length; i++) {
    if (t <= DUTY[i][0]) return lerpHex(DUTY[i - 1][1], DUTY[i][1], (t - DUTY[i - 1][0]) / (DUTY[i][0] - DUTY[i - 1][0]));
  }
  return DUTY[DUTY.length - 1][1];
}
function ring(cx, cy, r, pct, T, active, o = {}) {
  const sw = o.sw || 5, fs = o.fs || 13;
  const P = a => { const t = a * Math.PI / 180; return `${f1(cx + r * Math.sin(t))},${f1(cy - r * Math.cos(t))}`; };
  let s = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${T.track}" stroke-width="${sw}"/>`;
  if (pct != null && pct > 0) {
    const end = Math.min(100, pct) / 100 * 360;
    let arc = '';
    for (let a = 0; a < end; a += 2) {
      const b = Math.min(end, a + 2.6);        // slight overlap hides seams
      arc += `<path d="M${P(a)} A${r} ${r} 0 0 1 ${P(b)}" fill="none" stroke="${dutyColor((a + 1) / 360)}" stroke-width="${sw}"/>`;
    }
    arc += `<circle cx="${cx}" cy="${cy - r}" r="${sw / 2}" fill="${dutyColor(0)}"/>`;
    const [ex, ey] = P(end).split(',');
    arc += `<circle cx="${ex}" cy="${ey}" r="${sw / 2}" fill="${dutyColor(end / 360)}"/>`;
    s += `<g opacity="${active ? 1 : (T.dark ? 0.55 : 0.6)}">${arc}</g>`;
  }
  s += text(cx, cy + fs * 0.35, pct != null ? `${pct}%` : '—', { size: fs, weight: 700, fill: pct != null ? T.text : T.faint, anchor: 'middle' });
  return s;
}
// The previous ring (a left-to-right gradient), kept only for the before/after comparison.
function ringOld(cx, cy, r, pct, T, sw = 5, fs = 13) {
  const c = 2 * Math.PI * r, g = heatGrad(cx - r, cx + r, cy);
  return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${T.track}" stroke-width="${sw}"/>` +
    `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="url(#${g})" stroke-width="${sw}" stroke-linecap="round"` +
    ` stroke-dasharray="${f1(c * pct / 100)} ${f1(c)}" transform="rotate(-90 ${cx} ${cy})"/>` +
    text(cx, cy + fs * 0.35, `${pct}%`, { size: fs, weight: 700, fill: T.text, anchor: 'middle' });
}

// Design sheet: the proposed speed-ring progression.
function ringSheet(T) {
  let s = rect(0, 0, W, H, 0, T.bg);
  s += text(56, 76, 'Speed ring', { size: 28, weight: 700, fill: T.text });
  s += text(56, 106, 'Fills clockwise from 12 o’clock. The colour follows the dial like a tachometer, so a fan only shows red near full speed.',
    { size: 14, fill: T.muted });
  // large examples
  const vals = [15, 35, 55, 75, 92, 100];
  vals.forEach((v, i) => {
    const cx = 150 + i * 196, cy = 232;
    s += rect(cx - 86, 140, 172, 214, 18, T.surface, { filter: 'card' });
    s += rect(cx - 85.5, 140.5, 171, 213, 18, 'none', { stroke: T.border });
    s += ring(cx, cy, 52, v, T, true, { sw: 11, fs: 22 });
    const band = BANDS.find(b => v >= b[0] && v <= b[1] && !(v === b[1] && b[1] !== 100)) || BANDS[3];
    s += text(cx, 318, band[2], { size: 15, weight: 700, fill: dutyColor(v / 100), anchor: 'middle' });
    s += text(cx, 338, `${fmt(Math.round(2000 * (0.12 + 0.88 * v / 100) / 10) * 10)} RPM on a 2,000 RPM fan`,
      { size: 11, fill: T.faint, anchor: 'middle' });
  });
  // the dial unrolled
  const bx = 56, bw = W - 112, by = 410;
  s += text(bx, by - 22, 'The dial, unrolled', { size: 15, weight: 700, fill: T.text });
  const gid = nid('dg');
  defs.push(`<linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="0">` +
    DUTY.map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join('') + '</linearGradient>');
  s += rect(bx, by, bw, 16, 8, `url(#${gid})`);
  BANDS.forEach(([a, b, label]) => {
    const x0 = bx + a / 100 * bw, x1 = bx + b / 100 * bw;
    s += text((x0 + x1) / 2, by + 44, label, { size: 13, weight: 700, fill: dutyColor(((a + b) / 2) / 100), anchor: 'middle' });
    s += text((x0 + x1) / 2, by + 62, `${a}–${b} %`, { size: 12, fill: T.muted, anchor: 'middle' });
  });
  for (const t of [0, 45, 70, 90, 100]) {
    const x = bx + t / 100 * bw;
    s += `<path d="M${f1(x)},${by - 5} V${by + 21}" stroke="${T.bg}" stroke-width="2"/>`;
  }
  // before / after
  const py = 520, pw = (W - 112 - 24) / 2;
  const panel = (x, title, sub) => rect(x, py, pw, 240, 18, T.surface, { filter: 'card' }) +
    rect(x + 0.5, py + 0.5, pw - 1, 239, 18, 'none', { stroke: T.border }) +
    text(x + 24, py + 36, title, { size: 15, weight: 700, fill: T.text }) +
    text(x + 24, py + 58, sub, { size: 12, fill: T.muted });
  s += panel(56, 'Before and after, at 30 %', 'The old ring used the curve’s left-to-right tint, so its first stretch was already red.');
  s += ringOld(56 + 140, py + 150, 48, 30, T, 10, 20);
  s += text(56 + 140, py + 222, 'Before: reads as “hot”', { size: 13, weight: 700, fill: T.err, anchor: 'middle' });
  s += ring(56 + pw - 140, py + 150, 48, 30, T, true, { sw: 10, fs: 20 });
  s += text(56 + pw - 140, py + 222, 'After: calm', { size: 13, weight: 700, fill: T.ok, anchor: 'middle' });
  const x2 = 56 + pw + 24;
  s += panel(x2, 'Managed and unmanaged', 'Unmanaged fans use the same colours, softened, so a fan at full speed still shows its red line.');
  s += ring(x2 + 140, py + 150, 48, 95, T, true, { sw: 10, fs: 20 });
  s += text(x2 + 140, py + 222, 'Managed · 95 %', { size: 13, weight: 700, fill: T.text, anchor: 'middle' });
  s += ring(x2 + pw - 140, py + 150, 48, 95, T, false, { sw: 10, fs: 20 });
  s += text(x2 + pw - 140, py + 222, 'System default · 95 %', { size: 13, weight: 700, fill: T.muted, anchor: 'middle' });
  return s;
}

// Curve chart. Domain x 0..100, y 0..100.
function chart(o) {
  const { x, y, w, h, pts, T, labels = true, grid = true, markers = true, sw = 3, mr = 5, hover = {}, ops = [], fill = true, bg, floor = 0 } = o;
  const L = labels ? 44 : 0, B = labels ? 30 : 0, R = labels ? 14 : 0, Tp = labels ? 14 : 0;
  const px = x + L, py = y + Tp, pw = w - L - R, ph = h - Tp - B;
  const X = v => px + v / 100 * pw, Y = v => py + ph - v / 100 * ph;
  const f = pchip(pts);
  let s = '';
  if (bg) s += rect(x, y, w, h, 8, bg);
  if (grid) {
    for (let v = 0; v <= 100; v += 20) s += `<path d="M${px},${f1(Y(v))} H${px + pw}" stroke="${T.grid}" stroke-width="1"/>`;
    for (let v = 0; v <= 100; v += 10) s += `<path d="M${f1(X(v))},${py} V${py + ph}" stroke="${T.grid}" stroke-width="1" opacity="${v % 20 ? 0.5 : 1}"/>`;
  }
  if (labels) {
    for (let v = 0; v <= 100; v += 20) s += text(px - 10, Y(v) + 4, `${v}%`, { size: 11, fill: T.faint, anchor: 'end' });
    for (let v = 0; v <= 100; v += 10) s += text(X(v), py + ph + 20, v === 100 ? '100 °C' : `${v}°`, { size: 11, fill: T.faint, anchor: 'middle' });
  }
  if (floor) {
    const hp = nid('hp');
    defs.push(`<pattern id="${hp}" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)"><rect width="2.2" height="7" fill="${T.faint}" opacity="${T.dark ? 0.22 : 0.2}"/></pattern>`);
    s += `<rect x="${px}" y="${f1(Y(floor))}" width="${pw}" height="${f1(Y(0) - Y(floor))}" fill="url(#${hp})"/>`;
    s += `<path d="M${px},${f1(Y(floor))} H${px + pw}" stroke="${T.faint}" stroke-width="1.2" stroke-dasharray="5 4"/>`;
    if (labels) s += text(px + pw - 10, Y(floor / 2) + 4.5, `Minimum ${floor} %`, { size: 11.5, weight: 700, fill: T.faint, anchor: 'end' });
  }
  const g = heatGrad(px, px + pw);
  let d = '';
  for (let v = 0; v <= 100; v += 0.5) d += `${d ? ' L' : 'M'}${f1(X(v))},${f1(Y(f(v)))}`;
  if (fill) {
    const mid = nid('mk'), vg = linGrad([[0, '#ffffff', T.dark ? 0.32 : 0.26], [1, '#ffffff', 0]], 0, 1);
    defs.push(`<mask id="${mid}" maskUnits="userSpaceOnUse" x="${px}" y="${py}" width="${pw}" height="${ph}"><rect x="${px}" y="${py}" width="${pw}" height="${ph}" fill="url(#${vg})"/></mask>`);
    s += `<path d="${d} L${X(100)},${Y(0)} L${X(0)},${Y(0)} Z" fill="url(#${g})" mask="url(#${mid})"/>`;
  }
  s += `<path d="${d}" fill="none" stroke="url(#${g})" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round"/>`;
  // live operating points of the fans that use this curve
  ops.forEach((op, i) => {
    const ox = X(op.v), oy = Y(f(op.v)), c = heat(op.v);
    s += `<path d="M${f1(ox)},${py + ph} V${f1(oy)} H${px}" fill="none" stroke="${c}" stroke-width="1.4" stroke-dasharray="4 4" opacity="0.8"/>`;
    s += `<circle cx="${f1(ox)}" cy="${f1(oy)}" r="13" fill="${c}" opacity="0.16"/>`;
    s += `<circle cx="${f1(ox)}" cy="${f1(oy)}" r="6.5" fill="${c}" stroke="${T.surface}" stroke-width="3"/>`;
    if (op.label) {
      const lab = op.label, lw = tw(lab, 12, { bold: true }) + 20;
      let lx = ox - lw / 2; lx = Math.max(px + 4, Math.min(px + pw - lw - 4, lx));
      const ly = op.ly != null ? op.ly : oy - 44 - i * 0;
      s += rect(lx, ly, lw, 26, 13, T.surface, { stroke: c, sw: 1.4 });
      s += text(lx + lw / 2, ly + 17.5, lab, { size: 12, weight: 700, fill: T.text, anchor: 'middle' });
    }
  });
  if (markers) {
    pts.forEach(([vx, vy], i) => {
      const cx = f1(X(vx)), cy = f1(Y(vy)), c = heat(vx);
      if (i === hover.remove) {
        s += `<circle cx="${cx}" cy="${cy}" r="${mr + 11}" fill="${T.err}" opacity="0.16"/>`;
        s += `<circle cx="${cx}" cy="${cy}" r="${mr + 4}" fill="${T.err}" stroke="${T.surface}" stroke-width="3"/>`;
        s += icon('x', X(vx) - 5, Y(vy) - 5, 10, '#ffffff', 2.2);
        s += bubble(X(vx), Y(vy) - 52, `Click to remove  ·  ${vx} °C, ${vy} %`, T);
        s += cursor(X(vx) + 4, Y(vy) + 5);
      } else {
        s += `<circle cx="${cx}" cy="${cy}" r="${mr}" fill="${T.surface}" stroke="${c}" stroke-width="${mr > 3 ? 2.6 : 1.6}"/>`;
      }
    });
  }
  if (hover.add) {
    // ghost point, plus the band of speeds that keep the curve non-decreasing at this x
    const [ax, ay] = hover.add, gx = X(ax), gy = Y(ay);
    const prev = [...pts].reverse().find(p => p[0] < ax), next = pts.find(p => p[0] > ax);
    const lo = Math.max(prev ? prev[1] : 0, floor), hi = next ? next[1] : 100;
    s += `<path d="M${f1(gx)},${f1(Y(lo))} V${f1(Y(hi))}" stroke="${T.accent}" stroke-width="10" stroke-linecap="round" opacity="0.22"/>`;
    s += `<path d="M${f1(gx)},${py + ph} V${f1(gy)} H${px}" fill="none" stroke="${T.accent}" stroke-width="1.2" stroke-dasharray="3 4" opacity="0.7"/>`;
    s += `<circle cx="${f1(gx)}" cy="${f1(gy)}" r="${mr + 4}" fill="${T.surface}" stroke="${T.accent}" stroke-width="2" stroke-dasharray="3 2.5"/>`;
    s += icon('plus', gx - 5, gy - 5, 10, T.accent, 2.2);
    s += bubble(gx, gy - 52, `Click to add  ·  ${ax} °C, ${ay} %`, T);
    s += cursor(gx + 4, gy + 5);
  }
  return s;
}
function bubble(cx, ty, lab, T) {
  const lw = tw(lab, 12, { bold: true }) + 24, bg = T.dark ? '#eceef4' : '#1b1f2b';
  return rect(cx - lw / 2, ty, lw, 28, 8, bg) +
    `<path d="M${cx - 6},${ty + 28} L${cx},${ty + 34} L${cx + 6},${ty + 28} Z" fill="${bg}"/>` +
    text(cx, ty + 18.5, lab, { size: 12, weight: 700, fill: T.dark ? '#1b1f2b' : '#ffffff', anchor: 'middle' });
}
function cursor(x, y) {
  return `<path transform="translate(${f1(x)} ${f1(y)})" d="M0,0 L0,16 L4.3,12.2 L7.2,18.6 L9.9,17.4 L7.1,11.2 L12.6,11.2 Z" fill="#ffffff" stroke="#111318" stroke-width="1.2" stroke-linejoin="round"/>`;
}

// ---------------------------------------------------------------- chrome
function windowFrame(T, body, title = 'Fankata') {
  const bgG = linGrad([[0, T.backdrop[0]], [1, T.backdrop[1]]], 1, 1);
  const clip = nid('clip');
  defs.push(`<clipPath id="${clip}"><rect x="0" y="0" width="${W}" height="${H}" rx="14"/></clipPath>`);
  return `<rect width="${W + PAD * 2}" height="${H + PAD * 2}" fill="url(#${bgG})"/>` +
    `<g transform="translate(${PAD} ${PAD})">` +
    `<rect x="0" y="0" width="${W}" height="${H}" rx="14" fill="${T.bg}" filter="url(#win)"/>` +
    `<g clip-path="url(#${clip})"><rect width="${W}" height="${H}" fill="${T.bg}"/>${body}</g>` +
    `<rect x="0.5" y="0.5" width="${W - 1}" height="${H - 1}" rx="14" fill="none" stroke="${T.dark ? '#ffffff' : '#000000'}" stroke-opacity="${T.dark ? 0.08 : 0.1}"/>` +
    `</g>`;
}
// Four-bladed shuriken: straight leading edge, hooked trailing edge, centre hole.
function shuriken(cx, cy, R, rot = 0) {
  const P = (r, a) => { const t = (a + rot - 90) * Math.PI / 180; return `${f1(cx + r * Math.cos(t))},${f1(cy + r * Math.sin(t))}`; };
  let d = `M${P(R, 0)}`;
  for (let k = 0; k < 4; k++) {
    const a = k * 90;
    d += ` Q${P(R * 0.5, a + 8)} ${P(R * 0.36, a + 62)} Q${P(R * 0.52, a + 80)} ${P(R, a + 90)}`;
  }
  d += ' Z';
  const hole = R * 0.2;
  d += ` M${f1(cx + hole)},${cy} A${hole},${hole} 0 1 0 ${f1(cx - hole)},${cy} A${hole},${hole} 0 1 0 ${f1(cx + hole)},${cy} Z`;
  return d;
}
function appIcon(x, y, S, T) {
  const tile = linGrad([[0, T.dark ? '#3a3f4e' : '#343948'], [1, T.dark ? '#262a35' : '#1e222c']], 0, 1);
  const steel = linGrad([[0, '#f4f6fa'], [0.55, '#c3c9d5'], [1, '#8d95a7']], 1, 1);
  const cx = x + S / 2, cy = y + S / 2;
  return rect(x, y, S, S, S * 0.28, `url(#${tile})`) +
    rect(x + 0.5, y + 0.5, S - 1, S - 1, S * 0.28, 'none', { stroke: '#ffffff', op: 0.12 }) +
    `<path d="${shuriken(cx, cy, S * 0.4, 12)}" fill="url(#${steel})" fill-rule="evenodd"/>`;
}
function headerBar(T, view, o = {}) {
  let s = rect(0, 0, W, 52, 0, T.surface) + `<path d="M0,52.5 H${W}" stroke="${T.border}"/>`;
  s += appIcon(18, 12, 28, T);
  s += text(56, 31, 'Fankata', { size: 15, weight: 700, fill: T.text });
  // view switcher
  const sw = 248, sx = W / 2 - sw / 2;
  s += rect(sx, 9, sw, 34, 10, T.track);
  const segs = [['fans', 'fan', 'Fans'], ['curves', 'curve', 'Curves']];
  segs.forEach(([k, ic, label], i) => {
    const x = sx + 3 + i * (sw / 2 - 3), on = k === view, w = sw / 2 - 3;
    if (on) s += rect(x, 12, w, 28, 8, T.dark ? '#343847' : '#ffffff', { filter: 'seg' });
    const c = on ? T.text : T.muted, lw = tw(label, 13, { bold: true }) + 22;
    s += icon(ic, x + w / 2 - lw / 2, 18, 16, c);
    s += text(x + w / 2 - lw / 2 + 22, 30.5, label, { size: 13, weight: 700, fill: c });
  });
  if (o.menuOpen) s += `<circle cx="${W - 80}" cy="26" r="15" fill="${T.accentSoft}" stroke="${T.accent}" stroke-width="1.5"/>`;
  s += icon('dots', W - 88, 18, 16, o.menuOpen ? T.accent : T.muted);
  s += `<circle cx="${W - 32}" cy="26" r="12" fill="${T.track}"/>` + icon('x', W - 38, 20, 12, T.muted, 1.8);
  return s;
}
function baseDefs(T) {
  return `<filter id="card" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#0b0d14" flood-opacity="${T.shadow}"/></filter>` +
    `<filter id="lift" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="8" stdDeviation="14" flood-color="#0b0d14" flood-opacity="${T.shadow * 1.8}"/></filter>` +
    `<filter id="seg" x="-10%" y="-20%" width="120%" height="160%"><feDropShadow dx="0" dy="1" stdDeviation="1.5" flood-color="#0b0d14" flood-opacity="${T.shadow * 1.6}"/></filter>` +
    `<filter id="win" x="-10%" y="-10%" width="120%" height="125%"><feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#0b0d14" flood-opacity="${T.dark ? 0.6 : 0.18}"/></filter>` +
    `<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3"/></filter>`;
}

// ---------------------------------------------------------------- Fans view
function ripples(cx, cy, r0, T) {
  return [0, 1, 2].map(k => `<circle cx="${cx}" cy="${cy}" r="${r0 + k * 14}" fill="none" stroke="${T.accent}" stroke-width="${2.4 - k * 0.6}" opacity="${0.55 - k * 0.17}"/>`).join('');
}
// Simulated Speed pulse: 1 s at 100 %, 1 s at 30 %, RPM following with lag.
const PULSE = { len: 8, now: 3.3, low: 30 };
function pulseDuty(t) { return Math.floor(t) % 2 === 0 ? 100 : PULSE.low; }
function pulseTrace(f) {
  const out = []; let rpm = f.rpm; const max = MAXRPM[f.type], dt = 0.05;
  for (let t = 0; t <= PULSE.now + 1e-9; t += dt) {
    const target = max * (0.12 + 0.88 * pulseDuty(t) / 100);
    rpm += (target - rpm) * (1 - Math.exp(-dt / 0.35));
    out.push([t, rpm]);
  }
  return out;
}
function fanCard(x, y, w, h, f, T, selected, o = {}) {
  let s = rect(x, y, w, h, 18, T.surface, { filter: o.lifted ? 'lift' : 'card' });
  s += rect(x + 0.5, y + 0.5, w - 1, h - 1, 18, 'none', { stroke: selected ? T.accent : T.border, sw: selected ? 2 : 1 });
  const ia = f.managed ? linGrad([[0, T.illusA], [1, T.illusB]], 1, 1) : null;
  s += rect(x + 10, y + 10, w - 20, 134, 12, f.managed ? `url(#${ia})` : T.illusOff);
  const ic = nid('ic');
  defs.push(`<clipPath id="${ic}"><rect x="${x + 10}" y="${y + 10}" width="${w - 20}" height="134" rx="12"/></clipPath>`);
  // No "Managed" badge: the Probe group already says so (requirement 5.2.4).
  const badge = f.pulsing || !f.managed, ax = x + w / 2 + (badge ? 36 : 0);
  s += `<g clip-path="url(#${ic})">${f.pulsing ? ripples(ax, y + 77, 60, T) : ''}${fanArt(ax, y + 77, 100, f, T)}</g>`;
  if (f.pulsing) s += pill(x + 22, y + 22, 'Speed pulse', { bg: T.accentSoft, fg: T.accent, dot: T.accent }).s;
  else if (!f.managed) s += pill(x + 22, y + 22, 'System default', { bg: T.dark ? '#2a2e39' : '#e8eaf0', fg: T.muted, dot: T.faint }).s;
  // title + ring
  s += text(x + 22, y + 174, f.name, { size: 17, weight: 700, fill: T.text });
  s += text(x + 22, y + 194, f.driver, { size: 11.5, fill: T.muted, mono: true });
  s += ring(x + w - 46, y + 184, 22, f.duty, T, f.managed);
  // speed
  if (f.rpm != null) {
    s += icon('fan', x + 22, y + 214, 16, f.managed ? T.accent : T.faint);
    s += text(x + 46, y + 228, fmt(f.rpm), { size: 20, weight: 700, fill: T.text });
    s += text(x + 53 + tw(fmt(f.rpm), 20, { bold: true }), y + 228, 'RPM', { size: 12, weight: 700, fill: T.muted, ls: 0.5 });
  } else {
    s += icon('fan', x + 22, y + 214, 16, T.faint);
    s += text(x + 46, y + 227, 'Speed unknown', { size: 14, fill: T.faint });
  }
  s += `<path d="M${x + 18},${y + h - 50} H${x + w - 18}" stroke="${T.border}"/>`;
  const fy = y + h - 25;
  if (f.curve) {            // the assigned curve shows even while the service is off (like the app)
    const c = curve(f.curve);
    s += rect(x + 18, fy - 15, 56, 30, 7, T.input);
    s += chart({ x: x + 22, y: fy - 11, w: 48, h: 22, pts: c.pts, T, labels: false, grid: false, markers: false, sw: 2, fill: true });
    s += text(x + 84, fy - 1, c.name, { size: 13, weight: 700, fill: T.text });
    s += text(x + 84, fy + 14, 'curve', { size: 11, fill: T.muted });
  } else {
    s += text(x + 22, fy + 5, 'Not managed', { size: 13, fill: T.muted });
    s += text(x + w - 22 - 16 - 4, fy + 5, 'Assign a curve', { size: 13, weight: 700, fill: T.accent, anchor: 'end' });
    s += icon('chevRight', x + w - 36, fy - 7, 14, T.accent, 1.8);
  }
  return s;
}
function fansTitle(T, x, right) {
  let s = text(x, 102, 'Fans', { size: 28, weight: 700, fill: T.text });
  const managed = FANS.filter(f => f.managed).length;
  s += text(x + 78, 101, `${FANS.length} detected  ·  ${managed} managed by Fankata`, { size: 14, fill: T.muted });
  const chips = [['All', true], ['Managed', false], ['Unmanaged', false]];
  let cx = right;
  for (let i = chips.length - 1; i >= 0; i--) {
    const [l, on] = chips[i];
    const p = pill(cx, 80, l, { bg: on ? T.accentSoft : 'none', fg: on ? T.accent : T.muted, h: 30, size: 13, anchor: 'end', stroke: on ? null : T.border });
    s += p.s; cx -= p.w + 8;
  }
  const rb = button(cx - 4, 78, '', T, { ic: 'refresh', anchor: 'end' });
  return s + rb.s;
}
// Probe-pill thermometer (requirement 5.3.1): four 25 °C steps up to 100 °C.
// ≤25 °C: only the bulb, blue. Then yellow (⅓ stem), orange (⅔), red (full).
const TEMP_STEPS = { dark: ['#60a5fa', '#facc15', '#fb923c', '#f87171'], light: ['#2563eb', '#ca8a04', '#ea580c', '#dc2626'] };
const tempStep = v => (v <= 25 ? 0 : v <= 50 ? 1 : v <= 75 ? 2 : 3);
const tempColor = (v, T) => TEMP_STEPS[T.dark ? 'dark' : 'light'][tempStep(v)];
function thermometer(x, y, v, T) {      // 16 × 20 box, same geometry as the app (Thermometer.qml)
  const c = tempColor(v, T), k = tempStep(v);
  let s = rect(x + 5.5, y + 0.5, 5, 14, 2.5, 'none', { stroke: c, sw: 1 });   // tube: 1 px wall at x 5..11, y 0..15
  const fill = Math.round(10 * k / 3);                                       // visible stem: 0, 3, 7, 10 px
  if (fill > 0) s += rect(x + 7, y + 12 - fill, 2, fill + 3, 1, c);          // column, 1 px from each wall
  s += `<circle cx="${x + 8}" cy="${y + 16}" r="4" fill="${c}"/>`;           // bulb
  return s;
}

// Fans grouped by Probe (requirement 5.3). Unmanaged fans come last.
const PROBE_ORDER = [...SYS_PROBES, ...USER_PROBES].map(p => p.name);
const probeInfo = n => [...SYS_PROBES, ...USER_PROBES].find(p => p.name === n);
function groupHeader(x, y, w, key, count, T, o = {}) {
  const lit = !!o.lit;
  let s = '', px = x, h = 32;
  let inner, iw;
  if (key) {
    const p = probeInfo(key), val = `${f1(p.val)}°`;
    const nw = tw(key, 13, { mono: true }), vw = tw(val, 13, { bold: true });
    iw = 16 + 8 + nw + 10 + vw;
    inner = (ix) => thermometer(ix, y + 6, p.val, T) +
      text(ix + 24, y + 21, key, { size: 13, weight: 700, fill: lit ? T.accent : T.text, mono: true }) +
      text(ix + 24 + nw + 10, y + 21.5, val, { size: 13, weight: 700, fill: tempColor(p.val, T) });
  } else {
    const label = 'Unmanaged fans', lw = tw(label, 13, { bold: true });
    iw = 16 + 8 + lw;
    inner = (ix) => icon('fan', ix, y + 8, 16, lit ? T.accent : T.faint) +
      text(ix + 24, y + 21, label, { size: 13, weight: 700, fill: lit ? T.accent : T.muted });
  }
  const pw = iw + 28;
  if (lit) s += rect(px - 5, y - 5, pw + 10, h + 10, (h + 10) / 2, T.accent, { op: 0.22 });
  s += rect(px, y, pw, h, h / 2, lit ? T.accentSoft : T.surface, { stroke: lit ? T.accent : T.border, sw: lit ? 2 : 1 });
  s += inner(px + 14);
  const desc = o.hint || (key ? `${key.startsWith('sys.') ? probeInfo(key).desc : probeInfo(key).expr}  ·  ${count} fan${count === 1 ? '' : 's'}`
                                  : `System default  ·  ${count} fan${count === 1 ? '' : 's'}`);
  const tx = px + pw + 14;
  s += text(tx, y + 21, desc, { size: 12, weight: o.hint ? 700 : 400, fill: o.hint ? T.accent : T.muted, mono: !o.hint && key && !key.startsWith('sys.') });
  const lx = tx + tw(desc, 12, { mono: !o.hint && key && !key.startsWith('sys.'), bold: !!o.hint }) + 16;
  if (lx < x + w) s += `<path d="M${f1(lx)},${y + h / 2} H${x + w}" stroke="${lit ? T.accent : T.border}" stroke-width="${lit ? 1.5 : 1}"${lit ? '' : ' stroke-dasharray="1 0"'}/>`;
  return s;
}
function fanGroups(T, x0, width, cols, o = {}) {
  // like the app: up to three tiles share a row, each 380 × 290 scaled up to 2× (requirement 5.2.5)
  const gap = 20, cw = Math.min(760, (width - gap * (cols - 1)) / cols), ch = cw * 290 / 380, u = cw / 380;
  const tile = (x, y, f, sel, opt) => `<g transform="translate(${f1(x)} ${f1(y)}) scale(${u.toFixed(4)})">` +
    fanCard(0, 0, 380, 290, f, T, sel, opt) + `</g>`;
  const top = 128, scroll = o.scroll || 0;
  const groups = {};
  let fans = FANS.map(f => (o.override && f.name === o.override.name ? o.override : f));
  if (o.serviceOff) fans = fans.map(f => ({ ...f, managed: false }));    // firmware control; groups stay
  for (const f of fans) {
    if (o.drag && f.name === o.drag.fan) continue;
    const k = f.curve && f.probe ? f.probe : '';
    (groups[k] = groups[k] || []).push(f);
  }
  const dragFan = o.drag ? fans.find(f => f.name === o.drag.fan) : null;
  if (dragFan) (groups[o.drag.target] = groups[o.drag.target] || []);
  const keys = Object.keys(groups).sort((a, b) => (a === '') - (b === '') || PROBE_ORDER.indexOf(a) - PROBE_ORDER.indexOf(b));
  for (const k of keys) groups[k].sort((a, b) => a.name.localeCompare(b.name));
  const cid = nid('grid');
  defs.push(`<clipPath id="${cid}"><rect x="0" y="${top}" width="${x0 + width + 40}" height="${H - top}"/></clipPath>`);
  let s = '', floating = '';
  let y = top + 12 - scroll;
  for (const k of keys) {
    const list = groups[k].slice();
    let slot = -1;
    if (dragFan && k === o.drag.target) { slot = Math.min(o.drag.index, list.length); list.splice(slot, 0, null); }
    const lit = dragFan && k === o.drag.target;
    s += groupHeader(x0, y, width, k, groups[k].length, T, { lit, hint: lit ? o.drag.hint : null });
    y += 48;
    list.forEach((f, i) => {
      const cx = x0 + (i % cols) * (cw + gap), cy = y + Math.floor(i / cols) * (ch + gap);
      if (f === null) {
        s += rect(cx, cy, cw, ch, 18, T.alpha ? T.accentSoft : T.accentSoft, { stroke: T.accent, sw: 2, dash: '8 6', op: 0.9 });
        const [dx, dy] = o.drag.offset;
        floating = `<g transform="rotate(-2 ${cx + cw / 2 + dx} ${cy + ch / 2 + dy})">` +
          tile(cx + dx, cy + dy, dragFan, false, { lifted: true }) + `</g>` +
          cursor(cx + cw / 2 + dx + 10, cy + 60 + dy);
      } else {
        s += tile(cx, cy, f, o.selected === f.name);
      }
    });
    y += Math.ceil(list.length / cols) * (ch + gap) - gap + 32;
  }
  return `<g clip-path="url(#${cid})">${s}${floating}</g>`;
}
function fansView(T, o = {}) {
  let s = headerBar(T, 'fans', { menuOpen: o.appMenu });
  let body = fansTitle(T, 32, W - 32) + fanGroups(T, 32, W - 64, 3, o);
  if (o.serviceOff) {
    s += serviceBanner(T);
    body = `<g transform="translate(0 44)">${body}</g>`;
  }
  s += body;
  if (o.appMenu) s += appMenu(T, true, { hover: o.menuHover });
  return s;
}
// Read-only banner while the service is off (requirement 1.10, 4.6)
function serviceBanner(T) {
  const msg = 'Fan control is off: fans are under firmware control, and Fankata is showing live readings only.';
  const mw = tw(msg, 13, { bold: true }), bw = tw('Turn on', 13, { bold: true }) + 48;
  const x = (W - (16 + 12 + mw + 12 + bw)) / 2;
  let s = rect(0, 53, W, 44, 0, T.warnSoft);
  s += icon('warn', x, 67, 16, T.warn);
  s += text(x + 28, 79.5, msg, { size: 13, weight: 700, fill: T.warn });
  s += button(x + 28 + mw + 12, 61, 'Turn on', T, { ic: 'check', h: 28 }).s;
  return s;
}
// Title-bar ⋮ menu: the service switch, Troubleshoot fans (requirement 4.4), theme, About, Quit
function appMenu(T, on = true, o = {}) {
  const mw = 300, x = W - 64 - mw + 40, y = 50, mh = 348;
  let s = rect(x, y, mw, mh, 14, T.dark ? '#262a35' : T.surface, { filter: 'lift' });
  s += rect(x + 0.5, y + 0.5, mw - 1, mh - 1, 14, 'none', { stroke: T.border });
  if (!o.hover) s += rect(x + 6, y + 6, mw - 12, 58, 10, T.dark ? '#2f3442' : '#f3f4f8');
  s += rect(x + 18, y + 25, 20, 20, 6, on ? T.accent : 'none', on ? {} : { stroke: T.borderStrong, sw: 1.6 });
  if (on) s += icon('check', x + 21, y + 28, 14, '#ffffff', 2.2);
  s += text(x + 50, y + 30, 'Fan control service', { size: 14, weight: 700, fill: T.text });
  s += text(x + 50, y + 49, on ? 'On · fans follow their curves' : 'Off · fans under firmware control', { size: 12, fill: T.muted });
  if (o.hover === 'troubleshoot') s += rect(x + 6, y + 70, mw - 12, 42, 10, T.dark ? '#2f3442' : '#f3f4f8');
  s += icon('lifebuoy', x + 20, y + 83, 16, o.hover === 'troubleshoot' ? T.accent : T.muted);
  s += text(x + 50, y + 96, 'Troubleshoot fans…', { size: 14, weight: 700, fill: T.text });
  s += `<path d="M${x + 12},${y + 120.5} H${x + mw - 12}" stroke="${T.border}"/>`;
  [['Match system', false], ['Dark', T.dark], ['Light', !T.dark]].forEach(([label, sel], i) => {
    const yy = y + 128 + i * 40;
    s += `<circle cx="${x + 28}" cy="${yy + 19}" r="10" fill="${sel ? T.accent : 'none'}" stroke="${sel ? 'none' : T.borderStrong}" stroke-width="1.6"/>`;
    if (sel) s += `<circle cx="${x + 28}" cy="${yy + 19}" r="4" fill="#ffffff"/>`;
    s += text(x + 50, yy + 24, label, { size: 14, weight: 700, fill: T.text });
  });
  s += `<path d="M${x + 12},${y + 252.5} H${x + mw - 12}" stroke="${T.border}"/>`;
  s += text(x + 18, y + 284, 'About Fankata', { size: 14, weight: 700, fill: T.text });
  s += text(x + 18, y + 324, 'Quit', { size: 14, weight: 700, fill: T.text });
  return s;
}
function selectBox(x, y, w, T, inner, o = {}) {
  let s = rect(x, y, w, 46, 12, T.input, { stroke: o.focus ? T.accent : T.border, sw: o.focus ? 2 : 1 });
  s += inner;
  if (o.clear) {
    s += `<circle cx="${x + w - 58}" cy="${y + 23}" r="11" fill="${T.track}"/>` + icon('x', x + w - 63, y + 18, 10, T.muted, 1.8);
    s += `<path d="M${x + w - 38},${y + 12} V${y + 34}" stroke="${T.border}"/>`;
  }
  s += icon('chevDown', x + w - 28, y + 15, 16, T.muted);
  return s;
}
function fanDetail(T, o = {}) {
  const base = FANS[0], c = curve(base.curve);
  const trace = o.pulse ? pulseTrace(base) : null;
  const f = o.pulse ? { ...base, pulsing: true, duty: pulseDuty(PULSE.now), rpm: Math.round(trace[trace.length - 1][1] / 10) * 10 } : base;
  let s = headerBar(T, 'fans');
  const panelX = W - 450;
  s += fansTitle(T, 32, panelX - 28);
  s += fanGroups(T, 32, panelX - 32 - 28, 2, { selected: base.name, override: f });
  // panel
  s += rect(panelX, 53, 450, H - 53, 0, T.surface, { filter: 'lift' });
  s += `<path d="M${panelX + 0.5},53 V${H}" stroke="${T.border}"/>`;
  const x0 = panelX + 28, pw = 394;
  s += text(x0, 86, 'FAN DETAILS', { size: 11, weight: 700, fill: T.faint, ls: 1.2 });
  s += `<circle cx="${x0 + pw - 12}" cy="81" r="14" fill="${T.track}"/>` + icon('x', x0 + pw - 18, 75, 12, T.muted, 1.8);
  // device actions menu button (vertical ellipsis), left of close
  const mcx = x0 + pw - 48;
  s += o.menu
    ? `<circle cx="${mcx}" cy="81" r="14" fill="${T.accentSoft}" stroke="${T.accent}" stroke-width="1.5"/>` + icon('dots', mcx - 7, 74, 14, T.accent)
    : `<circle cx="${mcx}" cy="81" r="14" fill="${T.track}"/>` + icon('dots', mcx - 7, 74, 14, T.muted);
  const ia = linGrad([[0, T.illusA], [1, T.illusB]], 1, 1);
  s += rect(x0, 104, pw, 128, 14, `url(#${ia})`);
  const ic = nid('ic');
  defs.push(`<clipPath id="${ic}"><rect x="${x0}" y="104" width="${pw}" height="128" rx="14"/></clipPath>`);
  s += `<g clip-path="url(#${ic})">${o.pulse ? ripples(x0 + pw / 2, 168, 60, T) : ''}${fanArt(x0 + pw / 2, 168, 100, f, T)}</g>`;
  s += (o.pulse ? pill(x0 + 12, 116, 'Speed pulse', { bg: T.accentSoft, fg: T.accent, dot: T.accent })
    : { s: '' }).s;
  s += text(x0, 266, f.name, { size: 22, weight: 700, fill: T.text });
  s += icon('pencil', x0 + tw(f.name, 22, { bold: true }) + 10, 252, 15, T.muted);
  s += text(x0, 287, 'nct6798 · fan2_input · pwm2', { size: 11.5, fill: T.muted, mono: true });
  // type
  const tp = pill(x0 + pw, 256, 'Case fan · detected    ', { bg: T.input, fg: T.muted, h: 28, size: 12, anchor: 'end', stroke: T.border, bold: false });
  s += tp.s + icon('chevDown', x0 + pw - 22, 263, 12, T.muted);
  // stats
  const stats = [[fmt(f.rpm), 'RPM'], [`${f.duty} %`, 'duty cycle'], [`${f1(f.val)} °C`, f.probe]];
  const sw3 = (pw - 16) / 3;
  stats.forEach(([v, l], i) => {
    const sx = x0 + i * (sw3 + 8);
    s += rect(sx, 304, sw3, 60, 12, T.input);
    s += text(sx + 14, 332, v, { size: 19, weight: 700, fill: i === 2 ? heat(f.val) : T.text });
    s += text(sx + 14, 351, l, { size: 11.5, fill: T.muted, mono: i === 2 });
  });
  s += o.pulse ? '<g opacity="0.45">' : '<g>';
  s += text(x0, 398, 'Curve', { size: 13, weight: 700, fill: T.text });
  s += text(x0 + pw, 398, 'Clear to return to system default', { size: 11.5, fill: T.faint, anchor: 'end' });
  let inner = rect(x0 + 10, 415, 52, 30, 7, T.surface);
  inner += chart({ x: x0 + 14, y: 419, w: 44, h: 22, pts: c.pts, T, labels: false, grid: false, markers: false, sw: 2 });
  inner += text(x0 + 74, 435, c.name, { size: 14, weight: 700, fill: T.text });
  inner += text(x0 + 74 + tw(c.name, 14, { bold: true }) + 8, 435, `${c.pts.length} points`, { size: 12, fill: T.muted });
  s += selectBox(x0, 407, pw, T, inner, { clear: true });
  s += text(x0, 482, 'Probe', { size: 13, weight: 700, fill: T.text });
  let pin = icon('thermo', x0 + 14, 507, 16, heat(f.val));
  pin += text(x0 + 38, 519, f.probe, { size: 13, fill: T.text, mono: true });
  pin += text(x0 + 38 + tw(f.probe, 13, { mono: true }) + 10, 519, 'CPU package · k10temp', { size: 12, fill: T.muted });
  pin += text(x0 + pw - 44, 519.5, `${f1(f.val)} °C`, { size: 13, weight: 700, fill: T.text, anchor: 'end' });
  s += selectBox(x0, 492, pw, T, pin);
  s += '</g>';
  if (o.pulse) return s + pulsePanel(x0, 558, pw, 222, base, trace, T);
  // live chart
  s += rect(x0, 558, pw, 222, 14, T.input);
  s += text(x0 + 16, 584, 'Live', { size: 13, weight: 700, fill: T.text });
  s += `<circle cx="${x0 + 54}" cy="580" r="4" fill="${T.ok}"/>`;
  s += text(x0 + pw - 16, 584, `${f1(f.val)} °C  →  ${f.duty} %`, { size: 13, weight: 700, fill: heat(f.val), anchor: 'end' });
  s += chart({ x: x0 + 4, y: 594, w: pw - 12, h: 182, pts: c.pts, T, mr: 4, sw: 2.6, ops: [{ v: f.val }] });
  if (o.menu) s += fanMenu(x0 + pw, 100, T);
  return s;
}
function fanMenu(right, y, T) {
  const mw = 300, x = right - mw, mh = 76;
  let s = rect(x, y, mw, mh, 14, T.dark ? '#262a35' : T.surface, { filter: 'lift' });
  s += rect(x + 0.5, y + 0.5, mw - 1, mh - 1, 14, 'none', { stroke: T.border });
  s += rect(x + 6, y + 6, mw - 12, mh - 12, 10, T.dark ? '#2f3442' : '#f3f4f8');
  s += `<circle cx="${x + 32}" cy="${y + 38}" r="15" fill="${T.accentSoft}"/>` + icon('pulse', x + 24, y + 30, 16, T.accent, 1.8);
  s += text(x + 58, y + 34, 'Speed pulse (8 sec)', { size: 14, weight: 700, fill: T.text });
  s += text(x + 58, y + 53, 'Spot this fan by ramping its speed', { size: 12, fill: T.muted });
  return s;
}
function pulsePanel(x, y, w, h, f, trace, T) {
  let s = rect(x, y, w, h, 14, T.input);
  s += `<circle cx="${x + 20}" cy="${y + 22}" r="4" fill="${T.accent}"/>`;
  s += `<circle cx="${x + 20}" cy="${y + 22}" r="8" fill="${T.accent}" opacity="0.25"/>`;
  s += text(x + 34, y + 27, 'Speed pulse', { size: 13, weight: 700, fill: T.text });
  const left = Math.ceil(PULSE.len - PULSE.now);
  s += text(x + 34 + tw('Speed pulse', 13, { bold: true }) + 10, y + 27, `${left} s left`, { size: 12.5, fill: T.muted });
  s += button(x + w - 12, y + 9, 'Stop', T, { anchor: 'end', h: 30, danger: true }).s;
  const px = x + 46, py = y + 54, pw = w - 62, ph = 110;
  const X = t => px + t / PULSE.len * pw, Yd = d => py + ph - d / 100 * ph;
  const max = MAXRPM[f.type], Yr = r => py + ph - r / max * ph;
  for (let r = 0; r <= max; r += 500) {
    s += `<path d="M${px},${f1(Yr(r))} H${px + pw}" stroke="${T.grid}"/>`;
    s += text(px - 8, Yr(r) + 4, r ? `${r / 1000}k` : '0', { size: 10.5, fill: T.faint, anchor: 'end' });
  }
  for (let t = 0; t <= PULSE.len; t += 2) s += text(X(t), py + ph + 18, `${t} s`, { size: 10.5, fill: T.faint, anchor: 'middle' });
  // commanded duty: full pattern, the future part dimmer
  let d = '';
  for (let t = 0; t < PULSE.len; t++) {
    const v = pulseDuty(t);
    d += `${d ? ' L' : 'M'}${f1(X(t))},${f1(Yd(v))} L${f1(X(t + 1))},${f1(Yd(v))}`;
  }
  s += `<path d="${d}" fill="none" stroke="${T.muted}" stroke-width="1.5" stroke-dasharray="4 3" opacity="0.7"/>`;
  s += rect(X(PULSE.now), py, X(PULSE.len) - X(PULSE.now), ph, 0, T.input, { op: 0.55 });
  // measured RPM
  const g = linGrad([[0, T.accent, 0.3], [1, T.accent, 0]], 0, 1);
  const line = trace.map(([t, r], i) => `${i ? 'L' : 'M'}${f1(X(t))},${f1(Yr(r))}`).join(' ');
  const last = trace[trace.length - 1];
  s += `<path d="${line} L${f1(X(last[0]))},${py + ph} L${px},${py + ph} Z" fill="url(#${g})"/>`;
  s += `<path d="${line}" fill="none" stroke="${T.accent}" stroke-width="2.6" stroke-linejoin="round"/>`;
  s += `<path d="M${f1(X(PULSE.now))},${py - 4} V${py + ph}" stroke="${T.text}" stroke-width="1" opacity="0.35"/>`;
  s += `<circle cx="${f1(X(last[0]))}" cy="${f1(Yr(last[1]))}" r="9" fill="${T.accent}" opacity="0.25"/>`;
  s += `<circle cx="${f1(X(last[0]))}" cy="${f1(Yr(last[1]))}" r="4.5" fill="${T.accent}" stroke="${T.surface}" stroke-width="2"/>`;
  // wiring check
  const cy = y + h - 22;
  s += `<circle cx="${x + 22}" cy="${cy - 4}" r="9" fill="${T.okSoft}"/>` + icon('check', x + 16, cy - 10, 12, T.ok, 2);
  s += text(x + 40, cy, 'fan2 is following the pulse. This control drives this fan.', { size: 12, weight: 700, fill: T.ok });
  return s;
}

// ---------------------------------------------------------------- Curves view
function gallery(T, selName) {
  let s = rect(0, 53, 300, H - 53, 0, T.side) + `<path d="M300.5,53 V${H}" stroke="${T.border}"/>`;
  s += text(24, 92, 'Curves', { size: 20, weight: 700, fill: T.text });
  s += text(24 + 78, 92, `${CURVES.length}`, { size: 14, fill: T.faint });
  s += button(276, 70, 'New', T, { ic: 'plus', anchor: 'end', h: 32 }).s;
  CURVES.forEach((c, i) => {
    const x = 20, y = 112 + i * 112, w = 260, h = 100, on = c.name === selName;
    s += rect(x, y, w, h, 14, T.surface, on ? {} : { filter: 'card' });
    s += rect(x + 0.5, y + 0.5, w - 1, h - 1, 14, on ? T.accentSoft : 'none', { stroke: on ? T.accent : T.border, sw: on ? 2 : 1, op: 1 });
    if (on) s += rect(x + 1.5, y + 1.5, w - 3, h - 3, 13, T.surface, { op: T.dark ? 0.35 : 0.55 });
    s += chart({ x: x + 10, y: y + 10, w: w - 20, h: 52, pts: c.pts, T, labels: false, grid: false, mr: 2.4, sw: 2.2, bg: T.input });
    s += text(x + 12, y + 86, c.name, { size: 14, weight: 700, fill: T.text });
    const used = fansUsing(c.name).length;
    s += text(x + w - 12, y + 86, `${c.pts.length} pts · ${used ? `${used} fan${used > 1 ? 's' : ''}` : 'unused'}`, { size: 12, fill: used ? T.muted : T.faint, anchor: 'end' });
  });
  return s;
}
function probeRow(x, y, w, p, T, custom) {
  let s = '';
  s += text(x + 12, y + 22, p.name, { size: 13, weight: 700, fill: T.text, mono: true });
  s += text(x + 12, y + 40, custom ? p.expr : p.desc, { size: custom ? 11 : 11.5, fill: T.muted, mono: custom });
  s += text(x + w - 12, y + 24, `${f1(p.val)}°`, { size: 16, weight: 700, fill: heat(p.val), anchor: 'end' });
  s += sparkline(x + w - 74, y + 32, 60, 12, p.seed, heat(p.val), 1.4, false, T);
  return s;
}
function probesPanel(T, x) {
  const w = W - x;
  let s = rect(x, 53, w, H - 53, 0, T.surface) + `<path d="M${x + 0.5},53 V${H}" stroke="${T.border}"/>`;
  const x0 = x + 18, iw = w - 36;
  s += icon('thermo', x0, 78, 18, T.accent);
  s += text(x0 + 26, 92, 'Probes', { size: 17, weight: 700, fill: T.text });
  s += button(x0 + iw - 40, 72, '', T, { ic: 'plus', h: 32 }).s;
  s += button(x0 + iw, 72, '', T, { ic: 'panel', anchor: 'end', h: 32 }).s;
  s += text(x0, 132, 'SYSTEM', { size: 11, weight: 700, fill: T.faint, ls: 1.2 });
  s += text(x0 + iw, 132, 'read-only', { size: 11, fill: T.faint, anchor: 'end' });
  SYS_PROBES.forEach((p, i) => {
    const y = 142 + i * 54;
    if (i) s += `<path d="M${x0 + 12},${y} H${x0 + iw - 12}" stroke="${T.border}"/>`;
    s += probeRow(x0 - 12 + 12, y + 2, iw, p, T, false);
  });
  const cy = 142 + SYS_PROBES.length * 54 + 26;
  s += text(x0, cy, 'CUSTOM', { size: 11, weight: 700, fill: T.faint, ls: 1.2 });
  USER_PROBES.forEach((p, i) => {
    const y = cy + 10 + i * 62;
    s += rect(x0, y, iw, 54, 12, T.input, { stroke: T.border });
    s += probeRow(x0, y + 2, iw, p, T, true);
  });
  const by = cy + 10 + USER_PROBES.length * 62 + 4;
  s += rect(x0, by, iw, 40, 12, 'none', { stroke: T.borderStrong, dash: '5 4', sw: 1.2 });
  s += icon('plus', x0 + iw / 2 - 64, by + 12, 16, T.accent);
  s += text(x0 + iw / 2 - 42, by + 25, 'New custom probe', { size: 13, weight: 700, fill: T.accent });
  return s;
}
function probesRail(T, x) {
  let s = rect(x, 53, W - x, H - 53, 0, T.surface) + `<path d="M${x + 0.5},53 V${H}" stroke="${T.border}"/>`;
  const cx = x + (W - x) / 2;
  s += button(cx - 17, 72, '', T, { ic: 'panel', h: 34 }).s;
  s += icon('thermo', cx - 9, 128, 18, T.accent);
  s += text(cx + 5, 212, 'Probes', { size: 14, weight: 700, fill: T.muted, anchor: 'middle', rot: -90 });
  return s;
}
function pointsTable(x, y, w, c, T, o = {}) {
  const { err } = o, sel = o.hover && o.hover.remove != null ? o.hover.remove : -1;
  let s = text(x, y, 'Points', { size: 15, weight: 700, fill: T.text });
  s += text(x + 58, y, 'Click a dot to remove it, click empty space on the graph to add one, or type values below.', { size: 12.5, fill: T.muted });
  const ty = y + 22, lw = 76, addW = 8, n = c.pts.length;
  const colW = (w - lw - addW) / n;
  s += rect(x, ty, w, 104, 14, T.surface, { stroke: T.border });
  if (sel >= 0) s += rect(x + lw + sel * colW + 3, ty + 4, colW - 6, 96, 10, T.errSoft);
  s += text(x + 16, ty + 38, 'Temp', { size: 12.5, weight: 700, fill: T.muted });
  s += text(x + 16, ty + 80, 'Speed', { size: 12.5, weight: 700, fill: T.muted });
  c.pts.forEach(([vx, vy], i) => {
    const cx = x + lw + i * colW + 6, cw = colW - 12;
    const bad = err && err.i === i;
    s += rect(cx, ty + 14, cw, 36, 9, T.input, { stroke: T.border });
    s += `<circle cx="${cx + 14}" cy="${ty + 32}" r="4" fill="${heat(vx)}"/>`;
    s += text(cx + cw - 12, ty + 37, `${vx} °C`, { size: 13.5, weight: 700, fill: T.text, anchor: 'end' });
    s += rect(cx, ty + 56, cw, 36, 9, bad ? T.errSoft : T.input, { stroke: bad ? T.err : T.border, sw: bad ? 2 : 1 });
    s += text(cx + cw - 12, ty + 79, `${bad ? err.typed : vy} %`, { size: 13.5, weight: 700, fill: bad ? T.err : T.text, anchor: 'end' });
    if (bad) s += icon('warn', cx + 8, ty + 66, 15, T.err);
  });
  if (err) {
    const ey = ty + 118;
    s += rect(x, ey, w, 38, 10, T.errSoft);
    s += icon('warn', x + 14, ey + 11, 16, T.err);
    s += text(x + 40, ey + 24, err.msg, { size: 13, weight: 700, fill: T.err });
    s += text(x + w - 14, ey + 24, 'Not applied', { size: 12, fill: T.err, anchor: 'end', op: 0.8 });
  }
  return s;
}
function editor(T, x0, w, c, o = {}) {
  let s = '';
  s += text(x0, 100, c.name, { size: 28, weight: 700, fill: T.text });
  s += icon('pencil', x0 + tw(c.name, 28, { bold: true }) * 1.1 + 10, 83, 16, T.muted);
  const used = fansUsing(c.name);
  s += text(x0, 126, used.length ? 'Used by' : 'Not used by any fan', { size: 13, fill: T.muted });
  let ux = x0 + 56;
  used.forEach(f => {
    const p = pill(ux, 111, f.name, { bg: T.input, fg: T.text, h: 22, size: 12, stroke: T.border, dot: heat(f.val) });
    s += p.s; ux += p.w + 6;
  });
  const more = button(x0 + w, 76, '', T, { ic: 'more', anchor: 'end' });
  s += o.menu ? rect(x0 + w - more.w, 76, more.w, 34, 10, T.accentSoft, { stroke: T.accent }) + icon('more', x0 + w - more.w + 9, 85, 16, T.accent) : more.s;
  const chH = o.chartH || 330;
  s += rect(x0, 146, w, chH, 16, T.surface, { filter: 'card' });
  s += rect(x0 + 0.5, 146.5, w - 1, chH - 1, 16, 'none', { stroke: T.border });
  const ops = used.map((f, i) => ({ v: f.val, label: `${f.name} · ${f1(f.val)}°`, ly: 166 + i * 34 }));
  s += chart({ x: x0 + 10, y: 156, w: w - 20, h: chH - 20, pts: c.pts, T, hover: o.hover || {}, ops, mr: 6, sw: 3.4, floor: c.allowZero ? 0 : FLOOR });
  s += pointsTable(x0, 146 + chH + 38, w, c, T, o);
  if (o.menu) s += curveMenu(x0 + w, 118, c, used, T);
  return s;
}
function curveMenu(right, y, c, used, T) {
  const mw = 280, x = right - mw, mh = 182;
  let s = rect(x, y, mw, mh, 14, T.dark ? '#262a35' : T.surface, { filter: 'lift' });
  s += rect(x + 0.5, y + 0.5, mw - 1, mh - 1, 14, 'none', { stroke: T.border });
  // Duplicate
  s += icon('copy', x + 20, y + 16, 16, T.text);
  s += text(x + 50, y + 29, 'Duplicate curve', { size: 14, weight: 700, fill: T.text });
  s += `<path d="M${x + 12},${y + 50.5} H${x + mw - 12}" stroke="${T.border}"/>`;
  y += 50;
  // Allow zero (checkbox item)
  s += rect(x + 6, y + 6, mw - 12, 60, 10, T.dark ? '#2f3442' : '#f3f4f8');
  const on = !!c.allowZero;
  s += rect(x + 18, y + 20, 20, 20, 6, on ? T.accent : 'none', on ? {} : { stroke: T.borderStrong, sw: 1.6 });
  if (on) s += icon('check', x + 21, y + 23, 14, '#ffffff', 2.2);
  s += text(x + 50, y + 31, 'Allow zero', { size: 14, weight: 700, fill: T.text });
  s += text(x + 50, y + 50, `Speeds below ${FLOOR} % are allowed`, { size: 12, fill: T.muted });
  s += `<path d="M${x + 12},${y + 74.5} H${x + mw - 12}" stroke="${T.border}"/>`;
  // Delete
  const dis = used.length > 0, dc = dis ? T.faint : T.err;
  s += icon('trash', x + 20, y + 90, 16, dc);
  s += text(x + 50, y + 103, 'Delete curve', { size: 14, weight: 700, fill: dc });
  if (dis) s += text(x + 50, y + 121, `Used by ${used.length} fan${used.length > 1 ? 's' : ''}`, { size: 12, fill: T.faint });
  return s;
}
function curvesView(T, o = {}) {
  const c = curve(o.curve || 'Balanced');
  let s = headerBar(T, 'curves');
  s += gallery(T, c.name);
  const panelX = o.collapsed ? W - 56 : W - 320;
  s += editor(T, 332, panelX - 332 - 32, c, o);
  s += o.collapsed ? probesRail(T, panelX) : probesPanel(T, panelX);
  return s;
}

// ---------------------------------------------------------------- Probe dialog
function probeDialog(T, err) {
  let s = curvesView(T, {});
  s += `<rect width="${W}" height="${H}" fill="#0b0d14" opacity="${T.dark ? 0.55 : 0.32}"/>`;
  const dw = 560, dh = err ? 520 : 490, dx = (W - dw) / 2, dy = (H - dh) / 2 + 14;
  s += rect(dx, dy, dw, dh, 20, T.surface, { filter: 'lift' });
  const x0 = dx + 30, iw = dw - 60;
  s += text(x0, dy + 46, 'New custom probe', { size: 21, weight: 700, fill: T.text });
  s += `<circle cx="${x0 + iw - 12}" cy="${dy + 39}" r="14" fill="${T.track}"/>` + icon('x', x0 + iw - 18, dy + 33, 12, T.muted, 1.8);
  // name
  let y = dy + 84;
  s += text(x0, y, 'Name', { size: 12.5, weight: 700, fill: T.muted });
  s += rect(x0, y + 10, iw, 42, 11, T.input, { stroke: T.border });
  s += text(x0 + 14, y + 37, 'blend', { size: 15, fill: T.text, mono: true });
  s += `<circle cx="${x0 + iw - 20}" cy="${y + 31}" r="9" fill="${T.okSoft}"/>` + icon('check', x0 + iw - 26, y + 25, 12, T.ok, 2);
  s += text(x0, y + 72, 'Starts with a letter, then letters, digits and _ only. Unique among custom probes.', { size: 12, fill: T.muted });
  // expression
  y += 104;
  s += text(x0, y, 'Expression', { size: 12.5, weight: 700, fill: T.muted });
  s += rect(x0, y + 10, iw, 56, 11, T.input, { stroke: err ? T.err : T.accent, sw: 2 });
  const toks = err
    ? [['sys.cpu', 'p'], [' * ', 'o'], ['.9', 'n'], [' + ', 'o'], ['sys.gppu', 'e'], [' / ', 'o'], ['10', 'n']]
    : [['sys.cpu', 'p'], [' * ', 'o'], ['.9', 'n'], [' + ', 'o'], ['sys.gpu', 'p'], [' / ', 'o'], ['10', 'n']];
  let tx = x0 + 16; const ty = y + 44, cw = 15 * 0.602;
  for (const [t, k] of toks) {
    const tt = t.trim(), pre = (t.length - t.trimStart().length) * cw;
    tx += pre;
    const w = tt.length * cw;
    if (k === 'p') s += rect(tx - 4, ty - 17, w + 8, 24, 6, T.accentSoft);
    if (k === 'e') {
      let d = `M${tx},${ty + 5}`;
      for (let i = 0; i < w; i += 4) d += ` l2,${i / 4 % 2 ? -2.5 : 2.5}`;
      s += `<path d="${d}" fill="none" stroke="${T.err}" stroke-width="1.5"/>`;
    }
    const fill = { p: T.accent, o: T.muted, n: T.dark ? '#fdba74' : '#c2410c', e: T.err }[k];
    s += text(tx, ty, tt, { size: 15, fill, mono: true, weight: k === 'p' || k === 'e' ? 700 : 400 });
    tx += w + (t.length - t.trimEnd().length) * cw;
  }
  s += `<path d="M${tx + 2},${ty - 16} V${ty + 5}" stroke="${T.text}" stroke-width="1.5"/>`;
  y += 66;
  if (err) {
    y += 8;
    s += icon('warn', x0, y + 2, 15, T.err);
    s += text(x0 + 22, y + 14, 'Unknown probe “sys.gppu”. Did you mean', { size: 12.5, weight: 700, fill: T.err });
    const dm = pill(x0 + 22 + tw('Unknown probe “sys.gppu”. Did you mean', 12.5, { bold: true }) + 8, y - 2, 'sys.gpu', { bg: T.accentSoft, fg: T.accent, h: 22, size: 12, mono: true });
    s += dm.s + text(x0 + 30 + tw('Unknown probe “sys.gppu”. Did you mean', 12.5, { bold: true }) + dm.w + 2, y + 14, '?', { size: 12.5, weight: 700, fill: T.err });
    y += 22;
  }
  // insert chips
  y += 18;
  s += text(x0, y + 16, 'Insert', { size: 12, weight: 700, fill: T.faint });
  let chx = x0 + 50;
  for (const n of ['sys.cpu', 'sys.gpu', 'sys.nvme', 'sys.coolant', 'loop']) {
    const p = pill(chx, y, n, { bg: T.surface, fg: T.accent, h: 24, size: 11.5, mono: true, stroke: T.border, bold: false });
    s += p.s; chx += p.w + 6;
  }
  s += text(chx + 2, y + 16, '…', { size: 13, fill: T.faint });
  y += 32;
  let ox = x0 + 50;
  for (const op of ['+', '-', '*', '/', '^', '(', ')']) {
    s += rect(ox, y, 30, 26, 7, T.input, { stroke: T.border });
    s += text(ox + 15, y + 18, op, { size: 14, fill: T.text, mono: true, anchor: 'middle', weight: 700 });
    ox += 36;
  }
  s += text(ox + 6, y + 18, 'precedence: ^  then * /  then + -', { size: 11.5, fill: T.faint });
  // result
  y += 44;
  s += rect(x0, y, iw, 76, 14, err ? T.input : T.illusA, err ? { stroke: T.border } : {});
  s += text(x0 + 18, y + 26, 'Current value', { size: 12, weight: 700, fill: T.muted });
  if (err) {
    s += text(x0 + 18, y + 58, '—', { size: 26, weight: 700, fill: T.faint });
    s += text(x0 + 52, y + 56, 'Fix the expression to see a live value', { size: 13, fill: T.faint });
  } else {
    s += text(x0 + 18, y + 60, '53.6 °C', { size: 28, weight: 700, fill: heat(53.6) });
    s += text(x0 + 130, y + 58, '= 54.2 × 0.9 + 48.0 / 10', { size: 12, fill: T.muted, mono: true });
    s += sparkline(x0 + iw - 150, y + 18, 132, 40, 7, heat(53.6), 2, true, T);
  }
  // buttons
  y += 96;
  const pb = button(x0 + iw, y, 'Create probe', T, { primary: !err, anchor: 'end', h: 38, disabled: err });
  s += pb.s + button(x0 + iw - pb.w - 10, y, 'Cancel', T, { anchor: 'end', h: 38 }).s;
  return s;
}

// ---------------------------------------------------------------- Troubleshoot fans (requirement 4.7)
// Tiny Markdown subset, as the app renders it: ### headings, - bullets, paragraphs,
// ``` code blocks (with a Copy button), and inline **bold**, `code`, [links](url).
function inlineRuns(src) {
  const runs = [], re = /\*\*(.+?)\*\*|`(.+?)`|\[(.+?)\]\((.+?)\)|\*(.+?)\*/g;
  let i = 0, m;
  while ((m = re.exec(src))) {
    if (m.index > i) runs.push({ t: src.slice(i, m.index) });
    if (m[1]) runs.push({ t: m[1], b: true });
    else if (m[2]) runs.push({ t: m[2], code: true });
    else if (m[3]) runs.push({ t: m[3], link: true });
    else runs.push({ t: m[5], i: true });
    i = re.lastIndex;
  }
  if (i < src.length) runs.push({ t: src.slice(i) });
  return runs;
}
// real advance widths from the renderer's fonts (measured at 100 px between two bars), cached
const MW = new Map();
function mw(str, size, o = {}) {
  const key = `${o.mono ? 'm' : 's'}${o.bold ? 'b' : ''}|${str}`;
  if (!MW.has(key)) {
    const box = s2 => new Resvg(`<svg xmlns="http://www.w3.org/2000/svg" width="8000" height="200"><text x="10" y="120" font-family="${o.mono ? MONO : SANS}" font-size="100" font-weight="${o.bold ? 700 : 400}">${esc(s2)}</text></svg>`,
      { font: { loadSystemFonts: true } }).innerBBox().width;
    MW.set(key, (box(`|${str}|`) - box('||')) / 100);
  }
  return MW.get(key) * size;
}
function flow(x, y, w, src, T, o = {}) {      // word-wraps inline runs; returns { s, h }
  const size = o.size || 13, lh = o.lh || 21;
  const words = [];
  for (const r of inlineRuns(src)) {
    if (r.code) { words.push({ ...r, w: mw(r.t, size - 1, { mono: true }) + 10 }); continue; }
    r.t.split(/(\s+)/).filter(Boolean).forEach(t => words.push({ ...r, t, sp: /^\s+$/.test(t), w: mw(/^\s+$/.test(t) ? ' ' : t, size, { bold: r.b || r.link }) }));
  }
  let s = '', cx = 0, cy = 0;
  for (const wd of words) {
    if (wd.sp) {
      if (cx > 0 && wd.link) s += `<path d="M${f1(x + cx)},${y + cy + 3} H${f1(x + cx + wd.w)}" stroke="${T.accent}" stroke-opacity=".5"/>`;
      if (cx > 0) cx += wd.w;
      continue;
    }
    if (cx + wd.w > w && cx > 0) { cx = 0; cy += lh; }
    const bx = x + cx, by = y + cy;
    if (wd.code) {
      s += rect(bx, by - size + 0.5, wd.w, size + 6, 5, T.track);
      s += text(bx + 5, by, wd.t, { size: size - 1, mono: true, fill: T.text });
    } else {
      s += text(bx, by, wd.t, { size, weight: wd.b || wd.link ? 700 : 400, fill: wd.link ? T.accent : o.fill || T.text });
      if (wd.link) s += `<path d="M${f1(bx)},${by + 3} H${f1(bx + wd.w)}" stroke="${T.accent}" stroke-opacity=".5"/>`;
    }
    cx += wd.w;
  }
  return { s, h: cy + lh };
}
function markdown(x, y, w, md, T) {
  let s = '', yy = y;
  const lines = md.trim().split('\n');
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    if (!ln.trim()) { yy += 6; continue; }
    if (ln.startsWith('### ')) {
      yy += 6;
      s += text(x, yy + 14, ln.slice(4), { size: 14.5, weight: 700, fill: T.text });
      yy += 28;
    } else if (ln.startsWith('```')) {
      const code = [];
      while (!lines[++i].startsWith('```')) code.push(lines[i]);
      const h = code.length * 20 + 18;
      s += rect(x + 22, yy, w - 22, h, 10, T.input, { stroke: T.border });
      code.forEach((c, k) => { s += text(x + 36, yy + 23 + k * 20, c, { size: 12.5, mono: true, fill: T.text }); });
      s += button(x + w - 8, yy + 7, 'Copy', T, { ic: 'copy', h: 26, anchor: 'end' }).s;
      yy += h + 10;
    } else if (ln.startsWith('- ')) {
      s += `<circle cx="${x + 8}" cy="${yy + 9}" r="2.6" fill="${T.accent}"/>`;
      const r = flow(x + 22, yy + 13, w - 22, ln.slice(2), T);
      s += r.s; yy += r.h + 5;
    } else {
      const r = flow(x, yy + 13, w, ln, T, { fill: T.muted });
      s += r.s; yy += r.h + 4;
    }
  }
  return { s, h: yy - y };
}

const TIPS = {
  linux: `
- **Load your board's sensor driver.** Run \`sudo sensors-detect\`, accept the defaults, then \`sudo systemctl restart fankata\`.
- **ACPI resource conflict** in \`dmesg\`: add \`acpi_enforce_resources=lax\` to the kernel command line and reboot.
- **ITE chips** (IT8686E, IT8689E, IT8792E…) need the out-of-tree [it87 driver](https://github.com/frankcrawford/it87). With Secure Boot on, enrol its DKMS signing key.
- **Gigabyte boards** use ITE chips, often two (IT8686E, IT8688E, IT8689E or IT8696E, plus IT8792E or IT87952E). Use the community it87 driver and load it with \`ignore_resource_conflict=1\` rather than a boot option. \`gigabyte_wmi\` reads temperatures only.
- **New board, older kernel:** on Ubuntu 22.04 install the HWE kernel.
\`\`\`
sudo apt install linux-generic-hwe-22.04
\`\`\`
- **ThinkPad:** fan control needs \`options thinkpad_acpi fan_control=1\`.
- **BIOS:** set the fan headers to *PWM* or *Auto*, not *Full speed*.
- **Hubs and splitters** share one control, so their fans appear as one.
- **NVIDIA cards** have no fan control in Linux's hwmon interface.
- Still stuck? **Copy report** and attach it to an issue.`,
  windows: `
- **Quit other fan or RGB software:** Armoury Crate, iCUE, NZXT CAM, MSI Center, Gigabyte Control Center (and SIV, EasyTune, RGB Fusion), SignalRGB, FanControl. They can lock the fan chip or a cooler's USB link.
- **BIOS:** set the fan headers to *PWM* or *Auto*, not *Full speed*. On Gigabyte boards (Smart Fan 5/6) set *Fan Control Mode* to PWM for 4-pin fans and Voltage for 3-pin ones.
- **Repair PawnIO:** run the Fankata installer again; it reinstalls the driver if it's missing or stopped.
- **Driver blocked:** Windows Security → Device security → Core isolation shows blocked drivers. Event Viewer → System lists why.
- **Laptops:** the embedded controller runs the fans, and most have no software control. Use the maker's app.
- **Unsupported chip:** Fankata reads hardware through LibreHardwareMonitor 0.9.6. Search its [issues](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/issues) for your chip or board.
- **Hubs and splitters** share one control, so their fans appear as one.
- Still stuck? **Copy report** and attach it to an issue.`,
};

// status badge: ok / warn / fail / info / wait / run
function badge(cx, cy, st, T) {
  const c = { ok: T.ok, warn: T.warn, fail: T.err, info: T.accent, wait: T.faint, run: T.accent }[st];
  const soft = { ok: T.okSoft, warn: T.warnSoft, fail: T.errSoft, info: T.accentSoft, wait: T.track, run: T.accentSoft }[st];
  let s = `<circle cx="${cx}" cy="${cy}" r="13" fill="${soft}"/>`;
  if (st === 'ok') s += icon('check', cx - 7, cy - 7, 14, c, 2.2);
  if (st === 'warn') s += icon('bang', cx - 7, cy - 7, 14, c, 2.2);
  if (st === 'fail') s += icon('x', cx - 6, cy - 6, 12, c, 2.2);
  if (st === 'info') s += icon('info', cx - 7, cy - 7, 14, c, 1.8);
  if (st === 'wait') s += `<circle cx="${cx}" cy="${cy}" r="3" fill="${c}"/>`;
  if (st === 'run') s += `<path d="M${cx + 7},${cy} A7,7 0 1 1 ${cx},${cy - 7}" fill="none" stroke="${c}" stroke-width="2.2" stroke-linecap="round"/>`;
  return s;
}
// one check row; returns { s, h }
function checkRow(x, y, w, c, T) {
  const actW = c.action ? tw(c.action.label, 13, { bold: true }) + 28 + (c.action.ic ? 20 : 0) + 16 : 0;
  const tx = x + 44, tw_ = w - 44 - actW - 8;
  let s = badge(x + 16, y + 20, c.st, T);
  s += text(tx, y + 18, c.title, { size: 14, weight: 700, fill: c.st === 'wait' && !c.tag ? T.muted : T.text });
  if (c.tag) s += pill(tx + mw(c.title, 14, { bold: true }) + 10, y + 3, c.tag, { bg: T.track, fg: T.muted, h: 20, size: 11 }).s;
  let h = 26;
  if (c.detail) { const r = flow(tx, y + 38, tw_, c.detail, T, { size: 12.5, lh: 19, fill: T.muted }); s += r.s; h += r.h; }
  if (c.check) {
    const cy = y + h + 6;
    s += rect(tx, cy, 18, 18, 5, c.check.on ? T.accent : 'none', c.check.on ? {} : { stroke: T.borderStrong, sw: 1.6 });
    if (c.check.on) s += icon('check', tx + 3, cy + 3, 12, '#ffffff', 2.2);
    s += flow(tx + 28, cy + 14, tw_ - 28, c.check.label, T, { size: 12.5 }).s;
    h += 30;
  }
  if (c.code) {
    const cy = y + h + 4, ch = c.code.length * 20 + 18, cw = w - 44;
    s += rect(tx, cy, cw, ch, 10, T.input, { stroke: T.border });
    c.code.forEach((l, k) => { s += text(tx + 14, cy + 23 + k * 20, l, { size: 12, mono: true, fill: l.startsWith('#') ? T.faint : T.text }); });
    s += button(tx + cw - 8, cy + 7, 'Copy', T, { ic: 'copy', h: 26, anchor: 'end' }).s;
    h += ch + 10;
  }
  if (c.action) s += button(x + w, y + 4, c.action.label, T, { anchor: 'end', primary: c.action.primary, ic: c.action.ic, h: 32, disabled: c.action.disabled }).s;
  return { s, h: Math.max(h, 40) + 14 };
}
function troubleshootDialog(T, o) {
  let s = o.under(T);
  s += `<rect width="${W}" height="${H}" fill="#0b0d14" opacity="${T.dark ? 0.55 : 0.32}"/>`;
  const dw = 780, dh = 712, dx = (W - dw) / 2, dy = (H - dh) / 2 + 8;
  s += rect(dx, dy, dw, dh, 20, T.surface, { filter: 'lift' });
  const x0 = dx + 30, iw = dw - 60;
  s += icon('lifebuoy', x0, dy + 30, 22, T.accent, 1.8);
  s += text(x0 + 34, dy + 48, 'Troubleshoot fans', { size: 21, weight: 700, fill: T.text });
  s += text(x0, dy + 76, o.lead, { size: 13, fill: T.muted });
  s += `<circle cx="${x0 + iw - 12}" cy="${dy + 41}" r="14" fill="${T.track}"/>` + icon('x', x0 + iw - 18, dy + 35, 12, T.muted, 1.8);
  // summary strip
  let y = dy + 94;
  s += rect(x0, y, iw, 62, 14, T.illusA);
  const cells = o.summary, cw = iw / cells.length;
  cells.forEach(([big, small, col], i) => {
    const cx = x0 + 20 + i * cw;
    if (i) s += `<path d="M${x0 + i * cw + 0.5},${y + 14} V${y + 48}" stroke="${T.border}"/>`;
    s += text(cx, y + 28, big, { size: 15, weight: 700, fill: col ? T[col] : T.text });
    s += text(cx, y + 47, small, { size: 12, fill: T.muted });
  });
  // scrolling body
  y += 78;
  const bodyTop = y, bodyBot = dy + dh - 74;
  const cid = nid('tsc');
  defs.push(`<clipPath id="${cid}"><rect x="${dx}" y="${bodyTop - 4}" width="${dw}" height="${bodyBot - bodyTop + 4}"/></clipPath>`);
  let b = '';
  y -= o.scroll || 0;
  b += text(x0, y + 12, 'CHECKS', { size: 11, weight: 700, fill: T.faint, ls: 1.2 });
  y += 24;
  o.checks.forEach((c, i) => {
    if (i) b += `<path d="M${x0 + 44},${y - 7.5} H${x0 + iw}" stroke="${T.border}"/>`;
    const r = checkRow(x0, y, iw, c, T);
    b += r.s; y += r.h;
  });
  y += 6;
  b += `<path d="M${x0},${y + 0.5} H${x0 + iw}" stroke="${T.border}"/>`;
  y += 18;
  b += icon(o.tips ? 'chevDown' : 'chevRight', x0, y - 1, 16, T.muted);
  b += text(x0 + 24, y + 12, 'Things to try', { size: 14.5, weight: 700, fill: T.text });
  b += text(x0 + 24 + tw('Things to try', 14.5, { bold: true }) + 10, y + 12, o.tipsNote || '', { size: 12.5, fill: T.muted });
  y += 26;
  if (o.tips) { const m = markdown(x0 + 4, y, iw - 4, TIPS[o.platform], T); b += m.s; y += m.h; }
  s += `<g clip-path="url(#${cid})">${b}</g>`;
  const contentH = y + (o.scroll || 0) - bodyTop, viewH = bodyBot - bodyTop;
  if (contentH > viewH) {
    const th = Math.max(40, viewH * viewH / contentH), ty = bodyTop + (viewH - th) * Math.min(1, (o.scroll || 0) / (contentH - viewH));
    s += rect(dx + dw - 10, ty, 4, th, 2, T.borderStrong, { op: 0.8 });
  }
  // footer
  const fy = dy + dh - 60;
  s += `<path d="M${dx},${fy - 13.5} H${dx + dw}" stroke="${T.border}"/>`;
  s += button(x0, fy, 'Copy report', T, { ic: 'copy', h: 38 }).s;
  const cb = button(x0 + iw, fy, 'Close', T, { primary: true, anchor: 'end', h: 38 });
  s += cb.s + button(x0 + iw - cb.w - 10, fy, 'Run again', T, { ic: 'refresh', anchor: 'end', h: 38 }).s;
  return s;
}

// Fans view with nothing to control (requirement 5.1.3): a Troubleshoot button instead of "see README"
function emptyFansView(T, o = {}) {
  let s = headerBar(T, 'fans');
  s += text(32, 102, 'Fans', { size: 28, weight: 700, fill: T.text });
  s += text(110, 101, '0 detected', { size: 14, fill: T.muted });
  const cw = 560, ch = 330, cx = (W - cw) / 2, cy = 190;
  s += rect(cx, cy, cw, ch, 22, T.surface, { stroke: T.border, filter: 'card' });
  s += `<circle cx="${W / 2}" cy="${cy + 82}" r="44" fill="${T.illusOff}" stroke="${T.border}"/>`;
  s += icon('fan', W / 2 - 24, cy + 58, 48, T.faint, 1.4);
  s += text(W / 2, cy + 158, 'No controllable fans found', { size: 19, weight: 700, fill: T.text, anchor: 'middle' });
  const lines = o.lines;
  lines.forEach((l, i) => { s += text(W / 2, cy + 188 + i * 21, l, { size: 13.5, fill: T.muted, anchor: 'middle' }); });
  const bw = tw('Troubleshoot', 13, { bold: true }) + 48;
  s += button(W / 2 - bw / 2, cy + 196 + lines.length * 21 + 12, 'Troubleshoot', T, { primary: true, ic: 'lifebuoy', h: 40 }).s;
  return s;
}
const EMPTY_LINUX = { lines: ['Fankata found temperatures from k10temp, nvme and acpitz,', 'but no fan control. The board’s sensor driver may not be loaded.'] };
const EMPTY_WINDOWS = { lines: ['LibreHardwareMonitor found no fan control on this PC.', 'The troubleshooter can check the driver and other fan software.'] };
const LX_SUMMARY = [['0 fan controls', 'pwm outputs found'], ['3 speed-only', 'fan1, fan2, fan3 on asus_wmi'], ['ASUS PRIME B550-PLUS', 'kernel 5.15.0-91 · Ubuntu 22.04']];
const LX_BASE = [
  { st: 'ok', title: 'Fan control service is running', detail: '`fankatad` 0.1.0 · Linux hwmon' },
  { st: 'warn', title: 'No sensor chip with fan control', detail: 'Loaded: `k10temp` (CPU), `nvme`, `acpitz`, `asus_wmi_sensors` (reads speeds only).' },
];
const TS_LINUX_START = {
  platform: 'linux', under: T => emptyFansView(T, EMPTY_LINUX),
  lead: 'Finds out why fans are missing, and fixes what it can.',
  summary: LX_SUMMARY,
  checks: [...LX_BASE,
    { st: 'wait', tag: 'Optional', title: 'Find the board’s fan chip', detail: 'Runs `sensors-detect` for Super I/O and CPU sensors only. It skips the riskier SMBus and ISA probes and changes no settings. Asks for an administrator password.', action: { label: 'Scan', ic: 'lock', primary: true } },
    { st: 'wait', title: 'Load the driver', detail: 'After the scan.' },
    { st: 'wait', title: 'Check kernel messages', detail: 'After the driver loads: looks for ACPI resource conflicts.' },
  ],
  tipsNote: '10 suggestions for Linux',
};
const TS_LINUX_FOUND = {
  ...TS_LINUX_START,
  checks: [...LX_BASE,
    { st: 'ok', title: 'Found a Nuvoton NCT6798D Super I/O chip', detail: '`sensors-detect`: driver `nct6775`, ISA address 0x290 (confidence 9). The driver is installed but not loaded.' },
    { st: 'info', title: 'Load the nct6775 driver', detail: 'Loads it now, then restarts the service so the fans appear.', check: { on: true, label: 'Also load it at every boot (`/etc/modules-load.d/fankata.conf`)' }, action: { label: 'Load driver', primary: true, ic: 'lock' } },
    { st: 'wait', title: 'Check kernel messages', detail: 'After the driver loads: looks for ACPI resource conflicts.' },
  ],
};
const TS_LINUX_CONFLICT = {
  ...TS_LINUX_START,
  summary: LX_SUMMARY,
  checks: [
    { st: 'ok', title: 'Found a Nuvoton NCT6798D Super I/O chip', detail: 'Driver `nct6775`, ISA address 0x290.' },
    { st: 'fail', title: 'The firmware won’t share the chip', detail: '`nct6775` loaded, but dmesg says: *ACPI: resource conflict*, so it couldn’t claim the chip. Fankata can fix it only by adding a boot option.', action: { label: 'Add boot option…', ic: 'lock' } },
  ],
  tips: true, tipsNote: 'nothing more could be fixed automatically',
};
const WIN_SUMMARY = [['4 fan controls', 'Nuvoton NCT6798D'], ['2 speed-only', 'fan5, fan7'], ['ASUS ROG STRIX X570-E', 'Windows 10 22H2']];
const WIN_BASE = [
  { st: 'ok', title: 'Fan control service is running', detail: 'LibreHardwareMonitor 0.9.6 as LocalSystem' },
  { st: 'ok', title: 'PawnIO driver is running', detail: 'Version 2.2.0 · no driver blocks in the event log' },
];
const TS_WINDOWS = {
  platform: 'windows', under: T => fansView(T),
  lead: 'Finds out why fans are missing, and points to what can fix it.',
  summary: WIN_SUMMARY,
  checks: [...WIN_BASE,
    { st: 'ok', title: 'Super I/O: Nuvoton NCT6798D', detail: '7 headers: 4 can be controlled; `fan5` (CHA_FAN3) and `fan7` (W_PUMP+) report speed only. Check their header mode in the BIOS.' },
    { st: 'warn', title: 'NZXT CAM is running', detail: 'It holds the USB link to the NZXT Kraken cooler, so the pump and radiator fans can’t be reached. Quit CAM, including its tray icon, then **Run again**.', action: { label: 'Open Task Manager', ic: 'link' } },
    { st: 'ok', title: 'No other fan software found', detail: 'Checked for Armoury Crate, iCUE, MSI Center, SignalRGB, FanControl, HWiNFO and SpeedFan.' },
  ],
  tipsNote: '8 suggestions for Windows',
};
const TS_WINDOWS_TIPS = {
  ...TS_WINDOWS, under: T => emptyFansView(T, EMPTY_WINDOWS),
  summary: [['0 fan controls', 'no Super I/O control'], ['2 speed-only', 'fan1, fan2 · EC'], ['Dell XPS 15 9520', 'laptop · Windows 10 22H2']],
  checks: [...WIN_BASE,
    { st: 'info', title: 'This is a laptop', detail: 'The embedded controller runs its fans; LibreHardwareMonitor can read their speeds but not set them.' },
  ],
  tips: true, tipsNote: 'nothing more could be checked automatically',
};


// ---- round 2: lm-sensors missing, Gigabyte boards, the GRUB confirmation
const TS_LINUX_NOSENSORS = {
  ...TS_LINUX_START,
  checks: [...LX_BASE,
    { st: 'warn', title: 'lm-sensors isn’t installed', detail: 'It provides `sensors-detect`, which finds the board’s fan chip. Installs the package `lm-sensors` with apt.', action: { label: 'Install lm-sensors', ic: 'lock', primary: true } },
    { st: 'wait', tag: 'Optional', title: 'Find the board’s fan chip', detail: 'Needs lm-sensors.', action: { label: 'Scan', ic: 'lock', disabled: true } },
    { st: 'wait', title: 'Load the driver', detail: 'After the scan.' },
  ],
};
const GB_SUMMARY = [['0 fan controls', 'pwm outputs found'], ['0 speed-only', 'gigabyte_wmi reads temperatures'], ['B550 AORUS ELITE V2', 'Gigabyte · kernel 5.15 · Ubuntu 22.04']];
const TS_GIGABYTE = {
  ...TS_LINUX_START,
  summary: GB_SUMMARY,
  checks: [
    { st: 'ok', title: 'Found two ITE chips: IT8688E and IT8792E', detail: '`sensors-detect`: Super I/O at 0x2e and 0x4e. Gigabyte boards drive their extra fan headers from the second chip.' },
    { st: 'fail', title: 'This kernel’s it87 driver doesn’t know the IT8688E', detail: 'Gigabyte’s newer ITE chips need the community `it87` driver. It builds against your kernel with DKMS and rebuilds after kernel updates.', code: ['sudo apt install dkms git build-essential linux-headers-$(uname -r)', 'git clone https://github.com/frankcrawford/it87', 'cd it87 && sudo make dkms'] },
    { st: 'info', title: 'Secure Boot is on', detail: 'While installing, DKMS asks you to choose a password; on the next restart a blue *MOK management* screen asks for it, to trust the new driver.' },
    { st: 'wait', title: 'Load it87 without a boot option', detail: 'After the community driver is installed: loads `it87` with `ignore_resource_conflict=1`, so only the fan chip is shared with the firmware.', check: { on: true, label: 'Also at every boot (`/etc/modprobe.d/fankata.conf`, `/etc/modules-load.d/fankata.conf`)' }, action: { label: 'Load driver', ic: 'lock', disabled: true } },
  ],
  tipsNote: '10 suggestions for Linux',
};
const WIN_GB = {
  ...TS_WINDOWS,
  summary: [['5 fan controls', 'ITE IT8689E + IT87952E'], ['0 speed-only', 'every header can be controlled'], ['X570 AORUS PRO', 'Gigabyte · Windows 10 22H2']],
  checks: [...WIN_BASE,
    { st: 'ok', title: 'Super I/O: ITE IT8689E and IT87952E', detail: 'Gigabyte boards drive their extra fan headers from the second chip; both were found, 5 controls in all.' },
    { st: 'warn', title: 'Gigabyte Control Center is running', detail: 'Its Smart Fan module and SIV write to the same ITE chips, so they overwrite Fankata’s speeds every few seconds. Quit it, or remove its fan module, then **Run again**.', action: { label: 'Open Task Manager', ic: 'link' } },
    { st: 'info', title: 'Gigabyte BIOS fan settings', detail: 'In Smart Fan 5/6, set each header’s *Fan Control Mode* to PWM for 4-pin fans or Voltage for 3-pin fans. *Full Speed* stops software control.' },
  ],
};
// GRUB confirmation (requirement 4.7): shows each file before and after, then writes it with update-grub
function codeLines(x, y, w, lines, T, kind) {        // kind: 'none' | 'add' | 'same'
  let s = '', yy = y;
  for (const l of lines) {
    const parts = Array.isArray(l) ? l : [[l, kind === 'add']];
    if (kind === 'add') s += rect(x, yy - 15, w, 21, 4, T.okSoft);
    let xx = x + (kind === 'none' ? 0 : 22);
    if (kind === 'add') s += text(x + 8, yy, '+', { size: 12, mono: true, weight: 700, fill: T.ok });
    for (const [t, hi] of parts) {
      const ww = mw(t, 12, { mono: true });
      if (hi && kind !== 'add') s += rect(xx - 2, yy - 14, ww + 4, 19, 4, T.okSoft);
      s += text(xx, yy, t, { size: 12, mono: true, fill: kind === 'none' || t.startsWith('#') ? T.faint : hi && kind !== 'add' ? T.ok : T.text, weight: hi && kind !== 'add' ? 700 : 400 });
      xx += ww;
    }
    yy += 22;
  }
  return { s, h: yy - y };
}
function beforeAfter(x, y, w, title, note, before, after, T) {
  let s = rect(x, y, w, 0, 0, 'none');
  const rowsB = before.lines.length, rowsA = after.lines.length;
  const h = 44 + 22 + rowsB * 22 + 14 + 22 + rowsA * 22 + 12;
  s += rect(x, y, w, h, 12, T.input, { stroke: T.border });
  s += text(x + 16, y + 26, title, { size: 13, mono: title.startsWith('/'), weight: 700, fill: T.text });
  s += text(x + w - 16, y + 26, note, { size: 12, fill: T.muted, anchor: 'end' });
  s += `<path d="M${x},${y + 40.5} H${x + w}" stroke="${T.border}"/>`;
  let yy = y + 62;
  s += text(x + 16, yy, 'BEFORE', { size: 10.5, weight: 700, fill: T.faint, ls: 1.1 });
  yy += 22;
  s += codeLines(x + 16, yy, w - 32, before.lines, T, before.kind).s; yy += rowsB * 22 + 14;
  s += text(x + 16, yy, 'AFTER', { size: 10.5, weight: 700, fill: T.faint, ls: 1.1 });
  yy += 22;
  s += codeLines(x + 16, yy, w - 32, after.lines, T, after.kind).s;
  return { s, h };
}
function grubConfirm(T) {
  let s = troubleshootDialog(T, TS_LINUX_CONFLICT);
  s += `<rect width="${W}" height="${H}" fill="#0b0d14" opacity="${T.dark ? 0.5 : 0.28}"/>`;
  const dw = 760, dh = 664, dx = (W - dw) / 2, dy = (H - dh) / 2 + 4;
  s += rect(dx, dy, dw, dh, 20, T.surface, { filter: 'lift' });
  const x0 = dx + 30, iw = dw - 60;
  s += text(x0, dy + 46, 'Add a boot option?', { size: 21, weight: 700, fill: T.text });
  s += `<circle cx="${x0 + iw - 12}" cy="${dy + 39}" r="14" fill="${T.track}"/>` + icon('x', x0 + iw - 18, dy + 33, 12, T.muted, 1.8);
  s += flow(x0, dy + 76, iw, 'Fankata will write one new file, then run `update-grub`. Nothing else changes. It takes effect when you restart.', T, { size: 13, fill: T.muted }).s;
  let y = dy + 100;
  const a = beforeAfter(x0, y, iw, '/etc/default/grub.d/fankata.cfg', 'new file', { kind: 'none', lines: ['(no file)'] },
    { kind: 'add', lines: ['# Added by Fankata (Troubleshoot fans). Delete this file and run', '# sudo update-grub to undo.', 'GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT acpi_enforce_resources=lax"'] }, T);
  s += a.s; y += a.h + 14;
  const b = beforeAfter(x0, y, iw, 'Kernel boot options', 'from /etc/default/grub + grub.d', { kind: 'same', lines: ['quiet splash'] },
    { kind: 'same', lines: [[['quiet splash ', false], ['acpi_enforce_resources=lax', true]]] }, T);
  s += b.s; y += b.h + 16;
  s += rect(x0, y, iw, 64, 12, T.warnSoft);
  s += icon('warn', x0 + 14, y + 13, 16, T.warn);
  s += flow(x0 + 40, y + 26, iw - 56, '`acpi_enforce_resources=lax` lets any driver use hardware the firmware reserved. It’s the usual fix for fan chips, but on a few boards it causes other conflicts. To undo it, use **Remove boot option** here.', T, { size: 12.5, lh: 19, fill: T.text }).s;
  const fy = dy + dh - 60;
  s += `<path d="M${dx},${fy - 13.5} H${dx + dw}" stroke="${T.border}"/>`;
  const pb = button(x0 + iw, fy, 'Write and update GRUB', T, { primary: true, ic: 'lock', anchor: 'end', h: 38 });
  s += pb.s + button(x0 + iw - pb.w - 10, fy, 'Cancel', T, { anchor: 'end', h: 38 }).s;
  s += button(x0, fy, 'Copy commands instead', T, { ic: 'copy', h: 38 }).s;
  return s;
}

// ---------------------------------------------------------------- output
const QUIET_ERR = 'Speed at 70 °C can’t be lower than 35 % (the speed at 55 °C).';
const DRAG = { fan: 'Front Intake', target: 'loop', index: 2, offset: [-34, 30],
               hint: 'Drop to use loop  ·  takes the Balanced curve from Radiator Fan (nearest)' };
const SCREENS = [
  ['01-fans', T => fansView(T), ['dark', 'light']],
  ['02-fans-drag', T => fansView(T, { scroll: 368, drag: DRAG }), ['dark', 'light']],
  ['03-fan-detail', T => fanDetail(T), ['dark', 'light']],
  ['04-fan-menu', T => fanDetail(T, { menu: true }), ['dark']],
  ['05-speed-pulse', T => fanDetail(T, { pulse: true }), ['dark', 'light']],
  ['06-curves', T => curvesView(T, { hover: { add: [30, 27] } }), ['dark', 'light']],
  ['07-curve-menu', T => curvesView(T, { curve: 'Performance', menu: true }), ['dark']],
  ['08-curves-probes-collapsed', T => curvesView(T, {
    curve: 'Quiet', collapsed: true, hover: { remove: 1 }, err: { i: 3, typed: 30, msg: QUIET_ERR },
  }), ['dark']],
  ['09-probe-editor', T => probeDialog(T, false), ['dark']],
  ['10-probe-editor-error', T => probeDialog(T, true), ['dark']],
  ['11-service-menu', T => fansView(T, { appMenu: true }), ['dark', 'light']],
  ['12-service-off', T => fansView(T, { serviceOff: true }), ['dark', 'light']],
  ['13-fans-wide', T => fansView(T), ['dark', 'light'], [2560, 1440]],
  ['14-speed-rings', T => ringSheet(T), ['dark', 'light']],
  ['15-troubleshoot-menu', T => fansView(T, { appMenu: true, menuHover: 'troubleshoot' }), ['dark', 'light']],
  ['16-fans-empty', T => emptyFansView(T, EMPTY_LINUX), ['dark', 'light']],
  ['17-troubleshoot-linux', T => troubleshootDialog(T, TS_LINUX_START), ['dark', 'light']],
  ['18-troubleshoot-linux-found', T => troubleshootDialog(T, TS_LINUX_FOUND), ['dark']],
  ['19-troubleshoot-linux-tips', T => troubleshootDialog(T, TS_LINUX_CONFLICT), ['dark', 'light']],
  ['20-troubleshoot-windows', T => troubleshootDialog(T, TS_WINDOWS), ['dark', 'light']],
  ['21-troubleshoot-windows-tips', T => troubleshootDialog(T, TS_WINDOWS_TIPS), ['dark']],
  ['22-troubleshoot-lm-sensors', T => troubleshootDialog(T, TS_LINUX_NOSENSORS), ['dark', 'light']],
  ['23-troubleshoot-grub-confirm', T => grubConfirm(T), ['dark', 'light']],
  ['24-troubleshoot-gigabyte-linux', T => troubleshootDialog(T, TS_GIGABYTE), ['dark', 'light']],
  ['25-troubleshoot-gigabyte-windows', T => troubleshootDialog(T, WIN_GB), ['dark']],
];

for (const [name, draw, themes, size] of SCREENS) for (const theme of themes) {
  [W, H] = size || [1280, 800];
  defs = []; uid = 0;
  const T = THEMES[theme];
  const body = draw(T);
  const frame = windowFrame(T, body);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W + PAD * 2}" height="${H + PAD * 2}" viewBox="0 0 ${W + PAD * 2} ${H + PAD * 2}">` +
    `<defs>${baseDefs(T)}${defs.join('')}</defs>${frame}</svg>`;
  fs.mkdirSync(path.join(OUT, 'src', 'svg', theme), { recursive: true });
  fs.mkdirSync(path.join(OUT, 'mocks', theme), { recursive: true });
  fs.writeFileSync(path.join(OUT, 'src', 'svg', theme, `${name}.svg`), svg);
  const png = new Resvg(svg, {
    fitTo: { mode: 'zoom', value: size ? 1 : 2 },          // big windows render at 1×
    font: { loadSystemFonts: true, defaultFontFamily: SANS },
  }).render().asPng();
  fs.writeFileSync(path.join(OUT, 'mocks', theme, `${name}.png`), png);
  console.log('wrote', `${theme}/${name}`);
}
