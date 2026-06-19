"""GitHub Pages 用 HTML と Gmail 本文 HTML の生成（東証 値上がり率ランキング）。

トンマナ・書式・カラーは PTS 版（pts-ranking-monitor/scripts/html_generator.py）と**同一**。
TSE 固有のデータ（列＝PTS気配なし・終値(円)／抽出条件＝≥+5%・¥10M・100億・上位50社／出典）
のみ差し替えている。配色・フォント・ヘッダー・バッジ・株探リンク・[開示PDF]・薄商い折りたたみ・
モバイルのカード化は PTS と一致。

公開データ（docs/data/YYYY-MM-DD.json）は build_day_ranking.py の出力に各行の変動要因（factor /
factor_kind）を埋めたもの（rows に disclosures/pdf_url・counts・capped を含むフルデータ）。
時価総額は要件により **常に億円の整数（カンマ区切り、1兆円以上も億円表示）** とする。
"""


def fmt_mcap(oku, flag=""):
    if oku is None:
        return "—"
    return f"{oku:,}{flag or ''}"


def fmt_pct(pct):
    if pct is None:
        return "—"
    return f"+{pct:.2f}%"


def _count_label(data):
    """capped のとき『該当 M 社（上位 N 社を掲載）』、それ以外は『該当 N 社』。"""
    rows = data.get("rows", [])
    n = len(rows)
    total = (data.get("counts", {}) or {}).get("qualifying", n)
    if data.get("capped"):
        return f"該当 {total} 社（上位 {n} 社を掲載）"
    return f"該当 {n} 社"


def _criteria_text(data):
    c = data.get("criteria", {}) or {}
    pct = c.get("min_pct", 5)
    tm = (c.get("min_turnover_yen", 10_000_000)) / 1e6
    mc = c.get("min_mcap_oku", 100)
    cap = c.get("max_rank")
    s = (f"値上がり率≥+{pct:g}% かつ 売買代金≥{tm:g}百万円／東証個別・時価総額≥{mc:g}億円")
    if cap:
        s += f"・上昇率上位{cap:g}社"
    return s


# ----------------------------------------------------------------------------- email

def _kind_badge(kind):
    k = (kind or "").strip("[]")
    color = {"開示": "#1b7f3b", "報道": "#1a6fd0", "テーマ": "#8a6d00"}.get(k, "#777")
    return (f'<span style="display:inline-block;font-size:10px;color:#fff;background:{color};'
            f'border-radius:3px;padding:1px 5px;margin-right:4px;white-space:nowrap;">{k or "—"}</span>') if k else ""


def generate_email_html(data, pages_url, max_items=25):
    rows = data.get("rows", [])
    display = rows[:max_items] if max_items else rows
    win = data.get("session_window", "")
    date_str = data.get("session_date", "")
    count_label = _count_label(data)
    trs = []
    for r in display:
        factor = (r.get("factor") or "（材料未確認）").strip()
        badge = _kind_badge(r.get("factor_kind"))
        trs.append(f"""<tr>
          <td style="padding:7px 8px;border-bottom:1px solid #eee;text-align:right;font-family:Arial,sans-serif;">{r.get('rank','')}</td>
          <td style="padding:7px 8px;border-bottom:1px solid #eee;font-family:Arial,sans-serif;white-space:nowrap;">{r.get('code','')}</td>
          <td style="padding:7px 8px;border-bottom:1px solid #eee;white-space:nowrap;">{r.get('name','')}</td>
          <td style="padding:7px 8px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap;font-family:Arial,sans-serif;">{fmt_mcap(r.get('mcap_oku'), r.get('mcap_flag'))}</td>
          <td style="padding:7px 8px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap;font-family:Arial,sans-serif;color:#c0392b;font-weight:600;">{fmt_pct(r.get('pct'))}</td>
          <td class="col-factor" style="padding:7px 8px;border-bottom:1px solid #eee;font-size:12px;line-height:1.5;">{badge}{factor}</td>
        </tr>""")
    table_rows = "\n".join(trs)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>@media screen and (max-width:600px){{ .col-factor{{display:none!important;}} }}</style>
