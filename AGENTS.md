# tse-ranking-monitor（自動化ルーチン仕様）

東証 日中（レギュラー）値上がり率ランキングを**日次・無人**で生成し、**GitHub Pages（Web）＋ Gmail 通知**で配信する Claude クラウドルーチンの仕様。本ディレクトリは独立リポ `tse-ranking-monitor` として切り出すための**雛形**である（PTS 版 `pts-ranking-monitor` と同じ分担）。

## 方法論の単一の真実源

- 方法論（抽出条件・時価総額算出・厳密窓・変動要因の裏取り・文体・品質ゲート）は
  **`news-financial-market/skills/tse-ranking-digest/SKILL.md`** が単一の真実源。本ファイルはそれに準拠する。
- 配信実装（Pages の体裁・Gmail）は on-disk の `tdnet-monitor`（`html_generator.py`・`gmail_sender.py`・`docs/`）を下敷きにしている。

## 起動とゲート

- **cron：当日 18:10 JST**（J-Quants が当日の四本値 16:30・銘柄マスタ 17:30・財務速報 18:00 を反映済み。`reference-jquants-data-update-timing`）。
- **営業日ゲート**：`business_day.is_business_day(today)` が真のときのみ実行（休場日はスキップ）。
- 使用モデル：Sonnet 4.6・effort=max（PTS ルーチンに合わせる）。

## フロー

1. **ゲート**：`python scripts/check_gate.py` を実行。`SKIP`（休場）なら Pages もメールも更新せず即終了。`SESSION=YYYY-MM-DD` ならその日付を SESSION として続行。
2. **Stage1（決定的）**：`build_day_ranking.py --date <today> --kabutan-news --out ranking.json` を実行（`JQUANTS_API_KEY` 必須）。
   - 抽出条件：東証個別株のみ／値上がり率≥+5%／売買代金≥¥10M／時価総額≥100億。`rows`/`dropped_turnover`/`dropped_mcap` を得る。
   - **掲載上限＝値上がり率上位50社**（該当が50社超なら上位50社のみ `rows` に入る。`--max-rank` 既定50）。`counts.qualifying`＝該当総数、`counts.ranked`＝掲載数。
   - 各 row に **`sector_cluster`**（同一33業種＝`S33` で当日ともに上昇した co-mover ＋ leader 候補）が付き、トップレベルに **`theme_clusters`**（クラスタ要約）が入る（Stage2 のセクター連動クロスチェックに使う）。
   - **`--kabutan-news`** を付けると各 row（上位50社）の **`kabutan_news[]`**（株探 材料・特集〔レーティング日報〕・5%ルール等の直近見出し＋時刻。テクニカル定型ノイズは除外）が事前充填され、Stage2 で「材料未確認」へ落とす前の確認材料になる。best-effort（失敗時は空配列）。
2.5. **（任意・既定 off）grok 委譲リサーチ**：env **`TSE_USE_GROK=1`** のときのみ実行。
   `python scripts/grok_research.py --in docs/tmp/ranking.json --out-dir docs/tmp/research --top 25` を実行し、
   **上昇率上位25社**の変動要因を **xAI Grok API**（`XAI_API_KEY`・web_search ツール）でリサーチ → `<code>-<name>-<date>.md`（末尾に DIGEST_BLOCK）を生成する（**APIコスト削減方針：grok は上位25社まで。26位以降は Stage2 で Claude〔手順B〕が裏取り**）。
   `TSE_USE_GROK` 未設定/0 のときは本ステップを**完全にスキップ**（従来の Claude 完結フローと同一）。`grok_research.py` がエラー・API 失敗のときも、その回は grok を捨てて Stage2 を全行 Claude で実施する。
   方法論・プロンプトは `skills/tse-ranking-digest/grok/`（共有雛形）・`reference/sources.md §4`（3層ソース方針）に準拠。
