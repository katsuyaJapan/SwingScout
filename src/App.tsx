import { useCallback, useEffect, useRef, useState } from "react";
import changelog from "./changelog.json";
type Candidate = {
  code: string;
  name: string;
  sector?: string;
  sectorPhase?: string;
  setup?: string;
  entry?: string;
  entryLower?: number;
  entryUpper?: number;
  entryRiskPct?: number;
  riskReward?: number;
  targetPrice?: number;
  targetPrice1?: number;
  targetPrice2?: number;
  maxOpeningPrice?: number;
  maxOpeningGapPct?: number;
  openingRule?: string;
  close: number;
  score: number;
  displayScore?: number;
  technical: number;
  liquidity: number;
  invalidation: string;
  reasons: string[];
  provisional?: boolean;
  priceDate?: string;
  excludeReason?: string;
  earningsDate?: string | null;
  earningsStatus?: string;
  earningsPeriod?: string | null;
  earningsSources?: Array<{ name: string; date?: string; status?: string }>;
  earningsCheckedSources?: string[];
  earningsDays?: number | null;
  lastEarningsDate?: string | null;
  rightsRecordDate?: string;
  exRightsDate?: string;
  rightsExitDeadline?: string;
  rightsReason?: string;
  exRightsDays?: number | null;
  riskFlags?: string[];
  lastSelectedDate?: string;
};
type Sector = {
  name: string;
  score: number;
  phase: string;
  return5: number;
  return20: number;
  breadth: number;
  breadthChange: number;
  turnoverRatio: number;
  stocks: number;
};
type SectorOutflow = {
  name: string;
  score: number;
  level: string;
  action: string;
  return1: number;
  return5: number;
  return20: number;
  breadthChange: number;
  turnoverRatio: number;
  reasons: string[];
};
type Analysis = {
  asOf: string;
  officialAsOf?: string;
  priceStatus?: "PROVISIONAL" | "JPX_CONFIRMED";
  generatedAt: string;
  cached: boolean;
  message: string;
  finalCandidates: Candidate[];
  continuedCandidates?: Candidate[];
  excludedEarnings?: Candidate[];
  sectorSignals?: Sector[];
  sectorOutflows?: SectorOutflow[];
  sectorOutflowAsOf?: string;
  excludedExtended?: Candidate[];
  technicalCandidates: Candidate[];
  marketRegime?: { level: "NORMAL" | "CAUTION"; title: string; message: string; asOf?: string; topix1d?: number | null; topix5d?: number | null; nikkei1d?: number | null; nikkei5d?: number | null };
  funnel: Record<string, number>;
  quality: {
    passed: boolean;
    files: number;
    failures: number;
    latestCoverage: number;
    priceDate: string;
    officialPriceDate?: string;
    provisionalCount?: number;
    provisionalTotal?: number;
    fundamental: string;
    earningsDate: string;
    tdnet: string;
  };
  sources: Array<{ name: string; asOf: string; status: string }>;
};
type HistoryCandidate = {
  code: string;
  name: string;
  close: number;
  currentClose: number | null;
  changePct: number | null;
  entry?: string;
  targetPrice?: number;
  invalidation: string;
  targetReached: boolean;
};
type DailyHistory = {
  asOf: string;
  candidates: HistoryCandidate[];
};
type VisitCounts = {
  total: number;
  today: number;
};
type UpdateStatus = { lastAttemptAt?: string; lastAttemptStatus: "success" | "failed"; lastSuccessfulAt?: string; dataAsOf?: string; isPreviousBusinessDay?: boolean; message?: string };
type PurchaseRecord = { code: string; name: string; price: number; shares: number; purchasedAt: string };
const PURCHASE_KEY = "swing-scout-purchases-v1";
const BASE = import.meta.env.BASE_URL;
const labels: Record<string, string> = {
  listed: "JPX掲載",
  latestPrice: "最新価格あり",
  historyReady: "200日履歴",
  liquid: "流動性通過",
  primary: "一次候補",
  detailReview: "詳細確認",
  final: "最終候補",
};
const dateText = (d: string) =>
  d.length === 8 ? `${d.slice(0, 4)}/${d.slice(4, 6)}/${d.slice(6)}` : d;
