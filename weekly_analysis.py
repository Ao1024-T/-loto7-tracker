"""
ロト7 週次自動分析スクリプト
=========================================

やること:
1. 最新の当選番号データを取得
2. (prediction.txt があれば) 今回の予想数字と実際の当選番号とのズレを比較
3. 今回の当選番号と「本数字の一致が多い」過去の回を探し、その翌週の結果を一覧化
4. 結果を Markdown レポートとして reports/ フォルダに保存

使い方:
    # その場で予想数字を渡す場合
    python weekly_analysis.py --predicted 3 7 12 18 24 29 35

    # 事前に prediction.txt (例: "3,7,12,18,24,29,35") を用意しておく場合
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


def load_prediction(cli_predicted):
    if cli_predicted:
        return list(cli_predicted)
    if os.path.exists("prediction.txt"):
        with open("prediction.txt", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return [int(x) for x in content.split(",")]
    return None


def build_report(df: pd.DataFrame, predicted) -> str:
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

    if predicted:
        predicted_set = set(predicted)
        matched = predicted_set & actual_numbers
        lines.append("## 今回の予想とのズレ")
        lines.append(f"- 予想した数字: {sorted(predicted_set)}")
        lines.append(f"- 一致した数字: {sorted(matched)}（{len(matched)}個 / 7個中）")
        lines.append("")
    else:
        lines.append("## 今回の予想とのズレ")
        lines.append("- (predicted オプション、または prediction.txt が未指定のためスキップ)")
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
    predicted = load_prediction(args.predicted)
    report = build_report(df, predicted)

    print(report)

    os.makedirs("reports", exist_ok=True)
    filename = f"reports/loto7_report_{datetime.date.today()}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n保存しました -> {filename}")


if __name__ == "__main__":
    main()
