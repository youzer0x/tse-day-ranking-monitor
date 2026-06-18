# tse-day-ranking-monitor（自動化ルーチン仕様）

東証 日中（レギュラー）値上がり率ランキングを**日次・無人**で生成し、**GitHub Pages（Web）＋ Gmail 通知**で配信する Claude クラウドルーチンの仕様。本ディレクトリは独立リポ `tse-day-ranking-monitor` として切り出すための**雛形**である（PTS 版 `pts-ranking-monitor` と同じ分担）。

## 方法論の単一の真実源

- 方法論（抽出条件・時価総額算出・厳密窓・変動要因の裏取り・文体・品質ゲート）は
  **`news-financial-market/skills/tse-day-ranking-digest/SKILL.md`** が単一の真実源。本ファイルはそれに準拠する。
- 配信実装（Pages の体裁・Gmail）は on-disk の `tdnet-monitor`（`html_generator.py`・`gmail_sender.py`・`docs/`）を下敷きにしている。

## 起動とゲート

- **cron：当日 18:10 JST**（J-Quants が当日の四本値 16:30・銘柄マスタ 17:30・財務速報 18:00 を反映済み。`reference-jquants-data-update-timing`）。
- **営業日ゲート**：`business_day.is_business_day(today)` が真のときのみ実行（休場日はスキップ）。
- 使用モデル：Sonnet 4.6・effort=max（PTS ルーチンに合わせる）。

## フロー

1. **ゲート**：`python scripts/check_gate.py` を実行。`SKIP`（休場）なら Pages もメールも更新せず即終了。`SESSION=YYYY-MM-DD` ならその日付を SESSION として続行。
2. **Stage1（決定的）**：`build_day_ranking.py --date <today> --out ranking.json` を実行（`JQUANTS_API_KEY` 必須）。
   - 抽出条件：東証個別株のみ／値上がり率≥+5%／売買代金≥¥10M／時価総額≥100億。`rows`/`dropped_turnover`/`dropped_mcap` を得る。
   - **掲載上限＝値上がり率上位50社**（該当が50社超なら上位50社のみ `rows` に入る。`--max-rank` 既定50）。`counts.qualifying`＝該当総数、`counts.ranked`＝掲載数。
3. **Stage2（Claude が変動要因をフル裏取り）**：`rows`（上位50社）各銘柄の `factor`/`factor_kind` を
   **[開示]（TDnet 前営業日15:30以降∪当日15:30未満）→[報道]（一次記事＋配信時刻を当日セッションに整合）→[テーマ]** の順で埋める。
   検索要約を出典にせず、材料未確認は正直に記す。個人発信は不使用。
4. **Publish**：`publish.py --in docs/tmp/ranking.json --docs docs --pages-url "$PAGES_URL" --send`
   - `docs/data/<date>.json` 保存（ランキング＋要因）／`docs/data/manifest.json` 更新／30日より古い JSON を削除。
   - `docs/index.html`（日付選択式 Pages）を更新。
   - メール HTML を生成し、`--send` で **Gmail API（HTTPS）送信**（`gmail_sender.send_gmail`）。
     クラウド環境は SMTP(465) を通さないため **PTS 版と同じ Gmail API 方式**を用いる。必要な環境変数は
     `GMAIL_CLIENT_ID`／`GMAIL_CLIENT_SECRET`／`GMAIL_REFRESH_TOKEN`／`GMAIL_ADDRESS`／`NOTIFY_TO`
     （リフレッシュトークンは `scripts/get_gmail_token.py` でローカル1回取得。SETUP.md 参照）。
5. **デプロイ（必ず main へ）**：`docs/index.html` と `docs/data/` を commit し、`git push origin HEAD:main`。
   GitHub Pages は **main/docs** を配信するため、クラウドが `claude/` ブランチ上にいても **main へ直接 push**する（PR は作らない。リポジトリは unrestricted branch push 許可）。`docs/tmp/` はコミットしない。

## レポート（任意）

- オンデマンド版と同じ `である調` 全文を `reports/tse-day-rankings/<date>_tse-day-gainers.md` 相当として併せて出力してよい（リポ運用に合わせる）。

## 関連

- 方法論：`skills/tse-day-ranking-digest/SKILL.md`
- 配信下敷き：`project-private/tdnet-monitor`（Pages＋Gmail）
- ルーチン方式の先行例：`pts-ranking-monitor`（PTS ナイト版・cron 06:06 JST）
