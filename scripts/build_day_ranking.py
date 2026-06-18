"""Stage 1（決定的）: 東証 日中（レギュラー）値上がり率ランキングの素データを組み立てて JSON 出力する。

  J-Quants V2（全銘柄の当日 bars/daily）だけでスクリーニングが完結する：
    - 値上がり率 ＝ 当日 AdjC ÷ 前営業日 AdjC − 1（調整済み終値の連日比＝分割/併合クリーン）
    - 売買代金 ＝ Va（日通し取引代金・実値）
    - 時価総額 ＝ market_cap_jquants（AdjC×ShOutFY×分割補正/1e8、新規上場は Yahoo）
  TDnet（前回引け→当日引け直前の開示）と株探（† 最新株数）を結合する。
  **変動要因（[開示]/[報道]/[テーマ]）は含めない**（後段で Claude が裏取りして埋める）。

フィルタ（既定）:
  - 東証個別株のみ（J-Quants ProdCat=011 かつ Mkt∈{0111,0112,0113}）。ETF/REIT/地方上場は除外。
  - 値上がり率 ≥ min_pct（既定 +5%）かつ 売買代金 ≥ min_turnover（既定 ¥10,000,000）。
  - 時価総額 ≥ min_mcap 億円（既定 100）。
  - 期中の増資・自己株で J-Quants 株数と株探最新株数が >1% 乖離する銘柄は mcap_flag="†"。
  - 上記を満たす銘柄が max_rank（既定 50）社を超える場合は、値上がり率の高い順に上位 max_rank 社のみをランキング対象とする
    （--max-rank 0 で上限なし）。該当総数は counts.qualifying、掲載数は counts.ranked に記録する。

usage:
  python build_day_ranking.py [--date YYYY-MM-DD] [--prev YYYY-MM-DD] [--out ranking.json]
  （--date 省略時は当日が営業日ならその日、--prev 省略時は直近営業日）
"""
import sys, os, json, time, argparse, datetime
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jquants, kabutan_pts, tdnet, business_day, market_cap_jquants as mcap


