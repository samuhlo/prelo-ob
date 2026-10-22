import test from "node:test";
import assert from "node:assert/strict";
import { compareVersions, findUpdate } from "../src/updates";
const release = (version: string, extras = {}) => ({ tag_name: version, draft: false, prerelease: true,
  assets: ["main.js", "manifest.json", "styles.css"].map(name => ({ name, state: "uploaded" })), ...extras });

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