const earningsDisplay = (candidate: Candidate) => {
  const flags = new Set(candidate.riskFlags ?? []);

  if (flags.has("EARNINGS_WITHIN_3_DAYS")) {
    return {
      className: "danger",
      text: `⚠️ ${dateText(candidate.earningsDate ?? "")}（あと${candidate.earningsDays}営業日・選定対象外）`,
    };
  }
  if (flags.has("EARNINGS_DATE_UNDECIDED")) {
    return { className: "danger", text: "⚠️ 決算日未定・選定対象外" };
  }
  if (flags.has("EARNINGS_DATE_CONFLICT")) {
    return { className: "danger", text: "⚠️ 確認元で日付不一致・選定対象外" };
  }
  if (flags.has("EARNINGS_UNCONFIRMED")) {
    return { className: "danger", text: "⚠️ 決算日を確認できず・選定対象外" };
  }
  if (candidate.earningsDate) {
    return {
      className: "okText",
      text: `${dateText(candidate.earningsDate)}（あと${candidate.earningsDays}営業日）・安全圏`,
    };
  }
  if (candidate.earningsStatus === "RECENTLY_REPORTED") {
    const reported = candidate.lastEarningsDate ? `${dateText(candidate.lastEarningsDate)}発表済み` : "直近決算発表済み";
    return { className: "okText", text: `${reported}・安全圏` };
  }
  return { className: "pending", text: "決算日を確認中" };
};
const timeText = (d: string) =>
  new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(d));
