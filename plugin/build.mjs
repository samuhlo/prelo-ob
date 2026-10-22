import { build } from "esbuild";
import { copyFile, mkdir, readFile } from "node:fs/promises";
const manifest = JSON.parse(await readFile("manifest.json", "utf8"));
const rootManifest = JSON.parse(await readFile("../manifest.json", "utf8"));
if (JSON.stringify(manifest) !== JSON.stringify(rootManifest)) throw new Error("Root and plugin manifests must match.");
const pkg = JSON.parse(await readFile("package.json", "utf8"));
const versions = JSON.parse(await readFile("../versions.json", "utf8"));
if (pkg.version !== manifest.version || versions[manifest.version] !== manifest.minAppVersion)
  throw new Error("Package version and compatibility map must match the manifest. Run scripts/set_version.py.");
const license = await readFile("../THIRD_PARTY_NOTICES.md", "utf8");
await build({
  entryPoints: ["src/main.ts"], outfile: "main.js", bundle: true,
  format: "cjs", platform: "node", target: "es2022", external: ["obsidian", "electron"],
  sourcemap: false, minify: false,
  loader: { ".svg": "text", ".wasm": "binary" },
  banner: { js: "/*!\n" + license.replaceAll("*/", "* /") + "\n*/" },
});
await copyFile("node_modules/sql.js/dist/sql-wasm.wasm", "sql-wasm.wasm");
await mkdir("../dist/margen", { recursive: true });
for (const file of ["main.js", "manifest.json", "styles.css", "sql-wasm.wasm"])
  await copyFile(file, "../dist/margen/" + file);
