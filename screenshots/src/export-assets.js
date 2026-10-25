// Exports the app's artwork from the mockup drawing code, so app and mockups match.
//   fan illustrations (layered for animation) -> src/fankata/qml/assets/art/*.svg
//   app icon (SVG + PNGs)                     -> packaging/icons/
// Usage: NODE_PATH=<dir with @resvg/resvg-js> node screenshots/src/export-assets.js
var fs = require('fs');
var path = require('path');
const src = fs.readFileSync(path.join(__dirname, 'render.js'), 'utf8');
const cut = src.indexOf('// ---------------------------------------------------------------- output');
// eslint-disable-next-line no-eval
eval(src.slice(0, cut).replace(/^(const|let) /gm, 'var '));

const ROOT = path.resolve(__dirname, '..', '..');
const ART = path.join(ROOT, 'src/fankata/qml/assets/art');
const ICON_DIR = path.join(ROOT, 'packaging/icons');
fs.mkdirSync(ART, { recursive: true });
fs.mkdirSync(ICON_DIR, { recursive: true });

// Every layer shares this viewBox; the app rotates rotors about these centres.
const VW = 240, VH = 150, CX = 120, CY = 75, S = 100;
function write(file, body) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${VW}" height="${VH}" viewBox="0 0 ${VW} ${VH}">` +
    `<defs>${defs.join('')}</defs>${body}</svg>`;
  fs.writeFileSync(path.join(ART, file), svg);
}
function layer(file, draw) { defs = []; uid = 0; write(file, draw()); }

for (const theme of ['dark', 'light']) {
  const T = THEMES[theme];
  layer(`case-base-${theme}.svg`, () => caseFan(CX, CY, S, T, { part: 'base' }));
  layer(`aio-base-${theme}.svg`, () => aioFan(CX, CY, S, T, { part: 'base' }));
  layer(`pump-base-${theme}.svg`, () => pump(CX, CY, S, T, { part: 'base' }));
  layer(`generic-${theme}.svg`, () => generic(CX, CY, S, T));
  for (const [state, active] of [['active', true], ['idle', false]]) {
    layer(`case-rotor-${state}-${theme}.svg`, () => caseFan(CX, CY, S, T, { part: 'rotor', active }));
    layer(`aio-rotor-${state}-${theme}.svg`, () => aioFan(CX, CY, S, T, { part: 'rotor', active }));
    layer(`pump-ring-${state}-${theme}.svg`, () => pump(CX, CY, S, T, { part: 'ring', active }));
  }
}
// rotor centres, for the QML side
fs.writeFileSync(path.join(ART, 'centres.json'), JSON.stringify({
  viewBox: [VW, VH], case: [CX, CY], aio: [CX - S * 0.08, CY], pump: [CX, CY],
}, null, 1));

// App icon: steel shuriken on a charcoal tile (requirement 2.2)
defs = []; uid = 0;
const tile = appIcon(16, 16, 224, THEMES.light);
const iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><defs>${defs.join('')}</defs>${tile}</svg>`;
fs.writeFileSync(path.join(ICON_DIR, 'fankata.svg'), iconSvg);
fs.copyFileSync(path.join(ICON_DIR, 'fankata.svg'), path.join(ART, 'fankata.svg'));
for (const size of [32, 48, 64, 128, 256]) {
  const png = new Resvg(iconSvg, { fitTo: { mode: 'width', value: size } }).render().asPng();
  fs.writeFileSync(path.join(ICON_DIR, `fankata-${size}.png`), png);
}
console.log('exported', fs.readdirSync(ART).length, 'art files and the app icon');
