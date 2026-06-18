# tse-day-ranking-monitor セットアップ手順

東証 日中（レギュラー）値上がり率ランキングを**日次・無人**で生成し、**GitHub Pages（Web）＋ Gmail（API）**で配信するための手順。PTS 版 `pts-ranking-monitor` と**同じ構成・同じ Gmail 方式・Claude のスケジュール（ルーチン）機能**で運用する。方法論は `news-financial-market/skills/tse-day-ranking-digest/SKILL.md`、ルーチン仕様は本ディレクトリの `AGENTS.md`、貼り付けプロンプトは `ROUTINE_PROMPT.md`。

> 用意するもの：GitHub アカウント／Gmail アカウント＋ Google Cloud（無料・OAuth クライアント作成に使用）／J-Quants の **Light 以上**の API キー／Claude（Claude Code のルーチンが使えるアカウント）。
>
> メール送信について：クラウド環境は HTTP/HTTPS プロキシ経由で動くため Gmail の **SMTP（ポート465）は使えない**。本システムは PTS 版と同じ **Gmail API（HTTPS）** で送信する（送信先 `*.googleapis.com` は既定の許可リストに含まれる）。
>
> 環境変数・ネット許可・初期化は**すべて claude.ai 側**で設定する（GitHub Secrets はルーチンから読めない＝不使用）。専用の秘密保管庫は無く、認証情報も環境変数に入れる（個人ルーチンは非共有なので自分だけが見える）。

---

## Step 0：スクリプトを揃える（リポに同梱されていない Stage1 一式をコピー）

本ディレクトリには `scripts/publish.py`・`scripts/gmail_sender.py`・`scripts/get_gmail_token.py`・`scripts/check_gate.py` が同梱済み。**Stage1 のパイプライン一式をスキルからコピー**する：

```bash
cd /c/Users/YujiroOkawa/project-private/news-financial-market/automation/tse-day-ranking-monitor
cp ../../skills/tse-day-ranking-digest/scripts/{build_day_ranking.py,jquants.py,kabutan_pts.py,tdnet.py,business_day.py,market_cap_jquants.py,market_cap_yahoo.py} scripts/
```

ファイル構成（完成形）：
```
tse-day-ranking-monitor/
├── AGENTS.md                 # ルーチン仕様（方法論の真実源はスキル SKILL.md）
├── ROUTINE_PROMPT.md         # スケジュール作成フォームに貼る本文
├── scripts/
│   ├── build_day_ranking.py  # Stage1（決定的）※スキルからコピー
│   ├── jquants.py / tdnet.py / business_day.py / kabutan_pts.py
│   ├── market_cap_jquants.py / market_cap_yahoo.py
│   ├── check_gate.py         # 営業日ゲート（SESSION=日付 / SKIP を出力）
│   ├── publish.py            # Pages JSON/SPA ＋ メール HTML 生成・送信
│   ├── gmail_sender.py       # Gmail API（HTTPS）送信（PTS と同方式）
│   └── get_gmail_token.py    # ローカル1回：リフレッシュトークン取得
├── docs/                     # GitHub Pages（index.html・data/ は publish.py が生成）
├── requirements.txt
└── SETUP.md
```

---

## Step 1：GitHub にリポジトリを作る

1. https://github.com で右上「＋」→「New repository」。
2. **Repository name**：`tse-day-ranking-monitor`／公開範囲：**Public**（Pages を無料で使うため）／「Add a README file」のチェックは**外す**。
3. 「Create repository」。表示される URL（`https://github.com/<あなた>/tse-day-ranking-monitor.git`）を控える。

## Step 2：このフォルダを GitHub にアップロード

最も簡単なのは Claude Code に「このリポジトリを GitHub にプッシュして」と頼む方法。自分で行う場合（Git Bash）：
```bash
cd /c/Users/YujiroOkawa/project-private/news-financial-market/automation/tse-day-ranking-monitor
git init && git add . && git commit -m "Initial commit: TSE day ranking monitor"
git branch -M main
git remote add origin https://github.com/<あなた>/tse-day-ranking-monitor.git
git push -u origin main
```
> 本ディレクトリは `news-financial-market` リポの一部なので、独立リポにするなら**この `tse-day-ranking-monitor` フォルダだけを別の場所へコピーしてから** `git init` するのが安全。

## Step 3：Claude の GitHub App をリポジトリに入れる

1. https://github.com/apps/claude を開く →「Install」（導入済みなら「Configure」）。
2. 「Only select repositories」で `tse-day-ranking-monitor` を選択。
3. 権限は **Contents: Read and write** を許可（クラウドの Claude が clone し `docs/` を push するため）。

