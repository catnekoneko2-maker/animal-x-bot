# config.py

import datetime

# 緊急停止フラグ
ENABLED = True  # 停止したいときは False にしてコミット＆プッシュ

# 候補アカウント一覧（@なし or ありどちらでもOKだが、@は付けない方が楽）
# 実運用時にここをあなたが編集します。
CANDIDATE_ACCOUNTS = [
    "example_animal_account_1",
    "example_animal_account_2",
    "example_animal_account_3",
]

# 1回の起動でチェックする最大アカウント数
MAX_ACCOUNTS_PER_RUN = 3

# 1アカウントのタイムラインから取得する最大ツイート数
MAX_TWEETS_PER_ACCOUNT = 20

# 最低いいね数（これ未満は候補にしない）
MIN_FAVES = 50

# 連続で「使えるツイートが見つからなかった」回数のしきい値
EXHAUSTED_THRESHOLD = 5

# テキストNGワード（政治・宗教・差別などの一例）
NG_KEYWORDS = [
    "政治",
    "選挙",
    "宗教",
    "テロ",
    "差別",
    "戦争",
    # 必要に応じて増やす
]

# 今日の日付（YYYY-MM-DD）文字列を返すヘルパー
def today_str() -> str:
    return datetime.date.today().isoformat()
