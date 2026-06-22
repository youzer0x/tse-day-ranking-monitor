"""自動版（schedule 統合）: 各銘柄の変動要因を xAI Grok API でリサーチし、リサーチ本文＋末尾
DIGEST_BLOCK の研究ファイル（grok レスポンス全文）を生成する。Claude は後段（手順B'）でこの
**本文を主入力**として読み（DIGEST_BLOCK は索引／構造化サマリで単独依存しない＝当日ドライバーを
取りこぼす）、ランディングページ出典の削除・数値の一次再検証・窓外材料の背景格下げを経て
factor/factor_kind を起こす（発見は grok・判定と出典規律は Claude）。

- クラウドルーチンは**ローカルの grok build CLI に到達できない**ため、自動版は xAI Grok API を使う。
- プロンプトは `../grok/grok_research_prompt.md` の共有雛形（対話版 grok build と同一）。{{ }} を行データで置換。
- xAI **Responses API**（POST https://api.x.ai/v1/responses）。**web_search ツール**
  （tools=[{"type":"web_search"}]）で web をグラウンディングする。`XAI_API_KEY` 必須。
  （旧 Live Search / chat/completions の search_parameters は 2026-01 に廃止。Responses API + tools へ移行済み。）
  X 個人投稿を避けるため x_search は使わず web_search のみ。Web Search は $5/1K calls 課金。
- 既定モデルは `grok-4.3`（旧 grok-4/grok-3 エイリアスはこれにルーティング）。`XAI_MODEL` で上書き可。
- マスタースイッチ：呼び出し側ルーチンが env `TSE_USE_GROK=1` のときのみ本スクリプトを起動する想定
  （既定 off ＝ 起動しない ＝ 従来の Claude 完結フロー）。

usage:
  # build_day_ranking.py の出力(ranking.json)から上位N社をリサーチ
  python grok_research.py --in ranking.json --out-dir <research_dir> [--top N]
  # 単発（スモークテスト）: コードとセッション日を指定（行データを J-Quants から構築）
  python grok_research.py --code 5803 --date 2026-06-19 --out-dir <research_dir>
  # API を叩かず、埋め込み済みプロンプトだけ確認
  python grok_research.py --code 5803 --date 2026-06-19 --prompt-only
"""
import sys, os, json, re, argparse, datetime
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jquants, tdnet, business_day, market_cap_jquants as mcap

XAI_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = os.environ.get("XAI_MODEL", "grok-4.3")
DEFAULT_SEARCH_MODE = os.environ.get("XAI_SEARCH_MODE", "on")  # on|off（web_search ツールの有無）
PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "grok", "grok_research_prompt.md")

_INVALID = re.compile(r'[\\/:*?"<>|]+')


def load_prompt_template():
    """共有雛形から PROMPT START〜END の本文を取り出す。"""
    with open(PROMPT_PATH, encoding="utf-8") as f:
        txt = f.read()
    # マーカーは**行頭〜行末で独立した行**のものだけを対象にする（コメント内の言及に誤マッチしない）。
    m = re.search(r"^=+ *PROMPT START *=+ *$\s*(.*?)\s*^=+ *PROMPT END *=+ *$",
                  txt, re.S | re.M)
    if not m:
        raise SystemExit(f"PROMPT START/END マーカーが見つからない: {PROMPT_PATH}")
    return m.group(1).strip()


def format_disclosures(discs):
    if not discs:
        return "  （厳密窓内の TDnet 開示なし）"
    lines = []
    for d in discs:
        origin = "前営業日" if d.get("origin") == "prev" else "当日"
        lines.append(f"  - {d.get('date','')} {d.get('time','')}（{origin}）｜"
                     f"{d.get('title','')}｜{d.get('pdf_url','')}")
    return "\n".join(lines)


def fill_prompt(template, row, session_iso, prev_iso):
    repl = {
        "CODE": str(row.get("code", "")),
        "NAME": str(row.get("name", "")),
        "MARKET": str(row.get("market", "") or ""),
        "SESSION_DATE": session_iso,
        "PREV_DATE": prev_iso,
        "PCT": str(row.get("pct", "")),
        "CLOSE": str(row.get("close", "") or ""),
        "TURNOVER_M": str(row.get("turnover_m", "") or ""),
        "MCAP_OKU": str(row.get("mcap_oku", "") or ""),
        "DISCLOSURES": format_disclosures(row.get("disclosures") or []),
    }
    out = template
    for k, v in repl.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def context_for_code(code4, session_iso, prev_iso):
    """ranking.json が無い単発実行用に、1銘柄の行データを J-Quants/TDnet から構築する。"""
    api_key = os.environ.get("JQUANTS_API_KEY")
    if not api_key:
        raise SystemExit("JQUANTS_API_KEY not set（単発実行は行データ構築に J-Quants が必要）")
    c5 = jquants.code5(code4)
    session_d, prev_d = date.fromisoformat(session_iso), date.fromisoformat(prev_iso)
    master = jquants.master_by_date(session_iso)
    bars_now = jquants.bars_by_date(session_iso)
    bars_prev = jquants.bars_by_date(prev_iso)
    m, b, bp = master.get(c5), bars_now.get(c5), bars_prev.get(c5)
    if not b:
        raise SystemExit(f"{code4}: 当日 bars が取得できない（{session_iso}）")
    adjC, adjCp = b.get("AdjC"), (bp or {}).get("AdjC")
    pct = round((adjC / adjCp - 1.0) * 100.0, 2) if (adjC and adjCp) else None
    prices = {c: bb["AdjC"] for c, bb in bars_now.items() if bb.get("AdjC") is not None}
    mcap.prime_price_cache(session_d, prices)
    mc, *_ = mcap.compute_one(api_key, code4, prices, session_d)
    try:
        discs = tdnet.disclosures_window(prev_d, session_d).get(code4, [])
    except Exception as e:
        print(f"# WARN tdnet: {type(e).__name__}: {e}", file=sys.stderr)
        discs = []
    return dict(
        code=code4, name=jquants.normalize_company_name((m or {}).get("CoName")),
        market=(m or {}).get("MktNm"), pct=pct, close=b.get("C"),
        turnover_m=(round((b.get("Va") or 0) / 1e6, 1)),
        mcap_oku=(round(mc) if mc is not None else None), disclosures=discs)