## Step 4：GitHub Pages を有効にする

1. リポジトリ「Settings」→「Pages」。
2. **Source**：「Deploy from a branch」。**Branch**：「main」/ Folder「**/docs**」→「Save」。
3. 数分後 `https://<あなた>.github.io/tse-day-ranking-monitor/` で公開される。

---

## Step 5：Gmail API の認証情報を用意する（通知メール送信用・無料・1回だけ）

クラウドでは SMTP が使えないため Gmail API（HTTPS）で送る。Google Cloud で OAuth クライアントを作り、リフレッシュトークンを取得する。

1. **プロジェクト作成**：https://console.cloud.google.com に通知元 Gmail でログイン →「新しいプロジェクト」→ 名前 `TSE Day Ranking Monitor` → 作成 → 選択。
2. **Gmail API を有効化**：上の検索窓で「Gmail API」→「有効にする」。
3. **OAuth 同意画面**：「APIとサービス」→「OAuth 同意画面」→ User Type「外部」→ アプリ名 `TSE Day Ranking Monitor`、サポートメール＝自分、連絡先＝自分 →「保存して次へ」。スコープはそのまま →「保存して次へ」。テストユーザーに**自分の Gmail を追加**。
   - **重要**：最後に「**アプリを公開**（本番にする / Publish app）」を実行する。テストのままだとリフレッシュトークンが**7日で失効**し自動実行が1週間で止まる。本番にすれば失効しない（個人利用なので「未確認アプリ」警告は出るが問題ない）。
4. **OAuth クライアント ID 作成**：「認証情報」→「認証情報を作成」→「OAuth クライアント ID」→ 種類「**デスクトップ アプリ**」→ 作成。表示される **クライアント ID** と **クライアントシークレット** を控える。
5. **リフレッシュトークン取得**（手元の Git Bash で1回だけ）：
   ```bash
   cd /c/Users/YujiroOkawa/project-private/news-financial-market/automation/tse-day-ranking-monitor
   python scripts/get_gmail_token.py
   ```
   - クライアント ID／シークレットを貼り付け → ブラウザで自分の Google アカウントを選択。
   - 「このアプリは Google で確認されていません」が出たら「詳細」→「（アプリ名）に移動」→ Gmail 送信を「続行」。
   - ターミナルに出る `GMAIL_REFRESH_TOKEN=...` を控える。
6. これで **クライアント ID／クライアントシークレット／リフレッシュトークン**の3つが揃う（Step 7 で登録）。

## Step 6：J-Quants の API キーを用意する

- J-Quants（https://jpx-jquants.com）の **Light プラン以上**の `x-api-key` 用キーを控える。**Free は当日値が取れない（遅延）ため不可**。

## Step 7：Claude に「カスタム環境」を作る（環境変数・ネット許可・初期化）

1. https://claude.ai/code/routines で **New routine**（または既存の鉛筆＝Edit）。Instructions 欄下の**雲アイコン**（最初は `Default`）→「Add environment / 環境を追加」→ 名前 `tse-day-ranking-monitor`（"Default" は共有なので使わない）。
2. **環境変数**（`.env` 形式・1行 `KEY=value`・**引用符で囲まない**）：
   ```
   JQUANTS_API_KEY=（Step 6 の J-Quants API キー）
   GMAIL_CLIENT_ID=（Step 5 のクライアント ID）
   GMAIL_CLIENT_SECRET=（Step 5 のクライアントシークレット）
   GMAIL_REFRESH_TOKEN=（Step 5 のリフレッシュトークン）
   GMAIL_ADDRESS=（送信元の Gmail アドレス）
   NOTIFY_TO=okawa.yujiro@gmail.com
   TZ=Asia/Tokyo
   PAGES_URL=https://<あなた>.github.io/tse-day-ranking-monitor/
   ```
   - `TZ` … 営業日ゲートの日付判定を JST に固定（**必須**。これが無いと当日判定がずれる）。
   - `NOTIFY_TO` … カンマ区切りで複数可。
3. **ネットワーク許可（Network access）**：既定 `Trusted` だと外部サイトが `403` になる。次のどちらか：
   - **おすすめ＝`Full`**：すべて許可（記事取得が確実）。
   - **`Custom`**：「Allowed domains」に `api.jquants.com`／`www.release.tdnet.info`／`finance.yahoo.co.jp`／`kabutan.jp`／報道各社（`nikkei.com`・`asia.nikkei.com`・`reuters.com`・`bloomberg.com`・`wsj.com`・`ft.com`・`cnbc.com`・`jiji.com`・`kyodonews.jp`・`toyokeizai.net`・`diamond.jp` 等）を1行ずつ。**「Also include default list of common package managers」に必ずチェック**（pip と Gmail API `*.googleapis.com` のため）。
   - Gmail API の `gmail.googleapis.com`・`oauth2.googleapis.com` は既定の `*.googleapis.com` に含まれ**追加不要**。