3. **Stage2（変動要因の充填）**：`rows`（上位50社）各銘柄の `factor`/`factor_kind` を
   **[開示]（TDnet 前営業日15:30以降∪当日15:30未満）→[報道]（一次記事＋配信時刻を当日セッションに整合）→[セクター連動クロスチェック]→[テーマ]** の順で埋める。
   検索要約を出典にせず、材料未確認は5パス確認後にのみ正直に記す（詳細は `SKILL.md §5 手順B`）。
   - **`TSE_USE_GROK=1` のとき（手順B'）**：Stage2.5 の `docs/tmp/research/<code>-<name>-<date>.md` を `code`×`session_date` で取り込む。
     **研究本文を主入力**とし（DIGEST_BLOCK は索引・要約で単独依存しない＝当日ドライバーを取りこぼす）、取り込み時に **(a) ランディングページ出典の全削除（Yahoo `/quote`・日経会社ページ・株探銘柄トップ等）・(b) 数値を J-Quants/一次開示で再検証・(c) 窓外材料は「背景」に格下げ** を行い、
     **3層ソース再検証**（`sources_used`=採用／`sources_new_candidate`=ルーブリック再評価のうえ採用＋whitelist 昇格候補に記録／`sources_excluded`=不採用）＋`window_ok`/`trigger_time` の厳密窓整合を確認して `factor`/`factor_kind` を起こす（**発見は grok・判定は Claude**）。
     **研究ファイル欠落・検証落ち・窓不整合の行は従来の Claude 裏取りに fallback**。検証合格率が掲載行の半数未満なら grok を捨てて全行 Claude。
   - **ソース規律（3層方針）**：①中核 whitelist は採用、②良質な非whitelist（フィスコ・みんかぶ編集記事等）はルーブリック合格なら採用、③個人発信・匿名・純アルゴ生成は不使用（`reference/sources.md §4`）。
   - **証券会社のレーティング変更（投資判断・目標株価）も必ずカバーする**。TDnet には出ないため、`disclosures` が空なのに日中上昇した銘柄は **株探の銘柄ニュース `https://kabutan.jp/stock/news?code=<4桁>`（ブラウザ UA）の「レーティング日報」「材料」**を確認する（`--kabutan-news` 実行時は各 row の `kabutan_news[]` に充填済み）。寄り前に出た格上げ・目標株価引き上げ（当日15:30より前に伝わったもの）は日中上昇の有力材料。証券会社名・旧→新の投資判断/目標株価を具体的に記し、区分は `[報道]`。
   - **セクター連動クロスチェック（必須）**：各 row の `sector_cluster`／トップレベル `theme_clusters` を読み、同一33業種で束で動いた銘柄は、クラスタ内で具体的[開示]を持つ銘柄（`has_disclosure=true`。`leader_code` は機械的ヒントなので開示内容を読んで真の牽引役を選び直す）を名指しで根拠化し `[テーマ]`（連鎖）として帰属する。業種をまたぐテーマ（例：光部品＝非鉄金属〔電線〕＋電気機器〔光部品〕＋精密機器）は各クラスタの leader と地合いから横断的に結ぶ。**同一テーマの co-mover を材料未確認で放置しない**。連鎖／継続（決算後ドリフト）／需給（前日反動・薄商い）の別は本文で書き分ける（区分は3タグ維持）。
   - **材料未確認ゲート**：「材料未確認」は (i)`disclosures` (ii)`kabutan_news`（株探材料/レーティング） (iii)Web 検索 `<コード> <銘柄名> 急騰/ストップ高` (iv)`sector_cluster` の leader 連動 (v)（M&A観・出来高急増の小型株は）EDINET の TOB/大量保有 を**すべて確認**してもなお当日窓に材料が無い行にのみ残す。**ペイウォールで本文が取れないだけで即材料未確認にしない**（他の①②媒体で二次裏取り→当日テーマへの帰属が成れば [テーマ]）。
   - **EDINET（任意・環境依存）**：EDINET DB MCP が利用可能な環境では、買収観・大量保有が疑われる行で TOB（公開買付届出）・大量保有報告書を一次情報として確認する。MCP が無い環境では本パスは任意で、既存パスへフォールスルーする（**ハードな依存にしない**）。
4. **Publish（生成のみ・メールは送らない）**：`publish.py --in docs/tmp/ranking.json --docs docs --pages-url "$PAGES_URL"`
   - `docs/data/<date>.json` 保存（ランキング＋要因）／`docs/data/manifest.json` 更新／30日より古い JSON を削除。
   - `docs/index.html`（日付選択式 Pages）を更新（体裁は `html_generator.py`＝PTS 版と同一トンマナ・配色）。保存 JSON は rows に開示（pdf_url）を含むフルデータ。
   - メール HTML を生成・保存する**が、この段階では送信しない**（`--send` は付けない。送信は step6）。
5. **デプロイ（必ず main へ）**：`docs/index.html` と `docs/data/` を commit し、`git push origin HEAD:main`。
   GitHub Pages は **main/docs** を配信するため、クラウドが `claude/` ブランチ上にいても **main へ直接 push**する（PR は作らない。リポジトリは unrestricted branch push 許可）。`docs/tmp/` はコミットしない。
6. **メール通知（Pages 反映後に送信）**：`publish.py --in docs/tmp/ranking.json --docs docs --pages-url "$PAGES_URL" --notify`
   - **GitHub Pages が当日 SESSION を実際に配信し始める**（`data/manifest.json` の最新日付＝SESSION になる）まで
     キャッシュ無効化付きで**最大5分ポーリング**し、確認後にメール HTML を **Gmail API（HTTPS）送信**（`gmail_sender.send_gmail`）。
     クラウド環境は SMTP(465) を通さないため **PTS 版と同じ Gmail API 方式**を用いる。必要な環境変数は
     `GMAIL_CLIENT_ID`／`GMAIL_CLIENT_SECRET`／`GMAIL_REFRESH_TOKEN`／`GMAIL_ADDRESS`／`NOTIFY_TO`
     （リフレッシュトークンは `scripts/get_gmail_token.py` でローカル1回取得。SETUP.md 参照）。
   - **必ず step5 の push の後**に実行する。push 前にメールを送ると、読者がリンクを開いた時点で Pages が
     まだ前コミット（最新日付＝前営業日）を返し、当日分が見えない（=メールのリンク先ラグ）。`--notify` はその窓を閉じる。
   - ライブ確認の取得先は Pages ホスト（`*.github.io`）。ルーチンのカスタム環境の**ネット許可に `*.github.io` を含める**こと
     （未許可だと毎回失敗→5分後に送信＝従来同様ラグが残る）。`--notify` は生成・コミットを行わない（step4/5 済み前提）。

## レポート（任意）

- オンデマンド版と同じ `である調` 全文を `reports/tse-rankings/<date>_tse-gainers.md` 相当として併せて出力してよい（リポ運用に合わせる）。

## 関連

- 方法論：`skills/tse-ranking-digest/SKILL.md`
- 配信下敷き：`project-private/tdnet-monitor`（Pages＋Gmail）
- ルーチン方式の先行例：`pts-ranking-monitor`（PTS ナイト版・cron 06:06 JST）
