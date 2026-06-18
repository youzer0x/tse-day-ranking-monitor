"""東証の営業日判定と、東証日中（レギュラー）セッション日付の導出。

東証日中ランキングは「当日 9:00–15:30 に完了したレギュラーセッション」を対象とする。
当日 D の夕方（18:10 JST）に実行し、報告すべきセッション日は D 自身（D が東証営業日のとき）。
休場日に実行された場合は新規セッションが無いため None を返す＝ルーチンはスキップ。

jpholiday があれば祝日を考慮、無ければ土日のみ判定（スキル単体実行向けフォールバック）。
origin: pts-ranking-digest/scripts/business_day.py（tse_session_date_for を追加）。
"""
from datetime import date, timedelta

try:
    import jpholiday
    _HAS_JP = True
except ImportError:
    _HAS_JP = False


def is_business_day(d):
    """東証営業日か（土日・祝日・年末年始 12/31〜1/3 を除外）。"""
    if d.weekday() >= 5:
        return False
    if (d.month, d.day) in [(12, 31), (1, 1), (1, 2), (1, 3)]:
        return False
    if _HAS_JP and jpholiday.is_holiday(d):
        return False
    return True


def prev_business_day(d):
    """d より前の直近営業日。"""
    x = d - timedelta(days=1)
    while not is_business_day(x):
        x -= timedelta(days=1)
    return x


def tse_session_date_for(run_day):
    """当日 run_day の夕方に報告すべき東証日中セッション日（= run_day が営業日ならその日）。

    休場日に実行された場合は新規セッションが無い＝ None を返す（ルーチンはスキップ）。
    """
    return run_day if is_business_day(run_day) else None


if __name__ == "__main__":
    import sys
    today = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    print(f"jpholiday={'on' if _HAS_JP else 'OFF (weekday-only)'}")
    print(f"today={today} business_day={is_business_day(today)}")
    print(f"prev_business_day={prev_business_day(today)}")
    print(f"tse_session_date_for(today)={tse_session_date_for(today)}")
