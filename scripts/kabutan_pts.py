"""株探（かぶたん）個別銘柄ページの最新発行済株式数の取得。

本 skill（東証日中ランキング）では **`kabutan_shares()` のみ使用**する（† クロスチェック用）。
PTS 気配ランキングの取得関数（fetch_gainers/parse_html 等）も origin の互換のため同梱するが、
日中版では用いない（価格・売買代金・上昇率は J-Quants 由来で完結する）。

origin: pts-ranking-digest/scripts/kabutan_pts.py。stdlib のみ（urllib）。
"""
import sys, re, json, time, html as _html, urllib.request, urllib.parse

BASE = "https://kabutan.jp/warning/pts_night_price_increase"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_SHARES = re.compile(r'発行済株式数.{0,40}?>([\d,]+)', re.S)
_NEWS_TABLE = re.compile(r'<table class="s_news_list[^"]*">(.*?)</table>', re.S)
_NEWS_TIME = re.compile(r'<time[^>]*datetime="([^"]+)"')
_NEWS_LINK = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_NEWS_CTG = re.compile(r'newslist_ctg[^>]*>(.*?)</div>', re.S)
# 株探ニュースの定型テクニカル指標見出し（均衡表・GC/DC・パラボリック等）はノイズとして除外する
_NEWS_DROP_CTG = {"テク"}


def kabutan_shares(code):
    """株探の個別銘柄ページから最新の発行済株式数（int）を取得。失敗時 None。

    J-Quants の ShOutFY（期末）は期中の増資・自己株消却を反映しないため、
    最新株数との乖離が大きい銘柄に「†」を付すクロスチェック用。
    """
    url = f"https://kabutan.jp/stock/?code={code}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    m = _SHARES.search(html)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def kabutan_news(code, max_items=12):
    """株探 個別銘柄ニュース（材料・特集〔レーティング日報含む〕・開示・5%ルール等）の
    直近見出しと配信時刻を返す。各要素は {datetime, category, title, url}。失敗時 []。

    変動要因リサーチ（手順B item 2/4）の起点データ：これを各行に事前充填しておくと、
    「材料未確認」へ落とす前に株探の材料/レーティング/大量保有見出しを必ず確認できる。
    なお株探ニュースは §4① 拡張 whitelist だが、本関数は**見出しの索引**であり権威ではない。
    採用時は Claude が配信時刻の当日窓整合と3層ソース規律を必ず適用すること。
    best-effort：取得・パース失敗時は [] を返し、パイプラインを止めない（レイアウト変更時は
    従来挙動に degrade）。定型テクニカル指標見出し（category="テク"）はノイズとして除外する。
    """
    url = f"https://kabutan.jp/stock/news?code={code}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode("utf-8", "replace")
    except Exception:
        return []
    try:
        mtbl = _NEWS_TABLE.search(page)
        if not mtbl:
            return []
        out = []
        for tr in re.split(r'<tr[ >]', mtbl.group(1)):
            mt = _NEWS_TIME.search(tr)
            ma = _NEWS_LINK.search(tr)
            if not mt or not ma:
                continue
            mc = _NEWS_CTG.search(tr)
            cat = re.sub(r"<.*?>", "", mc.group(1)).strip() if mc else ""
            if cat in _NEWS_DROP_CTG:
                continue
            href, title = ma.groups()
            title = _html.unescape(re.sub(r"<.*?>", "", title)).strip()
            out.append({
                "datetime": mt.group(1).strip(),
                "category": cat,
                "title": title,
                "url": href if href.startswith("http") else f"https://kabutan.jp{href}",
            })
            if len(out) >= max_items:
                break
        return out
    except Exception:
        return []


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    code = sys.argv[1] if len(sys.argv) > 1 else "7203"
    print(f"{code}: kabutan_shares={kabutan_shares(code)}")
    for it in kabutan_news(code, 8):
        print(f"  {it['datetime']} | {it['category']} | {it['title'][:60]}")