4. **セットアップ・スクリプト（Setup script）**：クラウドの setup はリポジトリ外で走るため `-r requirements.txt` は使えない。パッケージ名を直接、PEP668 フォールバック付きで（クォートや `>=` は貼付で化けるので使わない）：
   ```bash
   pip install requests beautifulsoup4 lxml jpholiday || pip install --break-system-packages requests beautifulsoup4 lxml jpholiday
   ```
5. 「Save changes」。

## Step 8：スケジュール・ルーチンを作る

1. claude.ai の Claude Code ルーチン作成画面（Routines / スケジュール）を開く。
2. 設定：
   - **リポジトリ**：`tse-day-ranking-monitor`
   - **環境**：Step 7 の `tse-day-ranking-monitor`
   - **モデル**：**Sonnet 4.6**／**effort**：**max**
   - **スケジュール（cron）**：毎日 **18:10 JST**（タイムゾーン欄があれば Asia/Tokyo で `10 18 * * *`。UTC 指定なら `10 9 * * *` ＝ 09:10 UTC）
   - **プロンプト**：`ROUTINE_PROMPT.md` の```で囲んだ本文をそのまま貼り付け。
3. **Permissions タブ（フォーム最下部・リポジトリ追加後に出る）で「Allow unrestricted branch pushes」を ON**。これが無いとクラウドが `claude/` ブランチにしか push できず、Pages（main/docs）に反映されない。
4. 保存。

> **18:10 JST の根拠**：J-Quants は当日の四本値を約16:30、銘柄マスタ（市場区分）を約17:30、財務速報を約18:00 に反映する。マスタ反映後に余裕をもって起動する（PTS 版は前営業日ゲート・朝06:06 で対象セッションが異なる）。

## Step 9：初回テスト

1. ルーチンの「今すぐ実行 / Run now」で手動実行（**当日が東証営業日**なら最新セッションで動く。休場日は `check_gate.py` が `SKIP` を返して何もせず終了）。
2. 実行ログにエラーが無いことを確認。
3. 確認：
   - Web：`https://<あなた>.github.io/tse-day-ranking-monitor/` に当日ランキング（該当が50社超なら**上位50社**）と変動要因、サマリ「該当M社（上位50社を掲載）」が出る。
   - メール：`NOTIFY_TO` 宛に「[東証日中ランキング] YYYY-MM-DD｜…社該当（・上位50社）」が届く。
   - リポジトリ：`docs/data/` に新しい `YYYY-MM-DD.json`（`count_total`／`count`／`capped` 入り）が追加され、**main** に push されている。

以上で日次自動が稼働する。以後 毎日 18:10 JST に自動生成（休場日はスキップ）。

---

## 手元での手動実行（任意・動作確認用）

```bash
cd /c/Users/YujiroOkawa/project-private/news-financial-market/automation/tse-day-ranking-monitor
python scripts/check_gate.py                                   # SESSION=YYYY-MM-DD / SKIP
python scripts/build_day_ranking.py --date YYYY-MM-DD --out docs/tmp/ranking.json
# （必要なら docs/tmp/ranking.json の各 row の factor/factor_kind を編集）
python scripts/publish.py --in docs/tmp/ranking.json --docs docs --pages-url "$PAGES_URL"        # 送信なし
python scripts/publish.py --in docs/tmp/ranking.json --docs docs --pages-url "$PAGES_URL" --send  # Gmail 送信あり
```

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| 時価総額が「—」 | `JQUANTS_API_KEY` 未設定／Light 未満（Free は当日値なし）。新規上場は Yahoo 側も失敗時に発生 |
| 当日データが空 | 18:10 より前に実行していないか（四本値16:30・マスタ17:30 反映後に起動）。休場日でないか（`check_gate.py` が `SKIP`） |
| メール不達 | Gmail API の3変数（CLIENT_ID/SECRET/REFRESH_TOKEN）と `GMAIL_ADDRESS` を確認。**OAuth 同意画面を本番公開**したか（テストだと7日で失効） |
| Pages が `claude/...` に出て未反映 | ルーチンの「Allow unrestricted branch pushes」ON＋プロンプトの `git push origin HEAD:main` を確認 |
| Pages 未表示 | Settings → Pages の Branch=main / Folder=/docs を確認 |
| pip が `externally-managed` で失敗 | setup script のフォールバック `|| pip install --break-system-packages ...` が入っているか |
