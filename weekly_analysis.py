"""
ロト7 週次自動分析スクリプト
=========================================

やること:
1. 最新の当選番号データを取得
2. prediction_log.csv の一番下の行(=最新の予想)と実際の当選番号とのズレを比較
3. 今回の当選番号と「本数字の一致が多い」過去の回を探し、その翌週の結果を一覧化
4. 結果を Markdown レポートとして reports/loto7_report_日付.md に保存
   (同時に reports/latest.md にも上書き保存。Webアプリはこの latest.md を読みに行く)

prediction_log.csv の書き方（1行 = 1口の予想。同じ日付で複数行あってもOK。古い行は消さずに、下に追記していく）:
    2026-08-14,3,7,12,18,24,29,35
    2026-08-14,2,9,14,19,25,30,36
    2026-08-21,4,10,15,21,28,32,36

  → この例だと 8/14 の抽選には2口(3,7,12,18,24,29,35 と 2,9,14,19,25,30,36)、
    8/21 の抽選には1口だけ予想したことになる。
  → スクリプトは「一番新しい日付」に紐づく行を全部拾って、それぞれの一致数を表示する。

使い方:
    # その場で予想数字を渡す場合(1口のみ。prediction_log.csvより優先される)
    python weekly_analysis.py --predicted 3 7 12 18 24 29 35

    # prediction_log.csv の最新日付の行(複数可)を自動で使う場合
    python weekly_analysis.py

必要なライブラリ:
    pip install requests pandas
"""

import argparse
import datetime
import io
import os

import pandas as pd
import requests

SOURCE_URL = "https://loto7.thekyo.jp/data/loto7.csv"

COLUMN_NAMES = [
    "回別", "抽せん日",
    "本数字1", "本数字2", "本数字3", "本数字4", "本数字5", "本数字6", "本数字7",
    "BONUS数字1", "BONUS数字2",
    "1等口数", "2等口数", "3等口数", "4等口数", "5等口数", "6等口数",
    "1等賞金", "2等賞金", "3等賞金", "4等賞金", "5等賞金", "6等賞金",
    "キャリーオーバー",
]
MAIN_COLS = [f"本数字{i}" for i in range(1, 8)]


def fetch_data() -> pd.DataFrame:
    resp = requests.get(SOURCE_URL, timeout=30)
    resp.raise_for_status()
    raw = resp.content.decode("shift_jis", errors="replace")
    df = pd.read_csv(io.StringIO(raw), header=0, names=COLUMN_NAMES)
    df["抽せん日"] = pd.to_datetime(df["抽せん日"], format="%Y/%m/%d")
    return df.reset_index(drop=True)


def find_similar_draws(df: pd.DataFrame, target_idx: int, top_n: int = 5):
    """target_idx回と本数字の一致数が多い過去の回を探し、その「翌週」の結果とセットで返す"""
    target_numbers = set(df.loc[target_idx, MAIN_COLS])
    candidates = []
    for idx in range(len(df) - 1):  # 最後の1件は「翌週」が存在しないので除外
        if idx == target_idx:
            continue
        row_numbers = set(df.loc[idx, MAIN_COLS])
        overlap = len(target_numbers & row_numbers)
        candidates.append((overlap, idx))

    candidates.sort(key=lambda x: (-x[0], -x[1]))  # 一致数が多い順、同数なら新しい回優先
    top = candidates[:top_n]

    results = []
    for overlap, idx in top:
        row = df.loc[idx]
        next_row = df.loc[idx + 1]
        results.append({
            "similar_kai": int(row["回別"]),
            "similar_date": row["抽せん日"].date(),
            "similar_numbers": [int(row[c]) for c in MAIN_COLS],
            "overlap": overlap,
            "next_kai": int(next_row["回別"]),
            "next_date": next_row["抽せん日"].date(),
            "next_numbers": [int(next_row[c]) for c in MAIN_COLS],
        })
    return results


def load_predictions(cli_predicted):
    """予想数字のリストを取得する(1週に複数口ある場合はリストのリストで返す)。
    優先順位: 1) CLIの--predicted (1口のみ)  2) prediction_log.csv の最新日付の全行
    prediction_log.csv の1行は "日付,数字1,...,数字7" の形式。
    """
    if cli_predicted:
        return [list(cli_predicted)]

    if os.path.exists("prediction_log.csv"):
        with open("prediction_log.csv", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        parsed = []  # [(date_str, [n1..n7]), ...]
        for line in lines:
            parts = line.split(",")
            if len(parts) < 8:
                continue
            try:
                numbers = [int(x) for x in parts[1:8]]
            except ValueError:
                print(f"警告: prediction_log.csv の行の形式が不正です: {line}")
                continue
            parsed.append((parts[0], numbers))

        if parsed:
            latest_date = parsed[-1][0]  # 一番下の行の日付を「今週」とみなす
            return [numbers for date, numbers in parsed if date == latest_date]

    return None


def build_report(df: pd.DataFrame, predictions) -> str:
    latest_idx = len(df) - 1
    latest = df.loc[latest_idx]
    actual_numbers = set(int(latest[c]) for c in MAIN_COLS)

    lines = []
    lines.append(f"# ロト7 週次レポート ({datetime.date.today()})")
    lines.append("")
    lines.append(f"## 最新結果: 第{int(latest['回別'])}回 ({latest['抽せん日'].date()})")
    lines.append(f"- 本数字: {sorted(actual_numbers)}")
    lines.append(f"- ボーナス数字: {int(latest['BONUS数字1'])}, {int(latest['BONUS数字2'])}")
    lines.append("")

    lines.append("## 今回の予想とのズレ")
    if predictions:
        for i, predicted in enumerate(predictions, start=1):
            predicted_set = set(predicted)
            matched = predicted_set & actual_numbers
            label = f"予想{i}" if len(predictions) > 1 else "予想"
            lines.append(f"- {label}: {sorted(predicted_set)}")
            lines.append(f"  → 一致した数字: {sorted(matched)}（{len(matched)}個 / 7個中）")
        lines.append("")
    else:
        lines.append("- (prediction_log.csv が未設定のためスキップ)")
        lines.append("")

    lines.append(f"## 今回と似た過去の回 TOP5（本数字の一致数が多い順）とその翌週の結果")
    lines.append("")
    similar = find_similar_draws(df, latest_idx, top_n=5)
    for s in similar:
        lines.append(
            f"- 第{s['similar_kai']}回 ({s['similar_date']}) "
            f"本数字: {s['similar_numbers']} ← 今回と{s['overlap']}個一致"
        )
        lines.append(
            f"  → 翌週 第{s['next_kai']}回 ({s['next_date']}) の結果: {s['next_numbers']}"
        )
    lines.append("")
    lines.append(
        "※ ロト7は独立試行の完全ランダム抽選のため、過去の類似パターンが次回に影響することは"
        "統計的にはありません。この一覧はあくまで購入時の参考・娯楽目的です。"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--predicted", type=int, nargs=7, metavar="N",
        help="今回の予想数字を7個、スペース区切りで指定 (例: --predicted 3 7 12 18 24 29 35)"
    )
    args = parser.parse_args()

    df = fetch_data()
    predictions = load_predictions(args.predicted)
    report = build_report(df, predictions)

    print(report)

    os.makedirs("reports", exist_ok=True)

    filename = f"reports/loto7_report_{datetime.date.today()}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n保存しました -> {filename}")

    # Webアプリが常に同じURLで最新レポートを取得できるよう、固定名でも上書き保存
    latest_path = "reports/latest.md"
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"保存しました -> {latest_path}")


if __name__ == "__main__":
    main()