def build(session_iso, prev_iso, min_pct=5.0, min_turnover=10_000_000, min_mcap=100,
          max_rank=50, do_kabutan_shares=True, verbose=True):
    def log(*a):
        if verbose:
            print(*a, file=sys.stderr)

    api_key = os.environ.get("JQUANTS_API_KEY")
    if not api_key:
        raise SystemExit("JQUANTS_API_KEY not set")
    session_d = date.fromisoformat(session_iso)
    prev_d = date.fromisoformat(prev_iso)

    # 1) J-Quants 一括（master / bars 当日・前営業日）
    log(f"# J-Quants master/bars: session={session_iso} prev={prev_iso} ...")
    master = jquants.master_by_date(session_iso)
    bars_now = jquants.bars_by_date(session_iso)
    bars_prev = jquants.bars_by_date(prev_iso)
    log(f"# master={len(master)} bars_now={len(bars_now)} bars_prev={len(bars_prev)}")

    # 当日 AdjC を時価総額モジュールのキャッシュに流し込む（bars/daily の再取得を避ける）
    prices = {c: b["AdjC"] for c, b in bars_now.items() if b.get("AdjC") is not None}
    mcap.prime_price_cache(session_d, prices)

    # 2) スクリーニング（J-Quants のみ・全銘柄ループ）
    cand, excluded = [], []
    for c5, b in bars_now.items():
        m = master.get(c5)
        if not jquants.is_tse_individual(m):
            excluded.append({"code": jquants.code4(c5), "reason": "not_tse_individual"})
            continue
        adjC = b.get("AdjC")
        bp = bars_prev.get(c5)
        adjCp = bp.get("AdjC") if bp else None
        if not adjC or not adjCp:
            excluded.append({"code": jquants.code4(c5), "reason": "no_prev_close"})
            continue
        pct = (adjC / adjCp - 1.0) * 100.0
        if pct < min_pct:
            continue
        cand.append((c5, b, m, pct))
    # 値上がり率の高い順。同率は売買代金の大きい順（上限 max_rank の境界を決定的にする）
    cand.sort(key=lambda x: (-x[3], -(x[1].get("Va") or 0)))
    log(f"# candidates(>= +{min_pct}%, TSE individual, prev-close 有)={len(cand)}")

    # 3) 売買代金 → 時価総額 の順でフィルタ（候補のみ・少数なので per-code 呼び出しで十分）
    qualifying, dropped_turnover, dropped_mcap = [], [], []
    for c5, b, m, pct in cand:
        c4 = jquants.code4(c5)
        name = jquants.normalize_company_name(m.get("CoName"))
        va = b.get("Va")
        if va is None or va < min_turnover:
            dropped_turnover.append({"code": c4, "name": name, "pct": round(pct, 2),
                                     "turnover_m": (round(va / 1e6, 1) if va else 0.0)})
            continue
        mc, shoutfy, period_end, corr, source = mcap.compute_one(api_key, c4, prices, session_d)
        time.sleep(0.1)
        if mc is None or mc < min_mcap:
            dropped_mcap.append({"code": c4, "name": name, "pct": round(pct, 2),
                                 "turnover_m": round(va / 1e6, 1),
                                 "mcap_oku": (round(mc) if mc is not None else None),
                                 "mcap_source": source})
            continue
        qualifying.append(dict(
            code=c4, name=name, market=m.get("MktNm"),
            mcap_oku=round(mc), mcap_oku_exact=mc, mcap_flag="", mcap_source=source,
            pct=round(pct, 2), close=b.get("C"), adj_close=b.get("AdjC"),
            prev_adj_close=(bars_prev.get(c5) or {}).get("AdjC"),
            turnover_yen=round(va), turnover_m=round(va / 1e6, 1),
            shoutfy_jq=shoutfy, period_end=(period_end.isoformat() if period_end else None),
            corr=round(corr, 6), disclosures=[], factor="", factor_kind=""))

    # 上限：該当総数が max_rank を超えたら値上がり率上位 max_rank 社のみをランキング対象にする。
    # qualifying は cand のソート順（pct 降順）を継承しているので先頭から切り出せばよい。
    qualified_total = len(qualifying)
    capped = bool(max_rank and max_rank > 0 and qualified_total > max_rank)
    if capped:
        qualifying = qualifying[:max_rank]
    for i, row in enumerate(qualifying, 1):
        row["rank"] = i
    log(f"# qualifying(該当)={qualified_total}  ranked(掲載)={len(qualifying)}"
        f"{f' [上限{max_rank}社]' if capped else ''}  dropped_turnover={len(dropped_turnover)}  "
        f"dropped_mcap={len(dropped_mcap)}  excluded={len(excluded)}")

    # 4) TDnet 変動要因候補（前営業日>=15:30 ∪ 当日<15:30 の厳密窓・自前取得）
    log(f"# TDnet window: {prev_iso}>=15:30 ∪ {session_iso}<15:30 ...")
    try:
        by = tdnet.disclosures_window(prev_d, session_d)
    except Exception as e:
        log(f"# WARN tdnet: {type(e).__name__}: {e}")
        by = {}
    for row in qualifying:
        row["disclosures"] = by.get(row["code"], [])

    # 5) 株探 最新発行済株式数とのクロスチェック（† 注記。source=='jquants' のみ）
    if do_kabutan_shares:
        log(f"# kabutan shares cross-check for {len(qualifying)} names ...")
        for row in qualifying:
            if row["mcap_source"] != "jquants" or not row["shoutfy_jq"]:
                continue
            shk = kabutan_pts.kabutan_shares(row["code"])
            time.sleep(0.2)
            base = (row["shoutfy_jq"] or 0) * (row["corr"] or 1.0)
            if shk and base > 0 and abs(shk - base) / base > 0.01:
                row["mcap_flag"] = "†"
                row["shares_kabutan"] = shk
                if row["close"]:
                    row["mcap_kabutan_oku"] = round(row["close"] * shk / 1e8)

    return {
        "session_date": session_iso,
        "prev_date": prev_iso,
        "session_window": f"{session_iso} 09:00–15:30 JST（前場9:00-11:30／後場12:30-15:30）",
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M JST"),
        "criteria": {"min_pct": min_pct, "min_turnover_yen": min_turnover, "min_mcap_oku": min_mcap,
                     "max_rank": (max_rank if (max_rank and max_rank > 0) else None)},
        "capped": capped,
        "counts": {"qualifying": qualified_total, "ranked": len(qualifying),
                   "dropped_turnover": len(dropped_turnover),
                   "dropped_mcap": len(dropped_mcap), "excluded": len(excluded)},
        "rows": qualifying,
        "dropped_turnover": sorted(dropped_turnover, key=lambda x: -x["pct"]),
        "dropped_mcap": sorted(dropped_mcap, key=lambda x: -x["pct"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="セッション日 YYYY-MM-DD（省略時は当日が営業日ならその日）")
    ap.add_argument("--prev", help="前営業日 YYYY-MM-DD（省略時は直近営業日）")
    ap.add_argument("--min-pct", type=float, default=5.0)
    ap.add_argument("--min-turnover", type=float, default=10_000_000)
    ap.add_argument("--min-mcap", type=float, default=100)
    ap.add_argument("--max-rank", type=int, default=50,
                    help="掲載上限（値上がり率上位N社。0で上限なし。既定50）")
    ap.add_argument("--out", help="JSON 出力先パス（省略時は stdout）")
    ap.add_argument("--no-kabutan-shares", action="store_true")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    if args.date:
        session_iso = args.date
    else:
        sd = business_day.tse_session_date_for(date.today())
        if sd is None:
            print("# 本日は東証休場（新規セッション無し）。スキップ。", file=sys.stderr)
            return
        session_iso = sd.isoformat()
    prev_iso = args.prev or business_day.prev_business_day(date.fromisoformat(session_iso)).isoformat()

    data = build(session_iso, prev_iso, min_pct=args.min_pct, min_turnover=args.min_turnover,
                 min_mcap=args.min_mcap, max_rank=args.max_rank,
                 do_kabutan_shares=not args.no_kabutan_shares)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        d = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(d, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        c = data["counts"]
        print(f"# wrote {args.out} (該当{c['qualifying']}社 / 掲載{c['ranked']}社"
              f"{' [上限]' if data.get('capped') else ''})", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
