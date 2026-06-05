"""競馬レース出馬表取得スクリプト

netkeibaの出馬表HTMLから出走馬情報を取得する。
過去成績はJRA-VAN DBから取得するため、ここでは以下のみを取得:
- 馬名、枠番、馬番、性別、年齢、斤量、騎手、調教師、厩舎
- 未定騎手（○○）の検出
- 騎手重複チェック

HTMLテーブル構造（netkeiba ShutubaTable）:
  [0]枠番 [1]馬番 [2]印 [3]馬名 [4]性齢 [5]斤量 [6]騎手 [7]厩舎
  [8]空 [9]馬体重 [10]人気 [11-14]機能ボタン等
"""

import re
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, "src")


def fetch_html(url: str, encoding: str = "EUC-JP") -> str:
    """HTMLを取得してデコード"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            return raw.decode("utf-8", errors="replace")


def _clean_cell(html_fragment: str) -> str:
    """HTML断片からテキストを抽出"""
    return re.sub(r'<[^>]+>', ' ', html_fragment).strip()


def parse_netkeiba_shutuba(html: str) -> list[dict]:
    """netkeiba出馬表HTMLから出走馬情報を抽出

    テーブル行は固定15列:
    [0]枠 [1]馬番 [2]印 [3]馬名 [4]性齢 [5]斤量
    [6]騎手 [7]厩舎 [8]空 [9]馬体重 [10]人気 [11-14]ボタン等
    """
    horses = []

    # ShutubaTable クラスのテーブルを特定
    table_match = re.search(
        r'<table[^>]*class="[^"]*Shutuba[^"]*"[^>]*>(.*?)</table>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not table_match:
        return horses

    table_html = table_match.group(1)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

    for row_html in rows:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL | re.IGNORECASE)
        if len(tds) < 8:
            continue  # ヘッダ行をスキップ

        cells = [_clean_cell(td) for td in tds]

        # 馬番が数値かチェック（ヘッダ行除外）
        try:
            wakuban = int(cells[0])
            umaban = int(cells[1])
        except (ValueError, IndexError):
            continue

        name = cells[3].strip()
        sex_age_raw = cells[4].strip()
        weight_raw = cells[5].strip()
        jockey_raw = cells[6].strip()
        trainer_raw = cells[7].strip()

        # 性齢パース: "牡6", "牝5", "セ8"
        sa_match = re.match(r'^(牡|牝|セ)(\d+)', sex_age_raw)
        if not sa_match:
            continue
        sex_code = {"牡": "1", "牝": "2", "セ": "3"}[sa_match.group(1)]
        age = int(sa_match.group(2))

        # 斤量パース
        try:
            weight = float(weight_raw)
        except ValueError:
            continue

        # 騎手（○○はそのまま）
        jockey = jockey_raw if jockey_raw else "○○"

        # 厩舎（"美浦  田中博" → トレーナー名抽出）
        # "栗東  藤原" → trainer="藤原英昭", barn="栗東"
        barn_match = re.match(r'(栗東|美浦)\s+(.+)', trainer_raw)
        barn = barn_match.group(1) if barn_match else ""
        trainer_short = barn_match.group(2).strip() if barn_match else trainer_raw

        horses.append({
            "wakuban": wakuban,
            "umaban": umaban,
            "name": name,
            "sex": sex_code,
            "age": age,
            "weight": weight,
            "jockey": jockey,
            "trainer": trainer_short,
            "barn": barn,
        })

    return horses


def validate_jockeys(horses: list[dict]) -> list[str]:
    """騎手の重複と未定をチェック"""
    issues = []
    jockey_map = {}
    for h in horses:
        j = h["jockey"]
        if j == "○○":
            issues.append(f"  馬{h['umaban']:2d} {h['name']}: 騎手未定")
        elif j in jockey_map:
            issues.append(
                f"  ⚠️ 騎手重複: {j} → 馬{jockey_map[j]} と 馬{h['umaban']} {h['name']}"
            )
        else:
            jockey_map[j] = f"{h['umaban']}"
    return issues


def get_horse_ids_from_db(horse_names: list[str]) -> dict[str, str]:
    """JRA-VAN DBから馬名→血統登録番号のマッピングを取得"""
    from keiba.data.jrvan.loader import JrVanLoader

    loader = JrVanLoader()
    conn = loader.get_connection()
    try:
        mapping = {}
        for name in horse_names:
            rows = conn.execute(
                "SELECT DISTINCT ketto_toroku_bango FROM race_horse_detail "
                "WHERE horse_name = ? LIMIT 1",
                (name,),
            ).fetchall()
            if rows:
                mapping[name] = rows[0]["ketto_toroku_bango"]
        return mapping
    finally:
        conn.close()


def get_jockey_codes_from_db(jockey_names: list[str]) -> dict[str, str]:
    """JRA-VAN DBから騎手名→騎手コードのマッピングを取得"""
    from keiba.data.jrvan.loader import JrVanLoader

    loader = JrVanLoader()
    conn = loader.get_connection()
    try:
        mapping = {}
        for name in jockey_names:
            if name == "○○":
                continue
            # 部分一致で検索（netkeiba表記が短縮の場合があるため）
            rows = conn.execute(
                "SELECT DISTINCT jockey_code, jockey_name_short "
                "FROM race_horse_detail "
                "WHERE jockey_name_short LIKE ? LIMIT 5",
                (f"%{name}%",),
            ).fetchall()
            if rows:
                # 完全に一致するものを優先
                for r in rows:
                    if r["jockey_name_short"] == name:
                        mapping[name] = r["jockey_code"]
                        break
                else:
                    # 部分一致の最初のもの
                    mapping[name] = rows[0]["jockey_code"]
        return mapping
    finally:
        conn.close()


def fetch_racecard(race_id: str, db_lookup: bool = True) -> dict:
    """出馬表を取得してバリデーション＋DB照合

    race_id: netkeiba形式 (例: 202605030211)
    """
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    print(f"Fetching: {url}", file=sys.stderr)
    html = fetch_html(url)

    horses = parse_netkeiba_shutuba(html)
    print(f"取得完了: {len(horses)}頭", file=sys.stderr)

    # バリデーション
    issues = validate_jockeys(horses)

    # DB照合
    if db_lookup and horses:
        print("DB照合中...", file=sys.stderr)
        horse_names = [h["name"] for h in horses]
        id_map = get_horse_ids_from_db(horse_names)

        jockey_names = [h["jockey"] for h in horses]
        jockey_map = get_jockey_codes_from_db(jockey_names)

        for h in horses:
            h["horse_id"] = id_map.get(h["name"])
            if h["horse_id"] is None:
                print(f"  ⚠️ DB馬IDなし: {h['name']}", file=sys.stderr)
                issues.append(f"  ⚠️ DB馬IDなし: {h['name']}")

            h["jockey_code"] = jockey_map.get(h["jockey"])
            if h["jockey"] != "○○" and h["jockey_code"] is None:
                print(f"  ⚠️ DB騎手コードなし: {h['jockey']}", file=sys.stderr)
                issues.append(f"  ⚠️ DB騎手コードなし: {h['jockey']}")

    return {
        "race_id": race_id,
        "url": url,
        "horses": horses,
        "validation_issues": issues,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="レース出走馬情報取得")
    parser.add_argument("race_id", help="netkeiba race_id (例: 202605030211)")
    parser.add_argument("--output", "-o", default="output/racecard.json")
    parser.add_argument("--no-db", action="store_true", help="DB照合スキップ")
    args = parser.parse_args()

    result = fetch_racecard(args.race_id, db_lookup=not args.no_db)
    horses = result["horses"]

    # バリデーション表示
    if result["validation_issues"]:
        print("\n=== バリデーション ===", file=sys.stderr)
        for issue in result["validation_issues"]:
            print(issue, file=sys.stderr)

    # 保存
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n保存: {output_path}", file=sys.stderr)

    # サマリー表示
    print(f"\n=== 出走馬一覧 ({len(horses)}頭) ===")
    print(f"{'枠':>2} {'番':>2} | {'馬名':<16} | {'性齢':<3} | {'斤量':>5} | {'騎手':<10} | {'厩舎':<10} | {'DB ID':<12}")
    print("-" * 85)
    for h in horses:
        sex_str = {"1": "牡", "2": "牝", "3": "セ"}.get(h.get("sex", "1"), "?")
        hid = h.get("horse_id", "") or "---"
        print(f"{h['wakuban']:>2} {h['umaban']:>2} | {h['name']:<16} | {sex_str}{h['age']:<2} | {h['weight']:>5.1f} | {h['jockey']:<10} | {h.get('barn','')}{h.get('trainer',''):<8} | {hid}")
