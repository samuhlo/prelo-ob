// Local SVG preview; explicit fonts avoid a system-wide font scan.
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
const require = createRequire(new URL("../plugin/package.json", import.meta.url));
const { Resvg } = require("@resvg/resvg-js");
const [source, target, ...fonts] = process.argv.slice(2);
if (!source || !target) {
  console.error("Uso: node scripts/render_cover.mjs portada.svg portada.png [fuente.ttf ...]");
  process.exit(1);
}
const fontFiles = fonts.length ? fonts : process.platform === "darwin" ? [
  "/System/Library/Fonts/Supplemental/Arial.ttf",
  "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
] : [];
if (!fontFiles.length) throw new Error("Indica al menos un archivo de fuente.");
const render = new Resvg(readFileSync(source), {
  fitTo: { mode: "width", value: 720 },
  font: { loadSystemFonts: false, fontFiles, defaultFontFamily: "Arial", sansSerifFamily: "Arial" },
}).render();
writeFileSync(target, render.asPng());
console.log(target);
