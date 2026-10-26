import test from "node:test";
import assert from "node:assert/strict";
import { hash } from "../src/core";
import { compareVersions, findUpdate, installable, verifyUpdate } from "../src/updates";
const download = (version: string, name: string) => `https://github.com/samuhlo/prelo-ob/releases/download/${version}/${name}`;
const release = (version: string, extras = {}) => ({ tag_name: version, draft: false, prerelease: true,
  assets: ["main.js", "manifest.json", "styles.css", "SHA256SUMS"].map(name => ({ name, state: "uploaded", browser_download_url: download(version, name) })), ...extras });
const bytes = (text: string) => new TextEncoder().encode(text).buffer;
function releaseFiles(manifest: object) {
  const files: Record<string, ArrayBuffer> = { "main.js": bytes("module.exports = {};"), "styles.css": bytes(".margen {}"),
    "manifest.json": bytes(JSON.stringify(manifest)) };
  files.SHA256SUMS = bytes(Object.entries(files).map(([name, data]) => `${hash(new Uint8Array(data))}  ${name}`).join("\n") + "\n");
  return files;
}

test("versions are compared numerically, never lexically", () => {
  assert.equal(compareVersions("0.10.0", "0.9.9"), 1);
  assert.equal(compareVersions("v1.0.0", "1.0.0"), 0);
  assert.equal(compareVersions("0.8.0", "1.0.0"), -1);
  for (const invalid of ["main", "0.8", "0.8.0-beta", "01.2.3", "<script>"])
    assert.equal(compareVersions(invalid, "0.7.0"), undefined);
});

test("selects highest complete published release including betas, not newest timestamp", () => {
  const result = findUpdate([release("0.8.0"), release("0.10.0"), release("0.9.0")], "0.7.0");
  assert.equal(result?.version, "0.10.0");
  assert.equal(result?.beta, true);
  assert.equal(result?.url, "https://github.com/samuhlo/prelo-ob/releases/tag/0.10.0");
});

test("ignores drafts, partial uploads, malformed responses and downgrades", () => {
  assert.equal(findUpdate([release("0.8.0", { draft: true }), release("0.9.0", { assets: [] }),
    release("0.10.0", { assets: [{ name: "main.js", state: "new" }] }), release("main"), null,
    release("0.7.0")], "0.7.0"), undefined);
  assert.equal(findUpdate([release("0.8.0")], "0.9.0"), undefined);
  assert.throws(() => findUpdate({ message: "rate limited" }, "0.7.0"));
});

test("installs only releases with checksums and download links from the project", () => {
  const update = findUpdate([release("0.9.1")], "0.9.0");
  assert.ok(update && installable(update));
  assert.equal(update.downloads["main.js"], download("0.9.1", "main.js"));
  const unsigned = findUpdate([release("0.9.1", { assets: ["main.js", "manifest.json", "styles.css"].map(name => ({ name, state: "uploaded", browser_download_url: download("0.9.1", name) })) })], "0.9.0");
  assert.ok(unsigned && !installable(unsigned));
  const foreign = findUpdate([release("0.9.1", { assets: ["main.js", "manifest.json", "styles.css", "SHA256SUMS"].map(name => ({ name, state: "uploaded", browser_download_url: `https://example.com/${name}` })) })], "0.9.0");
  assert.ok(foreign && !installable(foreign));
});

test("verified update must match checksums, plugin id and announced version", () => {
  const manifest = { id: "margen", version: "0.9.1", minAppVersion: "1.8.0" };
  assert.deepEqual(verifyUpdate(releaseFiles(manifest), { id: "margen", version: "0.9.1" }), { minAppVersion: "1.8.0" });
  const tampered = releaseFiles(manifest);
  tampered["main.js"] = bytes("evil()");
  assert.throws(() => verifyUpdate(tampered, { id: "margen", version: "0.9.1" }), /main\.js/);
  assert.throws(() => verifyUpdate(releaseFiles({ ...manifest, id: "other" }), { id: "margen", version: "0.9.1" }));
  assert.throws(() => verifyUpdate(releaseFiles({ ...manifest, version: "0.9.2" }), { id: "margen", version: "0.9.1" }));
});
