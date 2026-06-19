"""東証 日中ランキングの publish（GitHub Pages JSON/SPA ＋ Gmail メール本文の生成・送信）。

入力：build_day_ranking.py の出力 JSON に、Claude が各 row の factor/factor_kind を埋めたもの。
出力：
  - docs/data/<session_date>.json（**フルデータ**＝rows に disclosures/pdf_url・counts・capped を含む）
  - docs/data/manifest.json／30日より古い JSON 削除
  - docs/index.html（PTS と同一トンマナの日付選択式 Pages・html_generator が生成）
  - メール HTML（--send 指定で Gmail API〔HTTPS〕送信＝gmail_sender.send_gmail）

トンマナ・書式・カラーは PTS 版（pts-ranking-monitor）と同一（html_generator.py 参照）。
メール送信は PTS と同じ Gmail API 方式（クラウドは SMTP 不可）。本体は stdlib のみ。

usage:
  python publish.py --in ranking.json --docs ../docs [--pages-url URL] [--send]
"""
import os, sys, json, glob, argparse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import html_generator


def save_data(data, docs_dir):
    """フルデータ（rows に disclosures/pdf_url、counts/capped 等）を docs/data/<date>.json に保存。"""
    data_dir = os.path.join(docs_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    sd = data["session_date"]
    path = os.path.join(data_dir, f"{sd}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  daily json: {path} ({len(data.get('rows', []))} rows)")
    return path


def cleanup_old(docs_dir, keep_days=30):
    data_dir = os.path.join(docs_dir, "data")
    cutoff = date.today() - timedelta(days=keep_days)
    for fn in glob.glob(os.path.join(data_dir, "*.json")):
        base = os.path.basename(fn)
        if base == "manifest.json":
            continue
        try:
            if date.fromisoformat(base[:-5]) < cutoff:
                os.remove(fn)
        except ValueError:
            pass


def update_manifest(docs_dir):
    data_dir = os.path.join(docs_dir, "data")
    dates = []
    for fn in sorted(glob.glob(os.path.join(data_dir, "*.json")), reverse=True):
        base = os.path.basename(fn)
        if base == "manifest.json":
            continue
        try:
            dates.append(date.fromisoformat(base[:-5]).isoformat())
        except ValueError:
            pass
    with open(os.path.join(data_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f, ensure_ascii=False)
    return dates


def write_index(docs_dir):
    os.makedirs(docs_dir, exist_ok=True)
    path = os.path.join(docs_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_generator.generate_pages_html())
    print(f"  pages html: {path}")


def send_email(data, html_body):
    """Gmail API（HTTPS）でメール送信する（PTS 版と同方式）。

    クラウドルーチン環境は SMTP(465) を通さないため、OAuth2 リフレッシュトークン
    （GMAIL_CLIENT_ID/GMAIL_CLIENT_SECRET/GMAIL_REFRESH_TOKEN）で Gmail API を叩く。
    認証情報が無ければ送信をスキップする。件名は capped 対応（該当M社・上位N社）。
    """
    if not (os.environ.get("GMAIL_CLIENT_ID") and os.environ.get("GMAIL_CLIENT_SECRET")
            and os.environ.get("GMAIL_REFRESH_TOKEN") and os.environ.get("GMAIL_ADDRESS")):
        print("  (skip send: GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN / GMAIL_ADDRESS 未設定)")
        return False
    import gmail_sender
    rows = data.get("rows", [])
    counts = data.get("counts", {}) or {}
    return gmail_sender.send_gmail(
        html_body, data["session_date"], len(rows),
        total=counts.get("qualifying", len(rows)), capped=bool(data.get("capped")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="build_day_ranking.py の出力 JSON（要因記入済み）")
    ap.add_argument("--docs", default="docs", help="GitHub Pages の docs ディレクトリ")
    ap.add_argument("--pages-url", default=os.environ.get("PAGES_URL", "./"))
    ap.add_argument("--send", action="store_true", help="Gmail 送信（環境変数が揃っていれば）")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with open(args.inp, encoding="utf-8") as f:
        data = json.load(f)
    if "session_date" not in data:
        sys.exit("invalid ranking json: missing session_date")
    print(f"Publishing {data['session_date']} ({len(data.get('rows', []))} rows) ...")

    save_data(data, args.docs)
    cleanup_old(args.docs, keep_days=30)
    update_manifest(args.docs)
    write_index(args.docs)

    email_html = html_generator.generate_email_html(data, args.pages_url)
    email_path = os.path.join(args.docs, "data", f"{data['session_date']}_email.html")
    with open(email_path, "w", encoding="utf-8") as f:
        f.write(email_html)
    print(f"  email html: {email_path}")

    if args.send:
        send_email(data, email_html)


if __name__ == "__main__":
    main()
