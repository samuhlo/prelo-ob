import test from "node:test";
import assert from "node:assert/strict";
import { validateConnection } from "../src/connection";
const token = "synthetic-" + "x".repeat(32);
test("remote connections require HTTPS; local loopback works without a proxy", () => {
  for (const url of ["http://127.0.0.1:8765", "http://localhost:8765", "http://[::1]:8765", "https://reader.example.test"])
    assert.equal(validateConnection({ serverUrl: url, token }).serverUrl, url);
  for (const url of ["http://reader.example.test", "https://user:pass@example.test", "https://example.test/?token=x", "file:///private/test"])
    assert.throws(() => validateConnection({ serverUrl: url, token }));
});
test("invalid connection data does not mutate the previous settings", () => {
  const previous = { serverUrl: "https://reader.example.test", token, highlightsFolder: "Quotes" };
  assert.throws(() => validateConnection({ ...previous, highlightsFolder: "../outside" }));
  assert.deepEqual(previous, { serverUrl: "https://reader.example.test", token, highlightsFolder: "Quotes" });
  assert.throws(() => validateConnection({ ...previous, token: token + "\n" }));
});
