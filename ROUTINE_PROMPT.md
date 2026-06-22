# ルーチン用プロンプト（Scheduled トリガにそのまま貼り付ける文面）

> claude.ai のルーチン（スケジュール）作成フォームの「プロンプト」欄に、下の```で囲んだ本文をコピーして貼り付ける。
> モデル＝**Sonnet 4.6**、effort＝**max**、スケジュール＝**毎日 18:10 JST**、リポジトリ＝`tse-ranking-monitor`、
> 環境＝先に作成したカスタム環境（環境変数・ネット許可・setup 入り）を選ぶ。

```
あなたはこのリポジトリ tse-ranking-monitor の AGENTS.md に厳密に従い、日本株の東証 日中（レギュラー）セッション（当日 09:00–15:30＝前場9:00-11:30/後場12:30-15:30）の株価上昇率ランキング（値上がり専用）を日次・無人で生成し、GitHub Pages と Gmail で配信するルーチンである。まず AGENTS.md を読み、その手順に従うこと。要点：

1. 営業日ゲート: `python scripts/check_gate.py` を実行。出力が SKIP なら、Pages もメールも更新せず即終了する（生成しない）。出力が SESSION=YYYY-MM-DD なら、その日付を SESSION として続行する。

2. 素データ生成: `python scripts/build_day_ranking.py --date <SESSION> --out docs/tmp/ranking.json` を実行する。抽出条件は東証個別株のみ・値上がり率≥前日比+5% かつ 売買代金≥¥10,000,000・時価総額≥100億円（スクリプトが適用済み）。掲載上限は値上がり率上位50社で、該当が50社を超える場合は上位50社のみが rows に入る（counts.qualifying=該当総数、counts.ranked=掲載数、capped=上限適用の有無）。各 row.disclosures に「前営業日15:30以降 ∪ 当日15:30未満」の TDnet 開示が入っている。

2.5. （任意・env TSE_USE_GROK=1 のときのみ）変動要因リサーチの grok 委譲: `python scripts/grok_research.py --in docs/tmp/ranking.json --out-dir docs/tmp/research` を実行し、各銘柄の DIGEST_BLOCK 付き研究ファイル（xAI Grok API・web_search ツール）を生成する。TSE_USE_GROK が未設定/0 のときは本ステップを実行しない（従来どおり Claude 完結）。grok_research.py がエラー・API 失敗のときは、その回は grok を使わず通常の裏取り（下記3）を行う。

3. 変動要因の裏取り（中核）: rows（上位50社）の各銘柄について「なぜ日中に上昇したか」を埋める。（TSE_USE_GROK=1 で grok を使った場合）docs/tmp/research/<code>-<name>-<date>.md を code×session_date で取り込む。研究本文を主入力とし（DIGEST_BLOCK は索引・要約で単独依存しない＝当日ドライバーを取りこぼす）、(a) ランディングページ出典（Yahoo /quote・日経会社ページ・株探銘柄トップ等）を全削除、(b) factor に使う数値を J-Quants/一次開示で再検証、(c) 窓外材料は「背景」に格下げ、のうえ3層ソース再検証（sources_used=①中核whitelistは採用／sources_new_candidate=②ルーブリック〔確立した報道機関・調査会社の編集記事／主体明確／検証可能な配信時刻URL〕合格なら採用しwhitelist昇格候補に記録／sources_excluded=③個人発信・匿名・純アルゴ生成は不採用）＋window_ok/trigger_time の厳密窓整合を確認して factor/factor_kind を起こす（発見はgrok・判定はClaude）。DIGEST_BLOCK 欠落・検証落ち・窓不整合の行、および検証合格率が掲載行の半数未満のときは、以下の通常手順で裏取りする：[開示]（前営業日15:30以降∪当日15:30未満の TDnet 開示）→[報道]（主要メディアの一次記事を WebSearch で探し、記事本文と配信時刻を確認して当日セッション〔前営業日引け後〜当日15:30〕との整合で裏取り）→[テーマ]（個別材料が無い場合のみ）の優先順で特定し、各 row の factor（日本語説明）と factor_kind（開示/報道/テーマ）を埋める。証券会社のレーティング変更（投資判断・目標株価）も必ずカバーすること：TDnet には出ないため、開示が無いのに日中上昇した銘柄は株探の銘柄ニュース https://kabutan.jp/stock/news?code=<4桁> （ブラウザUA）の「レーティング日報」「材料」を確認し、寄り前に伝わった格上げ・目標株価引き上げ（当日15:30より前）は factor_kind=報道 として証券会社名・旧→新の投資判断/目標株価を具体的に記す。当日15:30ちょうどの開示は日中に反応不能なので要因にしない（今夜のPTS材料）。検索結果の要約をそのまま出典にしない。材料が確認できなければ factor に「当日固有の材料は確認できず」等と正直に記す。個人発信（X個人・note・個人ブログ・掲示板・YouTube個人・匿名まとめ・生成系）は引用も参照もしない。数値は実測のみ・創作禁止・投資助言をしない。編集後 docs/tmp/ranking.json を上書き保存する。

4. 公開＋通知: `python scripts/publish.py --in docs/tmp/ranking.json --docs docs --pages-url "$PAGES_URL" --send` を実行する（docs/data/<SESSION>.json 保存・manifest 更新・index.html 再生成・Gmail API 送信）。

5. commit & push（必ず main へ）: docs/index.html と docs/data/ をコミットし、デフォルトブランチ main に push する。GitHub Pages は main/docs を配信するため claude/ ブランチに push しても反映されない。クラウドセッションが claude/ ブランチ上にいても、必ず `git add docs/index.html docs/data && git commit -m "Update TSE day gainers <SESSION>" && git push origin HEAD:main` で main へ直接 push する（PR は作らない／本リポジトリは unrestricted branch push 許可済み）。docs/tmp/ はコミットしない。

最後に、SESSION・該当社数（50社超なら「該当M社／上位50社を掲載」）・主要な変動要因の要約を1段落で報告すること。エラー時は原因と対処を報告する。
```
