import { test } from "node:test";
import assert from "node:assert/strict";
import { HEADER_GAP_PX, nearestPanelMode, sheetTop, visibleInsets, type MobileLayout } from "./mobileLayout.ts";

const layout = (viewportHeight: number, headerBottom = 124, safeBottom = 0): MobileLayout => ({
  viewportHeight,
  headerBottom,
  safeBottom,
});

test("expanded sheet starts just below the header", () => {
  assert.equal(sheetTop("expanded", layout(568)), 124 + HEADER_GAP_PX);
});

test("split sheet keeps at least 120px clearance under the header and prefers the middle", () => {
  assert.equal(sheetTop("split", layout(568)), 284); // 50% of 568
  assert.equal(sheetTop("split", layout(667)), 333.5);
  assert.ok(sheetTop("split", layout(568, 200)) >= 200 + 120);
});

test("peek sheet is a bottom bar of handle + bar + safe area", () => {
  assert.equal(sheetTop("peek", layout(667)), 667 - 30 - 44);
  assert.equal(sheetTop("peek", layout(844, 124, 34)), 844 - 30 - 44 - 34);
});

test("modes are ordered expanded < split < peek", () => {
  const l = layout(667);
  assert.ok(sheetTop("expanded", l) < sheetTop("split", l));
  assert.ok(sheetTop("split", l) < sheetTop("peek", l));
});

test("drag release snaps to the nearest stop", () => {
  const l = layout(667);
  assert.equal(nearestPanelMode(sheetTop("expanded", l) + 5, l), "expanded");
  assert.equal(nearestPanelMode(sheetTop("split", l) - 10, l), "split");
  assert.equal(nearestPanelMode(sheetTop("peek", l) - 3, l), "peek");
});

test("visible insets exclude header and sheet; expanded has none", () => {
  const l = layout(667);
  assert.equal(visibleInsets("expanded", l), null);
  const insets = visibleInsets("split", l);
  assert.ok(insets);
  assert.equal(insets.top, 124 + HEADER_GAP_PX);
  assert.equal(insets.bottom, 667 - sheetTop("split", l) + 12);
});
