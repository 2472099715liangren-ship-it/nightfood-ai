import test from "node:test";
import assert from "node:assert/strict";
import {
  loadConversation,
  saveConversation,
  clearConversation,
} from "../static/session-store.js";

const key = "nightfind-conversation-v1";
function memoryStorage() {
  const values = new Map();
  globalThis.localStorage = {
    getItem: (name) => values.get(name) ?? null,
    setItem: (name, value) => values.set(name, value),
    removeItem: (name) => values.delete(name),
  };
}

test("persists preferences, draft and IDs without caching merchant prices", () => {
  memoryStorage();
  saveConversation({
    history: [{ role: "user", text: "江汉路两个人" }],
    preferences: { party_size: 2 },
    selected: { id: 7, price_per_person: 999 },
    compared: new Map([[7, { id: 7 }]]),
    draft: "还没发",
    result: { stage: "catalog" },
    busy: false,
    failedRequest: false,
  });
  const saved = loadConversation();
  assert.equal(saved.preferences.party_size, 2);
  assert.equal(saved.selectedId, 7);
  assert.deepEqual(saved.comparedIds, [7]);
  assert.equal(saved.draft, "还没发");
  assert.ok(!localStorage.getItem(key).includes("price_per_person"));
  clearConversation();
  assert.equal(loadConversation(), null);
});

test("expires after 24 hours and rejects malformed timestamps", () => {
  memoryStorage();
  localStorage.setItem(
    key,
    JSON.stringify({ version: 1, savedAt: Date.now() - 25 * 3600000 }),
  );
  assert.equal(loadConversation(), null);
  localStorage.setItem(key, JSON.stringify({ version: 1 }));
  assert.equal(loadConversation(), null);
  localStorage.setItem(key, "invalid json");
  assert.equal(loadConversation(), null);
});

test("unavailable browser storage does not prevent application startup", () => {
  globalThis.localStorage = {
    getItem() {
      throw Error("disabled");
    },
    setItem() {
      throw Error("disabled");
    },
    removeItem() {
      throw Error("disabled");
    },
  };
  assert.equal(loadConversation(), null);
  assert.doesNotThrow(() =>
    saveConversation({ history: [], compared: new Map() }),
  );
  assert.doesNotThrow(() => clearConversation());
});
