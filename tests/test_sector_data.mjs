import test from "node:test";
import assert from "node:assert/strict";
import { snapshotSeries, makeProxy } from "../scripts/sector-data.mjs";

function snapshot() {
  const dates = Array.from({ length: 26 }, (_, i) => `202609${String(i + 1).padStart(2, "0")}`);
  return { asOf: dates.at(-1), dates, securities: [
    { code: "1332", c: dates.map((_, i) => 100 + i) },
    { code: "1306", c: dates.map((_, i) => 200 + i) },
  ] };
}

test("all members and index series end at the official snapshot date", () => {
  const data = snapshot();
  const series = snapshotSeries(data, ["1332", "1306"]);
  assert.equal(series.get("1332").at(-1).date, "2026-09-26");
  assert.equal(series.get("1306").length, 26);
  const proxy = makeProxy([...series.values()], data.asOf);
  assert.equal(proxy.length, 22);
  assert.equal(proxy.at(-1).date.replaceAll("-", ""), data.asOf);
});

test("a stale, missing or short member fails instead of publishing a stale proxy", () => {
  for (const change of [
    (data) => { data.securities[0].c[25] = null; },
    (data) => { data.securities[0].c = [100]; },
    (data) => { data.securities = []; },
    (data) => { data.securities[0].c.fill(null, 0, 6); },
  ]) {
    const data = snapshot(); change(data);
    assert.throws(() => snapshotSeries(data, ["1332"]));
  }
});

test("equal-weight daily return calculation is preserved", () => {
  const dates = snapshot().dates.slice(0, 21).map((d) => d.replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3"));
  const series = [102, 104].map((close) => dates.map((date, i) => ({ date, close: i ? close : 100 })));
  const proxy = makeProxy(series, "20260921");
  assert.equal(proxy[0].close, 100);
  assert.equal(proxy[1].close, 103);
  assert.equal(proxy.at(-1).close, 103);
});

test("insufficient common history or wrong final date is rejected", () => {
  const data = snapshot();
  const series = [...snapshotSeries(data, ["1332", "1306"]).values()];
  assert.throws(() => makeProxy([series[0].slice(0, 20), series[1]], data.asOf));
  assert.throws(() => makeProxy(series, "20260927"));
});