export default function Home() {
  const [data, setData] = useState<Analysis | null>(null),
    [history, setHistory] = useState<DailyHistory[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [changelogOpen, setChangelogOpen] = useState(false),
    [disclaimerOpen, setDisclaimerOpen] = useState(false),
    [visitCounts, setVisitCounts] = useState<VisitCounts | null>(null),
    [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null),
    [purchases, setPurchases] = useState<Record<string, PurchaseRecord>>({});
  const requested = useRef(false), visitRequested = useRef(false);
  const load = useCallback(async (force = false, silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      const suffix = force ? `?v=${Date.now()}` : "";
      const r = await fetch(`${BASE}data/latest.json${suffix}`, {
        cache: "no-store",
      });
      if (!r.ok) throw new Error("分析結果を取得できませんでした");
      setData(await r.json());
      const historyResponse = await fetch(`${BASE}data/history.json${suffix}`, { cache: "no-store" });
      if (historyResponse.ok) {
        const saved = await historyResponse.json() as { history?: DailyHistory[] };
        setHistory(saved.history ?? []);
      }
      const statusResponse = await fetch(`${BASE}data/status.json${suffix}`, { cache: "no-store" });
      if (statusResponse.ok) setUpdateStatus(await statusResponse.json() as UpdateStatus);
    } catch (e) {
      setError(e instanceof Error ? e.message : "取得エラー");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (requested.current) return;
    requested.current = true;
    load();
  }, [load]);
  useEffect(() => {
    const syncLatest = () => {
      if (document.visibilityState === "visible") load(false, true);
    };
    const interval = window.setInterval(syncLatest, 5 * 60 * 1000);
    document.addEventListener("visibilitychange", syncLatest);
    window.addEventListener("focus", syncLatest);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", syncLatest);
      window.removeEventListener("focus", syncLatest);
    };
  }, [load]);
  useEffect(() => {
    if (visitRequested.current) return;
    visitRequested.current = true;
    const today = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(new Date());
    const saved = JSON.parse(localStorage.getItem("swing-scout-local-visits") ?? "{}") as { total?: number; today?: number; date?: string };
    const counts = { total: (saved.total ?? 0) + 1, today: saved.date === today ? (saved.today ?? 0) + 1 : 1, date: today };
    localStorage.setItem("swing-scout-local-visits", JSON.stringify(counts));
    setVisitCounts({ total: counts.total, today: counts.today });
    try { setPurchases(JSON.parse(localStorage.getItem(PURCHASE_KEY) ?? "{}")); } catch { setPurchases({}); }
  }, []);
  const savePurchase = (record: PurchaseRecord) => {
    const next = { ...purchases, [record.code]: record };
    setPurchases(next); localStorage.setItem(PURCHASE_KEY, JSON.stringify(next));
  };
  const removePurchase = (code: string) => {
    const next = { ...purchases }; delete next[code];
    setPurchases(next); localStorage.setItem(PURCHASE_KEY, JSON.stringify(next));
  };
  useEffect(() => {
    if (!changelogOpen && !disclaimerOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setChangelogOpen(false);
        setDisclaimerOpen(false);
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [changelogOpen, disclaimerOpen]);
  return (
    <main>
      <header>
        <div className="brand">
          <span><img src={`${BASE}brand-mark.svg`} alt="" width={40} height={40} /></span>
          <div>
            <b>SWING SCOUT</b>
            <small>日本株・先回り候補</small>
          </div>
        </div>
        <div className="headerActions">
          <button
            className="changelogTrigger"
            onClick={() => setChangelogOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={changelogOpen}
          >
            <span>{changelog[0].version}</span> 更新履歴
          </button>
          <button onClick={() => load(true)} disabled={loading}>
            {loading ? "確認中" : "手動更新"}
          </button>
        </div>
      </header>
      <section className="hero brandHero">
        <p className="eyebrow">TODAY&apos;S SETUP · 2〜10営業日</p>
        <h1>今日、仕込むべき銘柄</h1>
        <p>
          全銘柄を検査し、品質ゲートを通過した候補だけを最大3銘柄表示します。
        </p>
      </section>
      {error && <div className="error">{error}</div>}
      {!data ? (
        <section className="loadingCard">生成済みの最新データを読み込んでいます…</section>
      ) : (
        <>
          {updateStatus && (
            <section className={`updateStatus ${updateStatus.lastAttemptStatus === "failed" ? "updateFailed" : "updateOk"}`}>
              <b>{updateStatus.lastAttemptStatus === "success" ? "日次更新 成功" : "日次更新 失敗・前回正常データを表示"}</b>
              <span>最終正常データ {dateText(updateStatus.dataAsOf ?? data.asOf)}{updateStatus.isPreviousBusinessDay ? "（前営業日）" : ""} / 確認 {updateStatus.lastAttemptAt ? timeText(updateStatus.lastAttemptAt) : "—"}</span>
              {updateStatus.message && <small>{updateStatus.message}</small>}
            </section>
          )}
          {data.marketRegime && (
            <section className={`marketRegime ${data.marketRegime.level === "CAUTION" ? "marketCaution" : "marketNormal"}`}>
              <div><small>MARKET REGIME</small><h3>{data.marketRegime.title}</h3></div>
              <p>{data.marketRegime.message}</p>
              <span>TOPIX 1日 {data.marketRegime.topix1d ?? "—"}%・5日 {data.marketRegime.topix5d ?? "—"}% / 日経 1日 {data.marketRegime.nikkei1d ?? "—"}%・5日 {data.marketRegime.nikkei5d ?? "—"}%</span>
            </section>
          )}
          <section
            className={`verdict ${data.finalCandidates.length ? "ready" : "hold"}`}
          >
            <div>
              <span className="status">
                {data.finalCandidates.length
                  ? `本日の暫定仕込み候補 ${data.finalCandidates.length}銘柄`
                  : "本日の暫定仕込み候補なし"}
              </span>
              <h2>
                {data.finalCandidates.length
                  ? data.finalCandidates.map((x) => x.name).join("・")
                  : "条件を満たす銘柄がありません"}
              </h2>
              <p>{data.message}</p>
            </div>
            <div className="asof">
              <span>株価基準</span>
              <b>{dateText(data.asOf)} 終値</b>
              <strong
                className={
                  data.priceStatus === "PROVISIONAL"
                    ? "provisional"
                    : "confirmed"
                }
              >
                {data.priceStatus === "PROVISIONAL"
                  ? "一次候補の暫定終値"
                  : "JPX確認済み"}
              </strong>
              <small>
                {data.cached ? "保存済み分析" : "今回作成"} ·{" "}
                {timeText(data.generatedAt)}
              </small>
            </div>
          </section>
          {data.finalCandidates.length > 0 && (
            <section className="morningGuide">
              <div className="morningGuideHead">
                <div>
                  <small>NEXT MORNING CHECK</small>
                  <h3>翌朝の取引チェック手順</h3>
                </div>
                <strong>GU +1.0%まで</strong>
              </div>
              <ol>
                <li><b>8:50以降</b><span>気配値と地合いを確認</span></li>
                <li><b>9:00</b><span>実際の寄り付き価格を確認</span></li>
                <li><b>上限以下</b><span>エントリーゾーン内なら候補継続</span></li>
                <li><b>上限超え</b><span>追いかけず、その日は見送り</span></li>
                <li><b>約定後</b><span>カード記載の無効化ラインを設定</span></li>
              </ol>
              <p>前日終値から＋1.0％を超えるギャップアップ、またはエントリー上限超えは、スコアが高くても新規エントリー対象外です。</p>
            </section>
          )}
          {data.finalCandidates.length > 0 && (
            <section className="pickGrid">
              {data.finalCandidates.map((c, i) => (
                <article className="pick" key={c.code}>
                  <div className="pickTop">
                    <i>{i + 1}</i>
                    <div>
                      <small>
                        {c.sector}・{c.sectorPhase}
                      </small>
                      <h3>
                        {c.name} <em>{c.code}</em>
                      </h3>
                    </div>
                    <strong>
                      {c.displayScore ?? Math.round(c.score)}
                      <small>/100</small>
                    </strong>
                  </div>
                  <span className="setupBadge">{c.setup}</span>
                  <p>{c.reasons.join("・")}</p>
                  <dl>
                    <div>
                      <dt>現在値</dt>
                      <dd>¥{c.close.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt>エントリー目安</dt>
                      <dd>{c.entry ?? "押し目待ち"}</dd>
                      {c.entryRiskPct != null && <small>上限買付時の損切り幅 {c.entryRiskPct}%</small>}
                    </div>
                    <div>
                      <dt>無効化ライン</dt>
                      <dd>{c.invalidation}</dd>
                    </div>
                    <div className="openingLimit">
                      <dt>寄り付き許容上限</dt>
                      <dd>¥{c.maxOpeningPrice?.toLocaleString() ?? "—"}</dd>
                      <small>前日終値＋{c.maxOpeningGapPct ?? 1.0}%以内</small>
                      <p>{c.openingRule ?? "9:00の寄り付きが上限を超えた場合は見送り"}</p>
                    </div>
                    <div>
                      <dt>リスクリワード</dt>
                      <dd className={(c.riskReward ?? 0)>=1.5?"okText":"pending"}>RR {c.riskReward?.toFixed(2) ?? "—"}</dd>
                      {c.targetPrice1 != null && <small>第1目標 ¥{c.targetPrice1.toLocaleString()} / 第2目標 ¥{(c.targetPrice2 ?? c.targetPrice)?.toLocaleString()}</small>}
                    </div>
                    <div>
                      <dt>決算</dt>
                      <dd className={earningsDisplay(c).className}>
                        {earningsDisplay(c).text}
                        {!!c.earningsCheckedSources?.length && <small>確認元：{c.earningsCheckedSources.join("・")}</small>}
                      </dd>
                    </div>
                    <div>
                      <dt>流動性</dt>
                      <dd>
                        {c.riskFlags?.includes("LOW_LIQUIDITY")
                          ? "注意：売買代金少なめ"
                          : "基準通過"}
                      </dd>
                    </div>
                    <div className={c.riskFlags?.includes("EX_RIGHTS_WITHIN_3_DAYS") ? "rightsRisk dangerBox" : "rightsRisk"}>
                      <dt>権利落ち回避</dt>
                      {c.exRightsDate ? (
                        <dd>
                          <b>{dateText(c.rightsExitDeadline ?? "")}までに売却</b>
                          <small>{c.rightsReason}・権利落日 {dateText(c.exRightsDate)}</small>
                        </dd>
                      ) : (
                        <dd className="pending">直近のJPX権利落情報なし</dd>
                      )}
                    </div>
                  </dl>
                  <PurchasePanel candidate={c} record={purchases[c.code]} onSave={savePurchase} onRemove={removePurchase} />
                </article>
              ))}
            </section>
          )}
          {!!data.continuedCandidates?.length && (
            <section className="card continuedCard">
              <div className="cardHead">
                <div>
                  <small>CONTINUED WATCH</small>
                  <h3>継続監視・新規枠から除外</h3>
                </div>
                <span>{data.continuedCandidates.length}銘柄</span>
              </div>
              <p className="continuedNote">過去5営業日以内に選出済みのため、新規3銘柄には重複掲載していません。過去ログで騰落率と目標到達を継続確認します。</p>
              <div className="continuedList">
                {data.continuedCandidates.slice(0, 6).map((candidate) => (
                  <article key={candidate.code}>
                    <div><b>{candidate.name}</b><em>{candidate.code}・{candidate.sector}</em></div>
                    <span>初回選出 {dateText(candidate.lastSelectedDate ?? "")}</span>
                    <strong>¥{candidate.close.toLocaleString()}</strong>
                  </article>
                ))}
              </div>
            </section>
          )}
          {!!data.excludedEarnings?.length && (
            <section className="card earningsExcluded">
              <div className="cardHead">
                <div>
                  <small>SAFETY FILTER</small>
                  <h3>決算リスクのため除外</h3>
                </div>
                <span className="ng">{data.excludedEarnings.length}銘柄</span>
              </div>
              <p className="muted">決算発表まで3営業日以内、またはJPXで発表日が未定の銘柄は、安全確認できないため仕込み候補に表示しません。</p>
              <div className="excludedList">
                {data.excludedEarnings.map((c) => (
                  <div key={c.code}>
                    <b>{c.name} <em>{c.code}</em></b>
                    <span>{c.riskFlags?.includes("EARNINGS_DATE_UNDECIDED") ? `⚠️ 決算日未定${c.earningsPeriod ? `・${c.earningsPeriod}` : ""}` : `⚠️ ${dateText(c.earningsDate ?? "")}・あと${c.earningsDays}営業日`}{c.earningsSources?.length ? `（${[...new Set(c.earningsSources.map(x=>x.name))].join("・")}）` : ""}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
          <section className="card historyCard">
            <div className="cardHead">
              <div>
                <small>DAILY ARCHIVE</small>
                <h3>過去の仕込み候補</h3>
              </div>
              <span>{history.length}日分</span>
            </div>
            <p className="historyNote">毎日の上位3銘柄を30営業日分保存します。選出時からの騰落率と目標到達を確認できます。</p>
            {history.length ? (
              <div className="historyDays">
                {history.map((day) => (
                  <details key={day.asOf} open={day.asOf === data.asOf}>
                    <summary>
                      <b>{dateText(day.asOf)}</b>
                      <span>{day.candidates.map((candidate) => candidate.name).join("・")}</span>
                    </summary>
                    <div className="historyRows">
                      {day.candidates.map((candidate) => (
                        <article key={candidate.code}>
                          <div className="historyName">
                            <b>{candidate.name}</b><em>{candidate.code}</em>
                            {candidate.targetReached && <strong>目標到達</strong>}
                          </div>
                          <dl>
                            <div><dt>選出時終値</dt><dd>¥{candidate.close.toLocaleString()}</dd></div>
                            <div><dt>最新確定終値</dt><dd>¥{candidate.currentClose?.toLocaleString() ?? "—"}</dd></div>
                            <div><dt>選出後騰落率</dt><dd className={(candidate.changePct ?? 0) >= 0 ? "historyUp" : "historyDown"}>{candidate.changePct == null ? "—" : `${candidate.changePct > 0 ? "+" : ""}${candidate.changePct}%`}</dd></div>
                            <div><dt>目標株価</dt><dd>¥{candidate.targetPrice?.toLocaleString() ?? "—"}</dd></div>
                            <div><dt>エントリー目安</dt><dd>{candidate.entry ?? "—"}</dd></div>
                            <div><dt>無効化ライン</dt><dd>{candidate.invalidation}</dd></div>
                          </dl>
                        </article>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            ) : (
              <p className="historyEmpty">本日の候補から保存を開始します。</p>
            )}
          </section>
          <section className="grid2">
            <article className="card">
              <div className="cardHead">
                <div>
                  <small>UNIVERSE CHECK</small>
                  <h3>全銘柄チェック</h3>
                </div>
                <span className={data.quality.passed ? "ok" : "ng"}>
                  {data.quality.passed ? "価格品質 OK" : "分析保留"}
                </span>
              </div>
              <div className="funnel">
                {Object.entries(data.funnel).map(([k, v]) => (
                  <div key={k}>
                    <span>{labels[k] ?? k}</span>
                    <b>{v.toLocaleString()}</b>
                  </div>
                ))}
              </div>
            </article>
            <article className="card">
              <div className="cardHead">
                <div>
                  <small>FRESHNESS GATE</small>
                  <h3>情報の鮮度・完全性</h3>
                </div>
              </div>
              <dl>
                <div>
                  <dt>全銘柄・公式価格</dt>
                  <dd className="okText">
                    {dateText(
                      data.quality.officialPriceDate ?? data.quality.priceDate,
                    )}{" "}
                    / {data.quality.latestCoverage.toLocaleString()}銘柄
                  </dd>
                </div>
                <div>
                  <dt>一次候補・当日補完</dt>
                  <dd
                    className={data.quality.provisionalCount ? "pending" : ""}
                  >
                    {dateText(data.quality.priceDate)} /{" "}
                    {data.quality.provisionalCount ?? 0}/
                    {data.quality.provisionalTotal ?? 30}銘柄
                  </dd>
                </div>
                <div>
                  <dt>取得資料</dt>
                  <dd>
                    {data.quality.files}ファイル・失敗{data.quality.failures}件
                  </dd>
                </div>
                <div>
                  <dt>最新ファンダ</dt>
                  <dd className="pending">{data.quality.fundamental}</dd>
                </div>
                <div>
                  <dt>決算予定・TDnet</dt>
                  <dd className="pending">
                    {data.quality.earningsDate} / {data.quality.tdnet}
                  </dd>
                </div>
              </dl>
            </article>
          </section>
          <section className="card sectorCard">
            <div className="cardHead">
              <div>
                <small>SECTOR ROTATION</small>
                <h3>次に資金が向かう33業種</h3>
              </div>
              <span>上位6業種</span>
            </div>
            <div className="sectorGrid">
              {data.sectorSignals?.slice(0, 6).map((s, i) => (
                <article key={s.name}>
                  <div>
                    <i>{i + 1}</i>
                    <b>{s.name}</b>
                    <em>{s.phase}</em>
                  </div>
                  <strong>
                    {s.score}
                    <small>/100</small>
                  </strong>
                  <p>
                    5日 {s.return5 > 0 ? "+" : ""}
                    {s.return5}% / 20日 {s.return20 > 0 ? "+" : ""}
                    {s.return20}%
                  </p>
                  <p>
                    広がり {s.breadth}%（{s.breadthChange > 0 ? "+" : ""}
                    {s.breadthChange}pt） / 代金比 {s.turnoverRatio}倍
                  </p>
                </article>
              ))}
            </div>
          </section>
          <section className="card outflowCard">
            <div className="cardHead">
              <div>
                <small>SECTOR OUTFLOW ALERT</small>
                <h3>お金が抜け始めたセクター</h3>
              </div>
              <span>{data.sectorOutflowAsOf?.replaceAll("-", "/") ?? dateText(data.asOf)} 基準</span>
            </div>
            <div className="outflowGuide">
              <b>スイング出口の早期警戒</b>
              <p>直近の下落・上昇失速・値上がり銘柄の減少・下落時の売買代金を合成した推定シグナルです。実際の資金流出額ではないため、個別銘柄の無効化ラインと併用してください。</p>
            </div>
            <div className="outflowList">
              {data.sectorOutflows?.slice(0, 6).map((sector, index) => (
                <article key={sector.name} className={sector.score >= 60 ? "outflowHigh" : sector.score >= 45 ? "outflowMid" : ""}>
                  <i>{index + 1}</i>
                  <div className="outflowName">
                    <b>{sector.name}</b>
                    <em>{sector.level}</em>
                  </div>
                  <strong>{sector.score}<small>/100</small></strong>
                  <div className="outflowMetrics">
                    <span>1日 <b>{sector.return1 > 0 ? "+" : ""}{sector.return1}%</b></span>
                    <span>5日 <b>{sector.return5 > 0 ? "+" : ""}{sector.return5}%</b></span>
                    <span>広がり <b>{sector.breadthChange > 0 ? "+" : ""}{sector.breadthChange}pt</b></span>
                    <span>代金比 <b>{sector.turnoverRatio}倍</b></span>
                  </div>
                  <p>{sector.reasons.join("・") || "相対的な弱含みを監視"}</p>
                  <mark>{sector.action}</mark>
                </article>
              ))}
            </div>
          </section>
          <section className="card candidates">
            <div className="cardHead">
              <div>
                <small>EARLY SETUP SHORTLIST</small>
                <h3>セクター内の先回り・初動候補</h3>
              </div>
              <span>{data.technicalCandidates.length} / 最大30</span>
            </div>
            <p className="guard">
              内部は小数点で連続評価し、表示のみ四捨五入しています。原則として異なる3セクターから1銘柄ずつ選定します。
            </p>
            <div className="table">
              <div className="tr th">
                <span>銘柄</span>
                <span>終値</span>
                <span>先回り点</span>
                <span>初動根拠</span>
                <span>無効化</span>
              </div>
              {data.technicalCandidates.slice(0, 10).map((c, i) => (
                <div className="tr" key={c.code}>
                  <span>
                    <i>{i + 1}</i>
                    <b>{c.name}</b>
                    <small>
                      {c.code}・{c.sector}
                    </small>
                  </span>
                  <span>
                    ¥{c.close.toLocaleString()}
                    <small className={c.provisional ? "pending" : ""}>
                      {c.provisional
                        ? `${dateText(c.priceDate ?? data.asOf)} 暫定`
                        : `${dateText(data.officialAsOf ?? data.asOf)} 公式`}
                    </small>
                  </span>
                  <span>
                    <b>{c.displayScore ?? Math.round(c.score)}/100</b>
                    <small>
                      {c.setup}・{c.sectorPhase}
                    </small>
                  </span>
                  <span>{c.reasons.join("・")}</span>
                  <span>{c.invalidation}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="card excluded">
            <div className="cardHead">
              <div>
                <small>EXTENDED / SKIP</small>
                <h3>上昇済みで見送った銘柄</h3>
              </div>
            </div>
            <div className="skipGrid">
              {data.excludedExtended?.slice(0, 6).map((c) => (
                <div key={c.code}>
                  <b>{c.name}</b>
                  <span>
                    {c.code}・{c.sector}
                  </span>
                  <em>{c.excludeReason}</em>
                </div>
              ))}
            </div>
          </section>
          <section className="card sources">
            <div className="cardHead">
              <div>
                <small>SOURCE LOG</small>
                <h3>参照元と基準日</h3>
              </div>
            </div>
            {data.sources.map((s) => (
              <div className="source" key={s.name}>
                <b>{s.name}</b>
                <span>{dateText(s.asOf)}</span>
                <em>{s.status}</em>
              </div>
            ))}
          </section>
        </>
      )}
      <footer>
        投資判断はご自身で行ってください。本画面は売買を推奨するものではなく、公開情報に基づく分析補助です。
        <button onClick={() => setChangelogOpen(true)}>CHANGELOG {changelog[0].version}</button>
        <div className="visitCounter" aria-label="このブラウザでのアクセス数">
          <span><small>LOCAL PV</small><b>{visitCounts?.total.toLocaleString() ?? "—"}</b></span>
          <i aria-hidden="true" />
          <span><small>TODAY</small><b>{visitCounts?.today.toLocaleString() ?? "—"}</b></span>
        </div>
        <div className="footerLegal">
          <small className="copyright">© 2026 katuya. All Rights Reserved.</small>
          <span aria-hidden="true">·</span>
          <button onClick={() => setDisclaimerOpen(true)} aria-haspopup="dialog" aria-expanded={disclaimerOpen}>免責事項</button>
        </div>
      </footer>
      {changelogOpen && (
        <div className="modalBackdrop" onMouseDown={() => setChangelogOpen(false)}>
          <section
            className="changelogModal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="changelog-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="changelogHeader">
              <div>
                <small>RELEASE NOTES</small>
                <h2 id="changelog-title">更新履歴</h2>
                <p>SWING SCOUTの機能追加と修正内容</p>
              </div>
              <button className="modalClose" onClick={() => setChangelogOpen(false)} aria-label="更新履歴を閉じる">×</button>
            </div>
            <div className="changelogList">
              {changelog.map((release, releaseIndex) => (
                <article key={release.version} className={releaseIndex === 0 ? "latestRelease" : ""}>
                  <div className="releaseMeta">
                    <b>{release.version}</b>
                    {releaseIndex === 0 && <em>最新版</em>}
                    <time dateTime={release.date}>{release.date.replaceAll("-", ".")}</time>
                  </div>
                  <h3>{release.title}</h3>
                  <ul>
                    {release.changes.map((change) => (
                      <li key={change.text}>
                        <span className={`changeType ${change.type}`}>{change.type === "fix" ? "修正" : "追加"}</span>
                        <p>{change.text}</p>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
      {disclaimerOpen && (
        <div className="modalBackdrop" onMouseDown={() => setDisclaimerOpen(false)}>
          <section
            className="disclaimerModal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="disclaimer-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="changelogHeader">
              <div>
                <small>IMPORTANT NOTICE</small>
                <h2 id="disclaimer-title">免責事項・ご利用上の注意</h2>
              </div>
              <button className="modalClose" onClick={() => setDisclaimerOpen(false)} aria-label="免責事項を閉じる">×</button>
            </div>
            <div className="disclaimerBody">
              <ul>
                <li>本サービス（SWING SCOUT）は、機械学習および技術的指標に基づいてデータを自動分析・表示するものであり、株式の売買を推奨・勧誘するものではありません。</li>
                <li>掲載データ（株価・指標・決算日等）の正確性には注意を払っておりますが、情報の遅延や誤りを保証するものではありません。</li>
                <li>投資に関する最終決定は、必ずご自身の判断と責任において行なってください。本サービスを利用したことによるいかなる損害についても、開発者は一切の責任を負いかねます。</li>
              </ul>
              <button className="disclaimerClose" onClick={() => setDisclaimerOpen(false)}>閉じる</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function PurchasePanel({ candidate, record, onSave, onRemove }: { candidate: Candidate; record?: PurchaseRecord; onSave: (record: PurchaseRecord) => void; onRemove: (code: string) => void }) {
  const stop = Number(candidate.invalidation.replaceAll(",", "").match(/[\d.]+/)?.[0] ?? 0);
  const pnlPct = record ? (candidate.close / record.price - 1) * 100 : null;
  const pnlYen = record ? (candidate.close - record.price) * record.shares : null;
  const stopDistance = record && record.price > 0 ? (record.price - stop) / record.price * 100 : null;
  const belowEntry = candidate.entryLower != null && candidate.close < candidate.entryLower;
  return (
    <section className="purchasePanel">
      <div className="purchaseHead"><b>MY TRADE</b><span>このブラウザにのみ保存</span></div>
      {record ? (
        <div className="purchaseSaved">
          <dl>
            <div><dt>購入価格</dt><dd>¥{record.price.toLocaleString()} × {record.shares}株</dd></div>
            <div><dt>購入日</dt><dd>{record.purchasedAt.replaceAll("-", "/")}</dd></div>
            <div><dt>購入価格から</dt><dd className={(pnlPct ?? 0) >= 0 ? "historyUp" : "historyDown"}>{pnlPct == null ? "—" : `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}% / ${pnlYen! >= 0 ? "+" : ""}¥${Math.round(pnlYen!).toLocaleString()}`}</dd></div>
            <div><dt>無効化まで</dt><dd>{stopDistance == null ? "—" : `${stopDistance.toFixed(2)}%`}</dd></div>
          </dl>
          {belowEntry && <p className="entryBreakWarning">⚠️ 現在値がエントリー下限を割れています。反発確認前の買い増しは避けてください。</p>}
          <button type="button" onClick={() => onRemove(candidate.code)}>購入記録を削除</button>
        </div>
      ) : (
        <form onSubmit={(event) => {
          event.preventDefault(); const form = new FormData(event.currentTarget);
          onSave({ code: candidate.code, name: candidate.name, price: Number(form.get("price")), shares: Number(form.get("shares")), purchasedAt: String(form.get("date")) });
        }}>
          <label>購入価格<input name="price" type="number" min="0.1" step="0.1" defaultValue={candidate.close} required /></label>
          <label>株数<input name="shares" type="number" min="1" step="1" defaultValue="100" required /></label>
          <label>購入日<input name="date" type="date" defaultValue={new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(new Date())} required /></label>
          <button type="submit">購入記録を保存</button>
        </form>
      )}
    </section>
  );
}
