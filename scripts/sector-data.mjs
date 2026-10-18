// Equal-weight sector proxies, aligned to the official snapshot's final session.
export function snapshotSeries(snapshot, codes) {
  const dates = snapshot.dates;
  if (!Array.isArray(dates) || dates.length < 21 || dates.at(-1) !== snapshot.asOf
      || dates.some((day, i) => !/^\d{8}$/.test(day) || (i > 0 && day <= dates[i - 1]))) {
    throw new Error("Invalid JPX snapshot dates for sector data");
  }
  const byCode = new Map(snapshot.securities.map((row) => [row.code, row]));
  const output = new Map();
  for (const code of codes) {
    const row = byCode.get(code);
    if (!row || row.c.length !== dates.length || !Number.isFinite(row.c.at(-1)) || row.c.at(-1) <= 0) {
      throw new Error(`Sector member ${code} has no close for ${snapshot.asOf}`);
    }
    const series = dates.map((day, i) => ({
      date: day.replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3"), close: row.c[i],
    })).filter((point) => Number.isFinite(point.close) && point.close > 0).slice(-26);
    if (series.length < 21) throw new Error(`Sector member ${code} has fewer than 21 closes`);
    output.set(code, series);
  }
  return output;
}

export function makeProxy(seriesList, asOf) {
  const maps = seriesList.map((series) => new Map(series.map((row) => [row.date, row.close])));
  const dates = [...maps[0].keys()].filter((date) => maps.every((map) => map.has(date)));
  if (dates.length < 21 || dates.at(-1).replaceAll("-", "") !== asOf) {
    throw new Error(`Sector series not aligned to ${asOf}: ${dates.length} common closes`);
  }
  let level = 100;
  return dates.map((date, index) => {
    if (index > 0) {
      const prior = dates[index - 1];
      const returns = maps.map((map) => map.get(date) / map.get(prior) - 1);
      level *= 1 + returns.reduce((sum, value) => sum + value, 0) / returns.length;
    }
    return { date, close: Number(level.toFixed(6)) };
  }).slice(-22);
}
