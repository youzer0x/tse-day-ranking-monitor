"""東証 日中ランキングの publish（GitHub Pages JSON/SPA ＋ Gmail メール本文の生成・送信）。

入力：build_day_ranking.py の出力 JSON に、Claude が各 row の factor/factor_kind を埋めたもの。
出力：
  - docs/data/<session_date>.json（**フルデータ**＝rows に disclosures/pdf_url・counts・capped を含む）
  - docs/data/manifest.json／30日より古い JSON 削除
  - docs/index.html（PTS と同一トンマナの日付選択式 Pages・html_generator が生成）
  - メール HTML（--send 指定で Gmail API〔HTTPS〕送信＝gmail_sender.send_gmail）

トンマナ・書式・カラーは PTS 版（pts-ranking-monitor）と同一（html_generator.py 参照）。
メール送信は PTS と同じ Gmail API 方式（クラウドは SMTP 不可）。本体は stdlib のみ。

2フェーズ運用（メールのリンク先が「前営業日」止まりになるラグ対策）：
  1) 生成（build）：`python publish.py --in ranking.json --docs docs --pages-url URL`
      … docs/ 一式を生成するだけ（メールは送らない）。
  2) この後に git push（GitHub Pages＝main/docs を反映）。
  3) 通知（notify）：`python publish.py --in ranking.json --docs docs --pages-url URL --notify`
     … Pages が新セッションを実際に配信し始めるまで待ってから Gmail 送信する。
  ※ `--send`（即時送信）は push 前送信になりラグの原因になるため**レガシー**。ルーチンでは使わない。

usage:
  python publish.py --in ranking.json --docs docs --pages-url URL            # 生成のみ
  python publish.py --in ranking.json --docs docs --pages-url URL --notify   # push 後にライブ確認→送信
  python publish.py --in ranking.json --docs docs --pages-url URL --send     # レガシー（即時送信・非推奨）
"""
import os, sys, json, glob, argparse, time
import urllib.request, urllib.error
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


def wait_until_live(pages_url, session, timeout=300, interval=10):
    """push 後、GitHub Pages が新セッションを配信し始めるまで待つ（メールのリンク先ラグ対策）。

    Pages の `data/manifest.json` をキャッシュ無効化クエリ（?cb=<epoch>）＋no-cache ヘッダで
    取得し、`dates[0]==session` になったら True を返す（＝SPA が当日分を最新として表示できる状態）。
    pages_url 未設定（"./"）はスキップして False。timeout 内に確認できなければ警告を出して False を
    返すが、**送信は呼び出し側で続行**する（遅れてでも通知する方がよい）。本体は stdlib のみ。
    """
    if not pages_url or pages_url in ("./", "."):
        print("  (skip live-check: pages-url 未設定)")
        return False
    base = pages_url.rstrip("/")
    deadline = time.monotonic() + timeout
    n = 0
    while time.monotonic() < deadline:
        n += 1
        url = f"{base}/data/manifest.json?cb={int(time.time())}"
        try:
            req = urllib.request.Request(url, headers={
                "Cache-Control": "no-cache", "Pragma": "no-cache",
                "User-Agent": "tse-ranking-monitor-livecheck"})
            with urllib.request.urlopen(req, timeout=15) as r:
                dates = json.loads(r.read()).get("dates", [])
            if dates and dates[0] == session:
                print(f"  live confirmed: Pages newest={session} (checks={n})")
                return True
            print(f"  not live yet (newest={dates[0] if dates else None}); wait {interval}s")
        except urllib.error.HTTPError as e:
            print(f"  live-check HTTP {e.code}; wait {interval}s")
        except Exception as e:
            print(f"  live-check {type(e).__name__}: {e}; wait {interval}s")
        time.sleep(interval)
    print(f"  WARN: Pages not confirmed live within {timeout}s; sending anyway")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="build_day_ranking.py の出力 JSON（要因記入済み）")
    ap.add_argument("--docs", default="docs", help="GitHub Pages の docs ディレクトリ")
    ap.add_argument("--pages-url", default=os.environ.get("PAGES_URL", "./"))
    ap.add_argument("--notify", action="store_true",
                    help="push 後に Pages のライブ反映を待ってから Gmail 送信（生成はしない）。ルーチン推奨")
    ap.add_argument("--send", action="store_true",
                    help="レガシー：生成と同時に即 Gmail 送信（push 前送信になりラグの原因。非推奨）")
    ap.add_argument("--live-timeout", type=int, default=300, help="--notify のライブ確認の最大待機秒（既定300）")
    ap.add_argument("--live-interval", type=int, default=10, help="--notify のライブ確認の間隔秒（既定10）")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with open(args.inp, encoding="utf-8") as f:
        data = json.load(f)
    if "session_date" not in data:
        sys.exit("invalid ranking json: missing session_date")

    if args.notify:
        # 通知フェーズ：生成・コミットは済んでいる前提。push 後の Pages 反映を待って送信する。
        print(f"Notify {data['session_date']} ({len(data.get('rows', []))} rows): wait for Pages then send ...")
        wait_until_live(args.pages_url, data["session_date"],
                        timeout=args.live_timeout, interval=args.live_interval)
        email_html = html_generator.generate_email_html(data, args.pages_url)
        send_email(data, email_html)
        return

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
        # レガシー経路（push 前送信＝リンク先が未反映になりやすい）。ルーチンは --notify を使う。
        print("  WARN: --send は push 前送信のためリンク先ラグの原因。ルーチンでは push 後に --notify を使う。")
        send_email(data, email_html)


if __name__ == "__main__":
    main()
