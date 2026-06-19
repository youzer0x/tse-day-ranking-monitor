"""Gmail 送信（東証 値上がり率ランキング通知）。Gmail API（HTTPS）方式。

クラウド環境（claude.ai ルーチン）は HTTP/HTTPS プロキシ経由のため SMTP(465) は
通らない。代わりに OAuth2 リフレッシュトークンでアクセストークンを取得し、Gmail API
の `users.messages.send`（HTTPS）でメールを送る。送信先ドメイン（*.googleapis.com /
oauth2.googleapis.com）は既定の Trusted 許可リストに含まれるため追加のネット許可は不要。
PTS 版 `pts-ranking-monitor/scripts/gmail_sender.py` と同方式（件名のみ日中用）。

必要な環境変数:
  GMAIL_CLIENT_ID     … Google Cloud の OAuth クライアント ID（種類: デスクトップ アプリ）
  GMAIL_CLIENT_SECRET … 同 クライアントシークレット
  GMAIL_REFRESH_TOKEN … get_gmail_token.py でローカル1回だけ取得するリフレッシュトークン
  GMAIL_ADDRESS       … 送信元（自分の Gmail アドレス）
  NOTIFY_TO           … 送信先（省略時は GMAIL_ADDRESS。カンマ区切りで複数可）

scope は gmail.send のみで足りる。標準ライブラリのみ。
"""
import os
import json
import base64
import urllib.parse
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _urlopen_json(req, what):
    """urlopen して JSON を返す。HTTP エラー時は本文（理由）を出して例外送出。

    Gmail の送信失敗（403 など）は本文に原因が書かれている（Gmail API 未有効化＝
    SERVICE_DISABLED／スコープ不足＝ACCESS_TOKEN_SCOPE_INSUFFICIENT／送信元不一致＝
    Delegation denied 等）。これをログに残すと原因が一目で分かる。
    """
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"{what} failed: HTTP {e.code} {e.reason}\n{body}") from None


def _access_token():
    """リフレッシュトークンからアクセストークンを取得する（HTTPS）。"""
    data = urllib.parse.urlencode({
        "client_id": os.environ["GMAIL_CLIENT_ID"],
        "client_secret": os.environ["GMAIL_CLIENT_SECRET"],
        "refresh_token": os.environ["GMAIL_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    return _urlopen_json(req, "Gmail token")["access_token"]


def _subject(session_date, count, total=None, capped=False):
    if capped and total is not None:
        return f"[東証値上がり率ランキング] {session_date}｜{total}社該当・上位{count}社"
    return f"[東証値上がり率ランキング] {session_date}｜{count}社該当"


def _build_raw(sender, recipient, subject, session_date, count, total, capped, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    cnt_txt = (f"{total}社該当（上位{count}社を掲載）" if (capped and total is not None)
               else f"{count}社該当")
    msg.attach(MIMEText(
        f"{session_date} の東証 値上がり率ランキング"
        f"（{cnt_txt}）です。HTML 表示に対応したメーラーでご覧ください。", "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send_gmail(html_body, session_date, count, total=None, capped=False):
    sender = os.environ["GMAIL_ADDRESS"]
    recipient = os.environ.get("NOTIFY_TO", sender)
    subject = _subject(session_date, count, total=total, capped=capped)

    print(f"  Sending email to {recipient} via Gmail API ...")
    token = _access_token()
    payload = json.dumps({
        "raw": _build_raw(sender, recipient, subject, session_date, count, total, capped, html_body)
    }).encode()
    req = urllib.request.Request(
        SEND_URL, data=payload, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    resp = _urlopen_json(req, "Gmail send")
    print(f"  Email sent. id={resp.get('id')}")
    return True
