"""営業日ゲート: 当日 D に生成すべき東証 日中（レギュラー）セッション日を判定して出力する。

  - 当日（D）が東証営業日 → `SESSION=YYYY-MM-DD`（=D）を出力し exit 0。
  - 当日が休場（=新規日中セッション無し） → `SKIP` を出力し exit 0。

ルーチンはこの出力を見て、SKIP のときは生成せず終了する。
PTS 版（前営業日ゲート・朝 06:06）と異なり、当日が営業日かを見る（cron 18:10 JST）。
TZ=Asia/Tokyo を前提（クラウド環境変数で設定）。
"""
import os, sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import business_day

if __name__ == "__main__":
    today = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    s = business_day.tse_session_date_for(today)
    print(f"SESSION={s.isoformat()}" if s else "SKIP")