</head>
<body style="font-family:'Helvetica Neue',Arial,'Hiragino Sans',sans-serif;color:#333;margin:0;padding:0;background:#f5f5f5;">
  <div style="max-width:980px;margin:20px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
    <div style="background:#11243f;color:#fff;padding:18px 22px;">
      <h1 style="margin:0;font-size:19px;font-weight:600;">📈 東証 値上がり率ランキング</h1>
      <p style="margin:6px 0 0;font-size:13px;opacity:0.9;">{date_str}｜{count_label}｜{win}</p>
      <p style="margin:4px 0 0;font-size:11px;opacity:0.7;">条件：{_criteria_text(data)}</p>
    </div>
    <div style="padding:16px 20px;">
      <div style="text-align:center;margin:0 0 14px;">
        <a href="{pages_url}" target="_blank" style="display:inline-block;background:#11243f;color:#fff;padding:9px 26px;border-radius:6px;text-decoration:none;font-size:14px;">全件・詳細を表示 →</a>
      </div>
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;font-size:13px;">
        <thead><tr style="background:#f6f8fa;">
          <th style="padding:8px;text-align:right;border-bottom:2px solid #11243f;">#</th>
          <th style="padding:8px;text-align:left;border-bottom:2px solid #11243f;white-space:nowrap;">コード</th>
          <th style="padding:8px;text-align:left;border-bottom:2px solid #11243f;">銘柄</th>
          <th style="padding:8px;text-align:right;border-bottom:2px solid #11243f;white-space:nowrap;">時価総額<br>(億円)</th>
          <th style="padding:8px;text-align:right;border-bottom:2px solid #11243f;white-space:nowrap;">上昇率</th>
          <th class="col-factor" style="padding:8px;text-align:left;border-bottom:2px solid #11243f;width:40%;">変動要因</th>
        </tr></thead>
        <tbody>
{table_rows}
        </tbody>
      </table>
      <p style="margin:14px 0 0;font-size:11px;color:#888;">価格・売買代金・終値・市場区分・時価総額＝J-Quants V2（新規上場の時価総額は Yahoo Finance JP）／開示＝TDnet。† は増資・自己株で株探最新株数と乖離。本情報は参考であり投資助言ではない。</p>
    </div>
    <div style="background:#f6f8fa;padding:11px 20px;font-size:11px;color:#999;text-align:center;">東証 値上がりランキング・モニター｜Claude 定期実行（自動送信）</div>
  </div>
