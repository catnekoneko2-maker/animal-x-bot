# bot.py

import json
import os
import random
import sys
from typing import Dict, Any, List

import tweepy  # requirements.txt で指定

import config


STATE_FILE = "state.json"


# ---- state.json の読み書き ----

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {
            "posted_tweet_ids": [],
            "consecutive_empty_runs": {},
            "exhausted_accounts": [],
        }
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---- X API クライアント作成 ----

def create_api_client() -> tweepy.API:
    """
    X API (v1.1) 用 Tweepy クライアントを生成
    ※ 環境変数からキーを取得
    """
    api_key = os.getenv("X_API_KEY")
    api_key_secret = os.getenv("X_API_KEY_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

    if not all([api_key, api_key_secret, access_token, access_token_secret]):
        print("X API の環境変数がセットされていません。実投稿はスキップします。", file=sys.stderr)
        return None  # 型的にはAPIだが、未設定時は None を返す

    auth = tweepy.OAuth1UserHandler(
        api_key,
        api_key_secret,
        access_token,
        access_token_secret,
    )
    api = tweepy.API(auth)
    return api


# ---- テキスト関連のフィルタ ----

def contains_ng_keyword(text: str) -> bool:
    lower = text.lower()
    for kw in config.NG_KEYWORDS:
        if kw in text or kw.lower() in lower:
            return True
    return False


def generate_caption(original_text: str) -> str:
    """
    キャプション生成ロジック。
    いまは単純に元テキストをそのまま返す。
    後で「英語→日本語翻訳＋少しパラフレーズ」に差し替える。
    """
    return original_text


# ---- 候補ツイート探索 ----

def is_video_tweet(status: tweepy.Status) -> bool:
    """
    ツイートに video / animated_gif が含まれているか判定
    """
    try:
        media = status.extended_entities.get("media", [])
    except AttributeError:
        media = getattr(status, "extended_entities", {}).get("media", []) if hasattr(status, "extended_entities") else []
    for m in media:
        if m.get("type") in ("video", "animated_gif"):
            return True
    return False


def pick_candidate_tweet(
    api: tweepy.API,
    account: str,
    state: Dict[str, Any],
) -> Any:
    """
    指定アカウントから「投稿候補ツイート」を1件探して返す。
    なければ None。
    """
    screen_name = account.lstrip("@")
    posted_ids: List[str] = state.get("posted_tweet_ids", [])

    try:
        statuses = api.user_timeline(
            screen_name=screen_name,
            count=config.MAX_TWEETS_PER_ACCOUNT,
            tweet_mode="extended",  # full_text を取る
        )
    except Exception as e:
        print(f"[WARN] user_timeline 取得失敗 @{screen_name}: {e}", file=sys.stderr)
        return None

    for status in statuses:
        tweet_id = str(status.id)
        full_text = getattr(status, "full_text", status.text)

        # すでに使ったツイートはスキップ
        if tweet_id in posted_ids:
            continue

        # 動画付きでないならスキップ
        if not is_video_tweet(status):
            continue

        # NGワード含むならスキップ
        if contains_ng_keyword(full_text):
            continue

        # いいね数チェック
        favorite_count = getattr(status, "favorite_count", 0)
        if favorite_count < config.MIN_FAVES:
            continue

        # 条件を満たす1件目を採用
        return status

    # 条件を満たすものが1件もない
    return None


# ---- X への投稿（引用ポスト） ----

def post_to_x(api: tweepy.API, status: tweepy.Status) -> str:
    """
    指定ツイートを引用して投稿。
    成功したら新しいツイートIDを文字列で返す。
    """
    original_text = getattr(status, "full_text", status.text)
    caption = generate_caption(original_text)

    screen_name = status.user.screen_name
    original_id = status.id
    attachment_url = f"https://x.com/{screen_name}/status/{original_id}"

    # 実運用時はここを有効化する
    new_status = api.update_status(
        status=caption,
        attachment_url=attachment_url,
    )
    print(f"[INFO] Posted quote tweet: {new_status.id} (from @{screen_name}/{original_id})")
    return str(new_status.id)


# ---- メイン処理 ----

def main():
    # 緊急停止フラグ
    if not config.ENABLED:
        print("[INFO] Bot is disabled (ENABLED = False). Exiting.")
        return

    state = load_state()

    exhausted_accounts = set(state.get("exhausted_accounts", []))
    all_accounts = [a for a in config.CANDIDATE_ACCOUNTS if a not in exhausted_accounts]

    if not all_accounts:
        print("[WARN] 有効な候補アカウントがありません（すべて枯渇済み）。")
        return

    # この起動で試すアカウントをランダムに抽出
    k = min(config.MAX_ACCOUNTS_PER_RUN, len(all_accounts))
    target_accounts = random.sample(all_accounts, k=k)

    api = create_api_client()
    if api is None:
        print("[WARN] X API クライアント未設定のため、投稿処理はスキップします。候補探索ロジックだけ動かします。")

    posted_this_run = False

    # 連続空振りカウンタを取り出す
    consecutive_empty = state.get("consecutive_empty_runs", {})

    for account in target_accounts:
        if posted_this_run:
            # すでにどこかのアカウントで投稿が決まっていれば残りは見ない
            break

        print(f"[INFO] Checking account @{account} ...")
        if api is None:
            candidate = None
        else:
            candidate = pick_candidate_tweet(api, account, state)

        if candidate is None:
            # 見つからなかった → 連続空振りカウント +1
            count = consecutive_empty.get(account, 0) + 1
            consecutive_empty[account] = count
            print(f"[INFO] No candidate tweet found for @{account}. consecutive_empty = {count}")

            # 閾値以上なら枯渇扱い
            if count >= config.EXHAUSTED_THRESHOLD:
                print(f"[INFO] Account @{account} appears exhausted. Marking as exhausted.")
                exhausted_accounts.add(account)
        else:
            # 見つかった → 連続空振りリセット
            consecutive_empty[account] = 0

            if api is not None:
                new_tweet_id = post_to_x(api, candidate)
                # 投稿済みIDとして登録
                posted_ids = state.get("posted_tweet_ids", [])
                posted_ids.append(str(candidate.id))
                state["posted_tweet_ids"] = posted_ids
                posted_this_run = True
            else:
                # API未設定の場合は投稿せずログのみ
                print(f"[DRY-RUN] Candidate found from @{account}: id={candidate.id}")

    # state 更新
    state["consecutive_empty_runs"] = consecutive_empty
    state["exhausted_accounts"] = list(exhausted_accounts)
    save_state(state)

    if not posted_this_run:
        print("[INFO] No tweet was posted in this run.")


if __name__ == "__main__":
    main()