def call_grok(prompt, model=DEFAULT_MODEL, search_mode=DEFAULT_SEARCH_MODE):
    import requests
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY not set")
    payload = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
        "max_output_tokens": 8000,
    }
    if search_mode and search_mode != "off":
        # xAI Web Search ツール（Responses API）。X 個人投稿を避けるため x_search は使わず web_search のみ。
        payload["tools"] = [{"type": "web_search"}]
    r = requests.post(XAI_URL, headers={"Authorization": f"Bearer {key}",
                      "Content-Type": "application/json"}, json=payload, timeout=300)
    r.raise_for_status()
    return _extract_text(r.json())


def _extract_text(data):
    """Responses API のレスポンスから本文テキストを取り出す（SDK 非依存・生 JSON 対応）。"""
    t = data.get("output_text")
    if isinstance(t, str) and t.strip():
        return t
    parts = []
    for item in (data.get("output") or []):
        if item.get("type") == "message":
            for c in (item.get("content") or []):
                if c.get("type") in ("output_text", "text") and c.get("text"):
                    parts.append(c["text"])
    if not parts:
        raise RuntimeError(f"no text in response: keys={list(data.keys())}")
    return "\n".join(parts)


def out_path(out_dir, code4, name, session_iso):
    safe = _INVALID.sub("", (name or "")).strip() or code4
    return os.path.join(out_dir, f"{code4}-{safe}-{session_iso.replace('-', '')}.md")


def has_digest_block(text):
    return "DIGEST_BLOCK" in text and "区分:" in text


def research_row(template, row, session_iso, prev_iso, out_dir, model, search_mode,
                 prompt_only=False):
    prompt = fill_prompt(template, row, session_iso, prev_iso)
    if prompt_only:
        print(prompt)
        return None
    text = call_grok(prompt, model=model, search_mode=search_mode)
    p = out_path(out_dir, row["code"], row.get("name"), session_iso)
    os.makedirs(out_dir, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    ok = has_digest_block(text)
    print(f"# {'OK ' if ok else 'WARN(DIGEST_BLOCK欠落) '}{row['code']} -> {p}", file=sys.stderr)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", help="build_day_ranking.py の出力 JSON")
    ap.add_argument("--code", help="単発リサーチする4桁/英数コード（--in 省略時）")
    ap.add_argument("--date", help="セッション日 YYYY-MM-DD（--code 単発時に必須）")
    ap.add_argument("--prev", help="前営業日 YYYY-MM-DD（省略時は直近営業日）")
    ap.add_argument("--out-dir",
                    default=os.path.expanduser(
                        "~/project-private/tse-ranking-research/research"),
                    help="研究ファイル出力先（既定 project-private/tse-ranking-research/research）")
    ap.add_argument("--top", type=int, default=0, help="ranking.json の上位N社のみ（0=全件）")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--search-mode", default=DEFAULT_SEARCH_MODE, choices=["on", "off"],
                    help="web_search ツールの有無（on=有効/off=無効）")
    ap.add_argument("--prompt-only", action="store_true", help="API を叩かずプロンプトを表示")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    template = load_prompt_template()

    if args.infile:
        with open(args.infile, encoding="utf-8") as f:
            data = json.load(f)
        session_iso, prev_iso = data["session_date"], data["prev_date"]
        rows = data.get("rows", [])
        if args.top and args.top > 0:
            rows = rows[:args.top]
    else:
        if not (args.code and args.date):
            raise SystemExit("--in か、--code と --date の指定が必要")
        session_iso = args.date
        prev_iso = args.prev or business_day.prev_business_day(
            date.fromisoformat(session_iso)).isoformat()
        rows = [context_for_code(args.code, session_iso, prev_iso)]

    written, missing = [], []
    for row in rows:
        try:
            p = research_row(template, row, session_iso, prev_iso, args.out_dir,
                             args.model, args.search_mode, prompt_only=args.prompt_only)
            if p:
                written.append(p)
        except Exception as e:
            missing.append(row.get("code"))
            print(f"# ERROR {row.get('code')}: {type(e).__name__}: {e}", file=sys.stderr)
    if not args.prompt_only:
        print(f"# done: written={len(written)} errors={len(missing)} "
              f"{('failed=' + ','.join(map(str, missing))) if missing else ''}", file=sys.stderr)


if __name__ == "__main__":
    main()