</body></html>"""


# ----------------------------------------------------------------------------- pages

def generate_pages_html():
    return r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>東証 値上がり率ランキング</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#eef1f5;--card:#fff;--primary:#11243f;--accent:#c0392b;--text:#222;--sub:#6b7785;--border:#e2e6ea;--hover:#f5f8ff;}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Noto Sans JP',sans-serif;background:var(--bg);color:var(--text);line-height:1.6;}
.header{background:linear-gradient(135deg,#11243f,#24507f);color:#fff;padding:24px 28px 18px;}
.header-inner{max-width:1280px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;}
.header h1{font-size:21px;font-weight:700;}
.date-selector{display:flex;align-items:center;gap:8px;}
.date-selector label{font-size:13px;opacity:.9;}
.date-selector select{padding:7px 30px 7px 12px;font-size:14px;font-family:Arial,sans-serif;border:1px solid rgba(255,255,255,.3);border-radius:6px;background:rgba(255,255,255,.15);color:#fff;cursor:pointer;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' stroke='white' stroke-width='1.5' fill='none'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;}
.date-selector select option{background:#11243f;color:#fff;}
.summary{max-width:1280px;margin:16px auto 0;padding:0 16px;display:flex;gap:10px;flex-wrap:wrap;}
.chip{background:var(--card);border-radius:8px;padding:8px 14px;font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.06);}
.chip .num{font-family:Arial,sans-serif;font-weight:700;font-size:16px;color:var(--primary);}
.container{max-width:1280px;margin:14px auto 28px;padding:0 16px;}
.card{background:var(--card);border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.06);overflow:hidden;}
.note{padding:10px 8px 12px;font-size:12px;color:var(--sub);}
table{width:100%;border-collapse:collapse;font-size:13px;}
thead th{padding:9px 10px;text-align:left;background:#f6f8fc;border-bottom:2px solid var(--primary);font-size:12px;color:var(--sub);white-space:nowrap;position:sticky;top:0;}
thead th.r{text-align:right;}
tbody td{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:top;}
tbody tr:hover td{background:var(--hover);}
.rank{font-family:Arial,sans-serif;text-align:right;color:var(--sub);}
.code{font-family:Arial,sans-serif;white-space:nowrap;}
.code a{color:var(--primary);text-decoration:none;}
.code a:hover{text-decoration:underline;}
.name{white-space:nowrap;font-weight:500;}
.mkt{white-space:nowrap;}
.num{font-family:Arial,sans-serif;text-align:right;white-space:nowrap;}
.pct{font-family:Arial,sans-serif;text-align:right;white-space:nowrap;color:var(--accent);font-weight:600;}
.factor{font-size:12.5px;line-height:1.55;min-width:240px;}
.kind{display:inline-block;font-size:10px;color:#fff;border-radius:3px;padding:1px 6px;margin-right:5px;white-space:nowrap;}
.kind.k開示{background:#1b7f3b;} .kind.k報道{background:#1a6fd0;} .kind.kテーマ{background:#8a6d00;}
.factor a{color:#1a6fd0;text-decoration:none;} .factor a:hover{text-decoration:underline;}
.dropped{margin-top:18px;}
.dropped summary{cursor:pointer;font-size:13px;color:var(--sub);padding:8px 4px;}
.footer{text-align:center;padding:18px;font-size:11px;color:var(--sub);}
.loading,.empty{text-align:center;padding:50px 20px;color:var(--sub);}
@media(max-width:820px){
 .header{padding:18px 14px;} .header-inner{flex-direction:column;align-items:flex-start;}
 .header h1{font-size:18px;}
 table,thead,tbody,tr,td{display:block;width:100%;}
 thead{display:none;}
 .card{background:transparent;box-shadow:none;border-radius:0;overflow:visible;}
 tbody tr{background:var(--card);border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.06);margin:0 0 12px;padding:12px 14px;border:none;}
 tbody td{padding:0;border:none;text-align:left!important;}
 #tableArea td.rank{display:block;font-size:13px;color:var(--sub);font-family:Arial,sans-serif;}
 #tableArea td.rank::before{content:'#';}
 #tableArea td.code{display:none;}
 #tableArea td.name{display:block;font-size:15px;font-weight:700;}
 #tableArea td.name::after{content:'（'attr(data-code)'）';font-weight:700;}
 #tableArea td.mkt{display:block;font-size:12px;color:var(--sub);}
 td.pct,td.num{display:inline-block;width:49%;font-size:14px;margin-top:8px;text-align:left;vertical-align:top;}
 td.pct::before,td.num::before{content:attr(data-label)'\00a0';display:block;color:var(--sub);font-size:11px;font-weight:400;font-family:'Noto Sans JP';}
 td.factor{min-width:0;margin-top:10px;padding-top:9px;border-top:1px solid var(--border)!important;}
}
</style></head>
<body>
<div class="header"><div class="header-inner">
  <div><h1>📈 東証 値上がり率ランキング</h1></div>
  <div class="date-selector"><label for="dateSelect">セッション日:</label>
  <select id="dateSelect" onchange="loadDate(this.value)"><option>読み込み中...</option></select></div>
</div></div>
<div class="summary" id="summary"></div>
<div class="container">
  <div class="note" id="note"></div>
  <div class="card">
  <div id="tableArea"><div class="loading">データを読み込んでいます…</div></div>
  </div>
<div class="container" style="margin-top:0;"><div id="droppedArea"></div></div>
</div>
<div class="footer">東証 値上がりランキング・モニター｜Claude 定期実行で自動生成｜価格・売買代金・終値・時価総額＝J-Quants V2／開示＝TDnet｜本情報は参考であり投資助言ではない</div>
<script>
let data=null;
function fmtMcap(o,f){if(o==null)return '—';return o.toLocaleString('ja-JP')+(f||'');}
function fmtPct(p){return p==null?'—':'+'+Number(p).toFixed(2)+'%';}
function fmtNum(x){return x==null?'—':Number(x).toLocaleString('ja-JP');}
function fmtTurnover(t){return t==null?'—':Math.round(Number(t)).toLocaleString('ja-JP');}
function fmtTurnoverOku(r){let v=(r.turnover_yen!=null)?Number(r.turnover_yen)/1e8:(r.turnover_m!=null?Number(r.turnover_m)/100:null);return v==null?'—':Math.round(v).toLocaleString('ja-JP');}
function fmtMarket(m){m=m||'';if(m.indexOf('プライム')>=0)return 'Prime';if(m.indexOf('スタンダード')>=0)return 'Standard';if(m.indexOf('グロース')>=0)return 'Growth';return m;}
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
function kindBadge(k){k=(k||'').replace(/[\[\]]/g,'');if(!k)return '';return '<span class="kind k'+k+'">'+k+'</span>';}
async function init(){
  try{
    const m=await (await fetch('data/manifest.json?'+Date.now())).json();
    const sel=document.getElementById('dateSelect');sel.innerHTML='';
    if(!m.dates||!m.dates.length){sel.innerHTML='<option>データなし</option>';document.getElementById('tableArea').innerHTML='<div class="empty">まだデータがありません。</div>';return;}
    m.dates.forEach((d,i)=>{const o=document.createElement('option');o.value=d;const dt=new Date(d+'T00:00:00');o.textContent=d+' ('+['日','月','火','水','木','金','土'][dt.getDay()]+')';if(i===0)o.selected=true;sel.appendChild(o);});
    loadDate(m.dates[0]);
  }catch(e){document.getElementById('tableArea').innerHTML='<div class="empty">データの読み込みに失敗しました。</div>';}
}
async function loadDate(d){
  if(!d)return;
  document.getElementById('tableArea').innerHTML='<div class="loading">読み込み中…</div>';
  try{data=await (await fetch('data/'+d+'.json?'+Date.now())).json();render();}
  catch(e){document.getElementById('tableArea').innerHTML='<div class="empty">この日付のデータを読み込めませんでした。</div>';}
}
function render(){
  const rows=data.rows||data.items||[];   /* data.items は旧形式 JSON 後方互換 */
  const cnt=data.counts||{};
  let total=cnt.qualifying;
  if(total==null) total=(data.count_total!=null?data.count_total:rows.length);
  const cntChip = data.capped
    ? '<div class="chip"><span class="num">'+total+'</span> 社該当（上位 '+rows.length+' 社を掲載）</div>'
    : '<div class="chip"><span class="num">'+rows.length+'</span> 社該当</div>';
  document.getElementById('summary').innerHTML=
    cntChip+
    '<div class="chip">'+esc(data.session_window||'')+'</div>'+
    (data.generated_at?'<div class="chip">生成 '+esc(data.generated_at)+'</div>':'');
  const c=data.criteria||{};
  document.getElementById('note').textContent=
    '抽出条件：値上がり率≥+'+(c.min_pct??5)+'% かつ 売買代金≥'+((c.min_turnover_yen??1e7)/1e6)+'百万円／東証個別株のみ・時価総額≥'+(c.min_mcap_oku??100)+'億円'+(c.max_rank?'・上昇率上位'+c.max_rank+'社':'')+'。時価総額は当日終値×発行済株式数（億円・四捨五入）。† は増資・自己株で株探最新株数と>1%乖離。';
  let h='<table><thead><tr><th class="r">#</th><th>コード</th><th>銘柄</th><th>市場</th><th class="r">時価総額<br>(億円)</th><th class="r">上昇率</th><th class="r">終値<br>(円)</th><th class="r">売買代金<br>(億円)</th><th>変動要因</th></tr></thead><tbody>';
  rows.forEach(r=>{
    let factor=esc(r.factor||'（材料未確認）');
    const fk=(r.factor_kind||'').replace(/[\[\]]/g,'');
    if(fk==='開示'&&r.disclosures&&r.disclosures.length&&r.disclosures[0].pdf_url){factor=factor+' <a href="'+esc(r.disclosures[0].pdf_url)+'" target="_blank">[開示PDF]</a>';}
    h+='<tr>'+
      '<td class="rank">'+(r.rank||'')+'</td>'+
      '<td class="code rankcode" data-rank="'+(r.rank||'')+'"><a href="https://kabutan.jp/stock/?code='+esc(r.code)+'" target="_blank">'+esc(r.code)+'</a></td>'+
      '<td class="name" data-code="'+esc(r.code)+'">'+esc(r.name)+'</td>'+
      '<td class="mkt">'+esc(fmtMarket(r.market))+'</td>'+
      '<td class="num" data-label="時価総額(億円)">'+fmtMcap(r.mcap_oku,r.mcap_flag)+'</td>'+
      '<td class="pct" data-label="上昇率">'+fmtPct(r.pct)+'</td>'+
      '<td class="num" data-label="終値(円)">'+fmtNum(r.close)+'</td>'+
      '<td class="num" data-label="売買代金(億円)">'+fmtTurnoverOku(r)+'</td>'+
      '<td class="factor">'+kindBadge(r.factor_kind)+factor+'</td>'+
    '</tr>';
  });
  h+='</tbody></table>';
  document.getElementById('tableArea').innerHTML=h;
  // 除外（薄商い／時価総額<100億）を折りたたみで
  const c2=data.criteria||{};
  const tmM=((c2.min_turnover_yen??1e7)/1e6);
  const mcO=(c2.min_mcap_oku??100);
  const pctMin=(c2.min_pct??5);
  let dh='';
  const dt=data.dropped_turnover||[];
  if(dt.length){
    dh+='<details class="dropped card" style="padding:0 14px 10px;"><summary>参考：値上がり率≥+'+pctMin+'% だが売買代金&lt;'+tmM+'百万円 で除外（薄商い '+dt.length+'件）</summary><table><thead><tr><th>コード</th><th>銘柄</th><th class="r">上昇率</th><th class="r">売買代金<br>(百万円)</th></tr></thead><tbody>';
    dt.forEach(r=>{dh+='<tr><td class="code">'+esc(r.code)+'</td><td class="name">'+esc(r.name)+'</td><td class="pct" data-label="上昇率">'+fmtPct(r.pct)+'</td><td class="num" data-label="売買代金(百万円)">'+fmtTurnover(r.turnover_m)+'</td></tr>';});
    dh+='</tbody></table></details>';
  }
  const dm=data.dropped_mcap||[];
  if(dm.length){
    dh+='<details class="dropped card" style="padding:0 14px 10px;margin-top:12px;"><summary>参考：値上がり率・売買代金は満たすが時価総額&lt;'+mcO+'億円 で除外（'+dm.length+'件）</summary><table><thead><tr><th>コード</th><th>銘柄</th><th class="r">上昇率</th><th class="r">時価総額<br>(億円)</th></tr></thead><tbody>';
    dm.forEach(r=>{dh+='<tr><td class="code">'+esc(r.code)+'</td><td class="name">'+esc(r.name)+'</td><td class="pct" data-label="上昇率">'+fmtPct(r.pct)+'</td><td class="num" data-label="時価総額(億円)">'+fmtMcap(r.mcap_oku)+'</td></tr>';});
    dh+='</tbody></table></details>';
  }
  document.getElementById('droppedArea').innerHTML=dh;
}
init();
</script>
</body></html>"""
