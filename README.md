# SWING SCOUT — standalone edition

ChatGPT Sites / Work / agent executionを日次運用から外した、GitHub Actions + GitHub Pages構成です。

## Architecture

1. GitHub Actionsが平日16:10、17:10、18:10（JST）に実行
2. JPX日報と上場銘柄一覧、Yahoo Finance公開終値、JPX決算予定表等を取得
3. 全銘柄スクリーニング、33業種資金循環、決算・権利リスク、最大3候補を計算
4. `public/data/latest.json`、`history.json`、`status.json`を生成してコミット
5. Reactの静的サイトをGitHub Pagesへ公開
6. ブラウザは生成済みJSONを読むだけで、閲覧時に銘柄スキャンを行わない

流動性は、直近20日平均売買代金3億円以上、かつ20日のうち15日以上で売買代金1億円以上を必須条件とします。出来高需給は、当日出来高÷過去20営業日中央値のRelative Volume、株価方向、終値位置、直近3日の安値トレンドと価格維持を組み合わせます。「出来高枯れ→再増加」を優先し、出来高減少は価格が崩れていない場合だけ売り枯れ候補として加点します。出来高急増や高値ブレイクは必須条件にしません。

更新処理はデータ全体を退避してから実行し、取得・生成・テストのいずれかで失敗した場合は全ファイルを復元します。その後、`status.json`と`update-diagnostics.json`へ今回の失敗理由を記録します。公開ジョブには検証済み、または復元済みの候補・履歴・状態・診断JSONだけを渡します。

GitHub Actionsはデータ更新とPages公開を別ジョブで表示します。更新失敗は更新ジョブで失敗として通知し、復元済みデータのPages公開は独立して実行します。公式データの公開待ちは失敗扱いにしません。

## Data sources

- 株価・出来高・売買代金・上場区分：JPX東京証券取引所日報を主系統
  - 公式ページが参照する月別配信一覧（新形式JSON・旧形式HTML）から直近250営業日の株式相場表PDFを取得します。月別一覧やPDFが欠けた場合は、既存のスナップショットを上書きせず停止します。
  - 朝の公開待ち判定も同じ配信一覧の最新日付を参照します。英数字コードと5桁の優先株コードは別銘柄として保持します。
- 当日終値補完：Yahoo Finance公開チャート（公式値より新しく、全候補で同じ日付の場合のみ使用）
- セクタープロキシ・指数ETF：取得済みJPX日報の終値。代表銘柄・等ウェイト計算は維持し、全業種・指数の最終日を公式スナップショットと一致させます。
- 業種：JPX上場銘柄一覧の東証33業種
- 決算予定：JPX予定表 + Yahoo!ファイナンス + 株予報
- 権利落ち：JPX権利落ち予定情報 + Yahoo!ファイナンス株主優待 + TDnet掲載一覧

決算日が未確認、未定、情報源間で不一致、3営業日以内の銘柄は最終候補から除外します。権利落ちについても3営業日以内、日付不一致、基準日・株主優待に関する直近開示がある銘柄を除外します。JPX権利データを取得できない場合や、Yahoo!ファイナンス・TDnet掲載一覧の確認率が80%未満の場合は正常データを更新しません。

## First deployment

1. このディレクトリをGitHubリポジトリのルートへpush
2. GitHubの **Settings → Pages → Source** を **GitHub Actions** に設定
3. **Actions → SwingScout daily update and Pages → Run workflow** を実行
4. `status.json`がsuccess、Pages URLで最新日・最大3候補・履歴を確認

通常運用ではChatGPTを開く必要はありません。コード変更時だけ任意で利用できます。

## Local verification

```bash
npm ci
python scripts/build-jpx-snapshot.py
node scripts/fetch-sector-data.mjs
python scripts/build-analysis-seed.py
python scripts/generate-static-data.py
python scripts/compare-volume-logic.py
npm run test:data
npm run build
npm run dev
```

購入価格・株数・購入日は`localStorage`へ保存され、サーバーや他ユーザーへ送信されません。端末やブラウザを変えると引き継がれません。

前回正常データの復元を含む全工程のローカル検証は`python scripts/run-data-pipeline.py`で実行できます（先に`npm ci`、`pip install xlrd openpyxl`と`pdftotext`の準備が必要です）。
