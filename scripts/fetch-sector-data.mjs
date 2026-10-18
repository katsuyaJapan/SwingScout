import { readFile, writeFile, rename } from "node:fs/promises";
import { snapshotSeries, makeProxy } from "./sector-data.mjs";

// 東証33業種の代表的な大型・高流動性銘柄を複数選び、日次騰落率を等ウェイト合成する。
// 公式の業種別指数そのものではなく、無料公開データで相対強弱を把握するためのプロキシ。
const sectors = [
  ["水産・農林業", ["1332", "1333"], "#0ea5e9"],
  ["鉱業", ["1605", "1662"], "#a16207"],
  ["建設業", ["1801", "1802", "1803"], "#16a34a"],
  ["食料品", ["2502", "2802", "2914"], "#ef4444"],
  ["繊維製品", ["3401", "3402"], "#c026d3"],
  ["パルプ・紙", ["3861", "3863"], "#84cc16"],
  ["化学", ["4063", "4188", "4452"], "#8b5cf6"],
  ["医薬品", ["4502", "4503", "4568"], "#f97316"],
  ["石油・石炭製品", ["5019", "5020"], "#b45309"],
  ["ゴム製品", ["5108", "5110"], "#be123c"],
  ["ガラス・土石製品", ["5201", "5202"], "#64748b"],
  ["鉄鋼", ["5401", "5411"], "#475569"],
  ["非鉄金属", ["5711", "5802"], "#78716c"],
  ["金属製品", ["5947", "5991"], "#71717a"],
  ["機械", ["6301", "6326", "6367"], "#2563eb"],
  ["電気機器", ["6501", "6758", "6861"], "#4f46e5"],
  ["輸送用機器", ["7203", "7267", "7011"], "#dc2626"],
  ["精密機器", ["4543", "7733", "7741"], "#7c3aed"],
  ["その他製品", ["7974", "7832", "7911"], "#9333ea"],
  ["電気・ガス業", ["9501", "9503", "9531"], "#0f766e"],
  ["陸運業", ["9020", "9022", "9005"], "#0891b2"],
  ["海運業", ["9101", "9104", "9107"], "#0284c7"],
  ["空運業", ["9201", "9202"], "#38bdf8"],
  ["倉庫・運輸関連業", ["9301", "9302"], "#14b8a6"],
  ["情報・通信業", ["9432", "9433", "9984"], "#3b82f6"],
  ["卸売業", ["8001", "8031", "8058"], "#92400e"],
  ["小売業", ["9983", "3382", "8267"], "#db2777"],
  ["銀行業", ["8306", "8316", "8411"], "#4d7c0f"],
  ["証券・商品先物取引業", ["8604", "8601"], "#0369a1"],
  ["保険業", ["8766", "8725"], "#0e7490"],
  ["その他金融業", ["8591", "8253", "8439"], "#2563eb"],
  ["不動産業", ["8801", "8802", "8830"], "#be185d"],
  ["サービス業", ["6098", "4661", "4755"], "#7e22ce"],
];

const snapshot = JSON.parse(await readFile(new URL("../public/data/jpx-snapshot.json", import.meta.url), "utf8"));
const allCodes = [...new Set([...sectors.flatMap(([, codes]) => codes), "1306", "1329"])];
const seriesByCode = snapshotSeries(snapshot, allCodes);
const rows = sectors.map(([name, codes, color]) => ({
  name,
  code: codes.join("/"),
  members: codes,
  color,
  prices: makeProxy(codes.map((code) => seriesByCode.get(code)), snapshot.asOf),
}));

const topix = seriesByCode.get("1306");
const nikkei = seriesByCode.get("1329");
const asOf = snapshot.asOf.replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3");
const payload = {
  source: "JPX東京証券取引所日報（終値）",
  sourceUrl: "https://www.jpx.co.jp/markets/statistics-equities/daily/index.html",
  indexFamily: "東証33業種分類・主要構成銘柄等ウェイトプロキシ",
  methodology: "各業種2〜3銘柄の日次騰落率を等ウェイト合成（公式指数ではありません）",
  asOf,
  fetchedAt: new Date().toISOString(),
  sectors: rows,
  topix,
  nikkei,
};
const output = new URL("../public/data/sector-data.json", import.meta.url);
const temporary = new URL("../public/data/sector-data.json.tmp", import.meta.url);
await writeFile(temporary, `${JSON.stringify(payload, null, 2)}\n`);
await rename(temporary, output);
console.log(`Saved ${rows.length} sector proxies through ${asOf}`);
