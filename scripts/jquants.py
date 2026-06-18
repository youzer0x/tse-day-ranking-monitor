"""J-Quants V2 API クライアント（市場区分・終値・四本値・発行済株式数）。

- 認証: ヘッダ `x-api-key`（環境変数 JQUANTS_API_KEY）。Light プラン以上で当日値が取れる。
- 東証個別株の権威判定: master の ProdCat=="011"（内国株券）かつ Mkt∈{0111,0112,0113}
  （プライム/スタンダード/グロース）。地方単独上場は bars/daily 非収録で自動除外。
- 本 skill（東証日中ランキング）では bars/daily の日通し終値 C・売買代金 Va・調整済み終値 AdjC を使う。
  値上がり率＝当日 AdjC ÷ 前営業日 AdjC（調整済みの連日比で分割・併合をクリーンに処理）。
- 時価総額の算出は market_cap_jquants.py（tdnet-monitor 由来）に委譲する。

origin: pts-ranking-digest/scripts/jquants.py（時価総額関数は本 skill では未使用のため割愛）。stdlib のみ（urllib）。
"""
import os, json, time, urllib.request, urllib.error, urllib.parse

API = "https://api.jquants.com/v2"


def _key():
    k = os.environ.get("JQUANTS_API_KEY")
    if not k:
        raise SystemExit("JQUANTS_API_KEY not set")
    return k


def get(path, params, max_pages=80):
    """V2 を呼び pagination_key を連結して data 配列を返す（429 リトライ込み）。"""
    key = _key()
    out, pk = [], None
    for _ in range(max_pages):
        p = dict(params)
        if pk:
            p["pagination_key"] = pk
        url = f"{API}{path}?" + urllib.parse.urlencode(p)
        req = urllib.request.Request(url, headers={"x-api-key": key})
        body = None
        for attempt in range(9):
            try:
                with urllib.request.urlopen(req, timeout=40) as r:
                    body = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(min(1.5 * (attempt + 1), 12)); continue
                raise
            except Exception:
                if attempt == 8:
                    raise
                time.sleep(1.5 ** attempt)
        if body is None:
            raise RuntimeError(f"empty/429-exhausted: {path} {params}")
        out.extend(body.get("data", []))
        pk = body.get("pagination_key")
        if not pk:
            break
    return out


def code5(code4):
    """株探/TDnet の4桁（または英数）コードを J-Quants の5桁へ。9760→97600, 285A→285A0。"""
    return code4 + "0" if len(code4) == 4 else code4


def code4(code5):
    """J-Quants の5桁コードを4桁（または末尾英字）へ。97600→9760, 285A0→285A。"""
    c = str(code5)
    if len(c) == 5 and c.endswith("0") and c[:-1].isdigit():
        return c[:-1]
    return c


def normalize_company_name(name):
    """表示用に社名を整える。

    - J-Quants の CoName はフルネームで返る（例：村田製作所／ソフトバンクグループ）が、
      英数字・記号は**全角**のことがある（例：ＡＧＣ／ＫＤＤＩ／日本Ｍ＆Ａセンター…）。
    - 仕様：英数記号は**半角**に統一し、万一含まれる「株式会社」表記は除去する
      （CoName は通常含まないが安全側）。日本語（かな・カナ・漢字）はそのまま。
    """
    if not name:
        return name
    out = []
    for ch in name:
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:      # 全角の英数字・記号 → 半角（! 〜 ~）
            out.append(chr(o - 0xFEE0))
        elif o == 0x3000:               # 全角スペース → 半角スペース
            out.append(" ")
        else:
            out.append(ch)
    s = "".join(out)
    for token in ("株式会社", "（株）", "(株)", "㈱"):
        s = s.replace(token, "")
    return s.strip()


def master_by_date(target_iso):
    return {r["Code"]: r for r in get("/equities/master", {"date": target_iso})}


def bars_by_date(target_iso):
    return {r["Code"]: r for r in get("/equities/bars/daily", {"date": target_iso})}


def is_tse_individual(m):
    """master 行が東証本則の内国株券か。"""
    return bool(m) and m.get("ProdCat") == "011" and m.get("Mkt") in ("0111", "0112", "0113")
