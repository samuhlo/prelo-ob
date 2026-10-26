import test from "node:test";
import assert from "node:assert/strict";
import { deliveryState } from "../src/delivery";

test("a copied edition is not reported as on the reader until the Kobo imports it", () => {
  assert.match(deliveryState({ delivery: "sent" }).text, /aparecerá al desconectar/);
  assert.match(deliveryState({ delivery: "sent", on_kobo: "copied" }).text, /aparecerá al desconectar/);
  assert.equal(deliveryState({ delivery: "sent", on_kobo: "imported", percent_read: 35 }).text, "En tu Kobo · 35 % leído");
  assert.equal(deliveryState({ delivery: "sent", on_kobo: "not_imported" }).tone, "is-warning");
  assert.ok(deliveryState({ delivery: "sent", on_kobo: "missing" }).resend);
  assert.equal(deliveryState({ delivery: "queued" }).text, "En cola para el Kobo");
  assert.match(deliveryState({ available: false, delivery: "sent" }).text, /retirado/);
});
