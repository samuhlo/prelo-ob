import test from "node:test";
import assert from "node:assert/strict";
import { apiErrorMessage, validateNoteSizes } from "../src/core";

test("shows server validation reasons for new and old servers without echoing note input", () => {
  assert.equal(apiErrorMessage(422, "Selecciona menos notas."), "Selecciona menos notas.");
  assert.equal(apiErrorMessage(422, [{ msg: "Value error, Máximo 600.000 caracteres.", input: "PRIVATE_NOTE" }]), "Máximo 600.000 caracteres.");
  assert.equal(apiErrorMessage(502, null), "El servicio respondió 502.");
  assert.equal(apiErrorMessage(422, [{ msg: "Too long" }, { msg: "Missing" }]), "Too long\nMissing");
});

test("preflight enforces existing per-note and per-edition limits, counting Unicode like Python", () => {
  assert.doesNotThrow(() => validateNoteSizes(["😀".repeat(200_000), "a".repeat(200_000), "b".repeat(200_000)]));
  assert.throws(() => validateNoteSizes(["a".repeat(200_001)]), /Una nota.*200.000/);
  assert.throws(() => validateNoteSizes(Array(4).fill("a".repeat(160_000))), /640.000.*600.000/);
});
