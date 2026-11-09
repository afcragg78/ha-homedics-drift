import assert from "node:assert/strict";
import { initialOpen } from "../custom_components/homedics_drift/www/drift-table-sections.js";

const closed = initialOpen({}, null);
assert.deepEqual(closed, {
  more: false,
  table: false,
  gallery: false,
  create: false,
  color: false,
  clean: false,
  storage: false,
});

const opened = initialOpen({ expanded: ["gallery", "table"] }, null);
assert.equal(opened.gallery, true);
assert.equal(opened.table, true);
assert.equal(opened.more, true);
assert.equal(opened.create, false);

const forced = initialOpen({ expanded: ["gallery"], collapsed: ["gallery", "more"] }, null);
assert.equal(forced.gallery, false);
assert.equal(forced.more, false);

const remembered = initialOpen({ expanded: ["gallery"] }, { gallery: false, more: false });
assert.equal(remembered.gallery, false);
assert.equal(remembered.more, false);

const words = initialOpen({ expanded: "Light Color, Clean Sand" }, null);
assert.equal(words.color, true);
assert.equal(words.clean, true);
assert.equal(words.more, true);
