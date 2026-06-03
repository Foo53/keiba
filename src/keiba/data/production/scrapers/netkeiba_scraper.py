"""netkeiba.com スクレイパ

最もデータが豊富なソース。過去成績（last_3f, running_style, passing_order 含む）、
騎手成績、厩舎成績、調教情報、血統などを取得する。
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup

from keiba.data.production.exceptions import ScraperError
from keiba.data.production.scrapers.base_scraper import BaseScraper


class NetkeibaScraper(BaseScraper):
    """netkeiba.com (db.netkeiba.com) 向けスクレイパ"""

    base_url = "https://db.netkeiba.com"

    @property
    def encoding(self) -> str:
        return "euc-jp"

    # ------------------------------------------------------------------
    # レース結果
    # ------------------------------------------------------------------

    def get_race_results(self, race_id: str) -> dict:
        """レース結果ページを取得・パース。

        URL: /race/{race_id}/

        Returns: {race: dict, entries: list[dict]}
        """
        html = self.fetch_page(f"/race/{race_id}/", cache_ttl=604800)
        return self._parse_race_results(html, race_id)

    def _parse_race_results(self, html: str, race_id: str) -> dict:
        soup = BeautifulSoup(html, "lxml")

        # レース基本情報
        race_info = self._parse_race_header(soup, race_id)

        # レース結果テーブル
        table = soup.find("table", class_="race_table_01")
        if not table:
            raise ScraperError(f"No result table found for race {race_id}")

        entries = []
        for row in table.find_all("tr")[1:]:  # ヘッダー行をスキップ
            cells = row.find_all(["th", "td"])
            if len(cells) < 20:
                continue

            entry = self._parse_result_row(cells, race_id)
            entries.append(entry)

        return {"race": race_info, "entries": entries}

    def _parse_race_header(self, soup: BeautifulSoup, race_id: str) -> dict:
        """race_head div からレース基本情報を抽出"""
        race_head = soup.find("div", class_="race_head")
        text = race_head.get_text() if race_head else ""

        # レース名
        race_name = ""
        race_title_el = soup.find("dl", class_="race_header")
        if race_title_el:
            # dt or the first prominent text
            for dt in race_title_el.find_all("dt"):
                race_name = dt.get_text(strip=True)
                break

        if not race_name:
            # Fallback: title タグから
            title_el = soup.find("title")
            if title_el:
                title_text = title_el.get_text(strip=True)
                race_name = title_text.split("｜")[0].strip()

        # 距離・コース
        distance = 0
        track_type = "芝"
        dist_match = re.search(r"(芝|ダート|障害)[^\d]*(\d+)m", text)
        if dist_match:
            track_type = dist_match.group(1)
            distance = int(dist_match.group(2))

        # 天候
        weather = ""
        weather_match = re.search(r"天候\s*:\s*(晴|曇|雨|小雨|雪)", text)
        if weather_match:
            weather = weather_match.group(1)

        # 馬場状態
        condition = ""
        cond_match = re.search(r"(芝|ダート)\s*:\s*(良|稍重|重|不良)", text)
        if cond_match:
            condition = cond_match.group(2)

        # コース・日付
        course = ""
        course_match = re.search(r"(\d{4})年(\d{2})月(\d{2})日", text)
        race_date = ""
        if course_match:
            race_date = f"{course_match.group(1)}-{course_match.group(2)}-{course_match.group(3)}"

        # コース名（race_head内のテキストから推測）
        for course_name in ["東京", "中山", "京都", "阪神", "中京", "福島", "新潟", "小倉", "札幌", "函館"]:
            if course_name in text:
                course = course_name
                break

        # grade
        grade = "L"
        for g in ["GI", "GII", "GIII", "OP"]:
            if g in text or g in race_name:
                grade = g
                break

        return {
            "race_id": race_id,
            "race_name": race_name,
            "race_date": race_date,
            "course": course,
            "distance": distance,
            "track_type": track_type,
            "grade": grade,
            "weather": weather,
            "track_condition": condition,
        }

    def _parse_result_row(self, cells: list, race_id: str) -> dict:
        """結果テーブルの1行をパース"""
        # セルインデックス（netkeiba の標準カラム順）
        # 0:着順 1:枠番 2:馬番 3:馬名 4:性齢 5:斤量 6:騎手
        # 7:タイム 8:着差  ... 14:通過 15:上り 16:単勝 17:人気
        # 18:馬体重  ... 21:調教師

        def text(idx: int) -> str:
            return cells[idx].get_text(strip=True) if idx < len(cells) else ""

        def link_href(idx: int) -> str:
            a = cells[idx].find("a", href=True) if idx < len(cells) else None
            return a["href"] if a else ""

        # 馬ID
        horse_link = link_href(3)
        horse_id = horse_link.split("/horse/")[-1].strip("/") if "/horse/" in horse_link else ""

        # 性別・年齢
        sex_age = text(4)
        gender = "牡"
        age = 0
        if sex_age:
            for g in ["牡", "牝", "セ"]:
                if g in sex_age:
                    gender = g
                    age_str = sex_age.replace(g, "").strip()
                    age = int(age_str) if age_str.isdigit() else 0
                    break

        # 馬体重
        weight_text = text(18)
        horse_weight = 0.0
        weight_change = 0.0
        weight_match = re.match(r"(\d+)\(([+-]?\d+)\)", weight_text)
        if weight_match:
            horse_weight = float(weight_match.group(1))
            weight_change = float(weight_match.group(2))

        # 通過順（例: "9-9" → "9-9"）
        passing_order = text(14)

        # 上がり3F
        last_3f = None
        last_3f_text = text(15)
        if last_3f_text:
            try:
                last_3f = float(last_3f_text)
            except ValueError:
                pass

        # タイム
        finish_time = None
        time_text = text(7)
        if time_text and ":" in time_text:
            try:
                parts = time_text.split(":")
                finish_time = int(parts[0]) * 60 + float(parts[1])
            except (ValueError, IndexError):
                pass

        # オッズ・人気
        odds = 0.0
        popularity = 0
        try:
            odds = float(text(16))
        except ValueError:
            pass
        try:
            popularity = int(text(17))
        except ValueError:
            pass

        # 騎手ID
        jockey_link = link_href(6)
        jockey_id = ""
        if "/jockey/" in jockey_link:
            jockey_id = jockey_link.split("/jockey/")[-1].strip("/")

        # 調教師（細胞21あたり）
        trainer_text = text(21) if len(cells) > 21 else ""
        trainer_name = re.sub(r"\[.*?\]", "", trainer_text).strip()

        # 脚質推定（通過順から）
        running_style = self._infer_running_style(passing_order)

        return {
            "entry_id": f"{race_id}-{text(2):0>2}",
            "horse_id": horse_id,
            "horse_name": text(3),
            "gender": gender,
            "age": age,
            "weight_carried": float(text(5)) if text(5) else 0.0,
            "jockey_id": jockey_id,
            "jockey_name": text(6),
            "trainer_name": trainer_name,
            "post_position": int(text(2)) if text(2).isdigit() else 0,
            "bracket_number": int(text(1)) if text(1).isdigit() else 0,
            "horse_weight": horse_weight,
            "weight_change": weight_change,
            "finish_position": int(text(0)) if text(0).isdigit() else 0,
            "finish_time": finish_time,
            "last_3f": last_3f,
            "passing_order": passing_order,
            "running_style": running_style,
            "odds": odds,
            "popularity": popularity,
        }

    @staticmethod
    def _infer_running_style(passing_order: str) -> str:
        """通過順から脚質を推定"""
        if not passing_order:
            return "差し"
        positions = [int(p) for p in passing_order.split("-") if p.isdigit()]
        if not positions:
            return "差し"
        avg_pos = sum(positions) / len(positions)
        if avg_pos <= 2.5:
            return "逃げ"
        elif avg_pos <= 4.5:
            return "先行"
        elif avg_pos <= 7.0:
            return "差し"
        else:
            return "追込"

    # ------------------------------------------------------------------
    # 馬の過去成績
    # ------------------------------------------------------------------

    def get_horse_past_performances(self, horse_id: str) -> list[dict]:
        """馬の全出走履歴を取得。

        URL: /horse/result/{horse_id}/

        Returns: list[dict] — 各出走の過去成績
        """
        html = self.fetch_page(f"/horse/result/{horse_id}/", cache_ttl=604800)
        return self._parse_horse_results(html)

    def _parse_horse_results(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", class_="db_h_race_results")
        if not table:
            return []

        results = []
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 28:
                continue
            results.append(self._parse_horse_result_row(cells))

        return results

    def _parse_horse_result_row(self, cells: list) -> dict:
        """馬成績テーブルの1行をパース

        カラム順:
        0:日付 1:開催 2:天気 3:R 4:レース名 5:映像 6:頭数
        7:枠番 8:馬番 9:オッズ 10:人気 11:着順 12:騎手 13:斤量
        14:距離 15:馬場(重量) 16:馬場状態 17:馬場指数 18:タイム
        19:着差 ... 26:通過 27:ペース 28:上り 29:馬体重 ...
        """
        def text(idx: int) -> str:
            return cells[idx].get_text(strip=True) if idx < len(cells) else ""

        # 日付
        date_str = text(0)
        race_date = ""
        if date_str:
            race_date = date_str.replace("/", "-")

        # 距離・馬場
        distance_str = text(14)
        track_type = "芝"
        distance = 0
        dist_match = re.match(r"(芝|ダート|障害)(\d+)", distance_str)
        if dist_match:
            track_type = dist_match.group(1)
            distance = int(dist_match.group(2))

        # タイム
        finish_time = None
        time_text = text(18)
        if time_text and ":" in time_text:
            try:
                parts = time_text.split(":")
                finish_time = int(parts[0]) * 60 + float(parts[1])
            except (ValueError, IndexError):
                pass

        # 上がり
        last_3f = None
        last_3f_text = text(26)
        if last_3f_text:
            try:
                last_3f = float(last_3f_text)
            except ValueError:
                pass

        # 通過順
        passing_order = text(24)

        # 着順
        finish_pos_text = text(11)
        finish_position = 0
        pos_match = re.match(r"(\d+)", finish_pos_text)
        if pos_match:
            finish_position = int(pos_match.group(1))

        # 頭数
        total_runners = int(text(6)) if text(6).isdigit() else 0

        # 人気・オッズ
        popularity = int(text(10)) if text(10).isdigit() else 0
        odds = 0.0
        try:
            odds = float(text(9))
        except ValueError:
            pass

        # レース名から grade 推定
        race_name = text(4)
        grade = "L"
        for g in ["GI", "GII", "GIII"]:
            if g in race_name:
                grade = g
                break
        if "OP" in race_name and grade == "L":
            grade = "OP"

        # 開催からコース名推定
        course = ""
        kaisai = text(1)
        for c in ["東京", "中山", "京都", "阪神", "中京", "福島", "新潟", "小倉", "札幌", "函館"]:
            if c in kaisai:
                course = c
                break

        # 馬場状態
        track_condition = text(16)

        # レースID推定（日付と開催番号から）
        race_id = f"{date_str.replace('/', '')}-{course}-R{text(3)}" if date_str and course else ""

        running_style = self._infer_running_style(passing_order)

        return {
            "race_id": race_id,
            "race_date": race_date,
            "race_name": race_name,
            "course": course,
            "distance": distance,
            "track_type": track_type,
            "track_condition": track_condition,
            "finish_position": finish_position,
            "total_runners": total_runners,
            "jockey_name": text(12),
            "weight_carried": float(text(13)) if text(13) else 0.0,
            "finish_time": finish_time,
            "popularity": popularity,
            "odds": odds,
            "last_3f": last_3f,
            "running_style": running_style,
            "passing_order": passing_order,
            "grade": grade,
        }

    # ------------------------------------------------------------------
    # 馬プロフィール
    # ------------------------------------------------------------------

    def get_horse_profile(self, horse_id: str) -> dict:
        """馬のプロフィール情報を取得。

        URL: /horse/{horse_id}/

        Returns: dict with horse details
        """
        html = self.fetch_page(f"/horse/{horse_id}/", cache_ttl=86400)
        return self._parse_horse_profile(html, horse_id)

    def _parse_horse_profile(self, html: str, horse_id: str) -> dict:
        soup = BeautifulSoup(html, "lxml")

        # 馬名（title タグから）
        title_el = soup.find("title")
        horse_name = ""
        if title_el:
            title_text = title_el.get_text(strip=True)
            horse_name = title_text.split("(")[0].strip().split("｜")[0].strip()

        # プロフィールテーブル
        profile = {}
        table = soup.find("table", class_="db_prof_table")
        if table:
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    val = cells[1].get_text(strip=True)
                    profile[key] = val

        # 性別・年齢
        gender = "牡"
        birth_year = 0
        birth_match = profile.get("生年月日", "")
        if birth_match:
            year_match = re.search(r"(\d{4})年", birth_match)
            if year_match:
                birth_year = int(year_match.group(1))
                age = datetime.now().year - birth_year
            else:
                age = 0

        # 調教師
        trainer_text = profile.get("調教師", "")
        trainer_name = re.sub(r"\(.*?\)", "", trainer_text).strip()

        # 血統
        pedigree_sire = ""
        pedigree_dam_sire = ""
        blood_table = soup.find("table", class_="blood_table")
        if blood_table:
            tds = blood_table.find_all("td")
            if tds:
                pedigree_sire = tds[0].get_text(strip=True)
            if len(tds) > 3:
                pedigree_dam_sire = tds[3].get_text(strip=True)

        return {
            "horse_id": horse_id,
            "horse_name": horse_name,
            "birth_year": birth_year,
            "gender": gender,
            "age": age if birth_year else 0,
            "trainer_name": trainer_name,
            "pedigree_sire": pedigree_sire,
            "pedigree_dam_sire": pedigree_dam_sire,
        }

    # ------------------------------------------------------------------
    # 騎手成績
    # ------------------------------------------------------------------

    def get_jockey_stats(self, jockey_id: str) -> dict:
        """騎手成績を取得。

        URL: /jockey/result/{jockey_id}/

        Returns: dict matching jockey_stats contract
        """
        html = self.fetch_page(f"/jockey/result/{jockey_id}/", cache_ttl=86400)
        return self._parse_jockey_stats(html, jockey_id)

    def _parse_jockey_stats(self, html: str, jockey_id: str) -> dict:
        soup = BeautifulSoup(html, "lxml")

        # 騎手名
        title_el = soup.find("title")
        jockey_name = ""
        if title_el:
            jockey_name = title_el.get_text(strip=True).split("の")[0].strip()

        # 成績テーブルを探す
        total_rides = 0
        wins = 0
        places = 0
        win_rate = 0.0
        place_rate = 0.0

        # 通算成績テキストから抽出
        text = soup.get_text()
        career_match = re.search(r"(\d+)戦(\d+)勝", text)
        if career_match:
            total_rides = int(career_match.group(1))
            wins = int(career_match.group(2))

        # 勝率・連対率
        # パターン: [数字-数字-数字-数字] (1着-2着-3着-着外)
        bracket_match = re.search(r"\[(\d+)-(\d+)-(\d+)-(\d+)\]", text)
        if bracket_match:
            wins = int(bracket_match.group(1))
            places = wins + int(bracket_match.group(2))
            total_rides = wins + int(bracket_match.group(2)) + int(bracket_match.group(3)) + int(bracket_match.group(4))

        if total_rides > 0:
            win_rate = round(wins / total_rides, 3)
            place_rate = round(places / total_rides, 3)

        return {
            "jockey_id": jockey_id,
            "jockey_name": jockey_name,
            "period": str(datetime.now().year),
            "total_rides": total_rides,
            "wins": wins,
            "places": places,
            "win_rate": win_rate,
            "place_rate": place_rate,
            "favorite_win_rate": 0.0,
            "course_stats": {},
        }

    # ------------------------------------------------------------------
    # オッズ
    # ------------------------------------------------------------------

    def get_odds(self, race_id: str) -> list[dict]:
        """オッズページを取得。

        URL: /odds/index.php?race_id={race_id}&rf=race_submenu

        Returns: list[dict] — 各馬のオッズ
        """
        html = self.fetch_page(
            f"/odds/index.php?race_id={race_id}&rf=race_submenu",
            cache_ttl=300,
        )
        return self._parse_odds(html, race_id)

    def _parse_odds(self, html: str, race_id: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        entries = []

        table = soup.find("table", class_="odds_table")
        if not table:
            # 代替: レース結果ページのオッズ列を使用
            return entries

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 5:
                continue

            horse_name = cells[1].get_text(strip=True)
            win_odds = 0.0
            try:
                win_odds = float(cells[3].get_text(strip=True))
            except ValueError:
                pass

            popularity = 0
            try:
                popularity = int(cells[4].get_text(strip=True))
            except ValueError:
                pass

            entries.append({
                "entry_id": f"{race_id}-{cells[0].get_text(strip=''):0>2}",
                "horse_name": horse_name,
                "win_odds": win_odds,
                "popularity_rank": popularity,
            })

        return entries

    # ------------------------------------------------------------------
    # レース検索
    # ------------------------------------------------------------------

    def search_races(self, year: int, month: int) -> list[str]:
        """指定年月のレースID一覧を取得。

        URL構造: /race/list/{YYYYMM}/ → 開催日一覧
                 /race/list/{YYYYMMDD}/ → レースID一覧

        Returns: list[str] — race_id のリスト
        """
        month_str = f"{year}{month:02d}"
        # 月ページ → 開催日一覧
        html = self.fetch_page(f"/race/list/{month_str}/", cache_ttl=86400)
        date_ids = self._parse_race_dates(html)

        race_ids = []
        for date_id in date_ids:
            try:
                day_html = self.fetch_page(f"/race/list/{date_id}/", cache_ttl=86400)
                day_races = self._parse_race_ids_from_day(day_html)
                race_ids.extend(day_races)
            except Exception as e:
                self.logger.warning(f"Failed to fetch races for {date_id}: {e}")
                continue

        return race_ids

    def _parse_race_dates(self, html: str) -> list[str]:
        """月ページから開催日ID一覧を抽出"""
        soup = BeautifulSoup(html, "lxml")
        dates = []
        for a in soup.find_all("a", href=True):
            match = re.search(r"/race/list/(\d{8})/", a["href"])
            if match:
                dates.append(match.group(1))
        return list(dict.fromkeys(dates))

    def _parse_race_ids_from_day(self, html: str) -> list[str]:
        """開催日ページからレースID一覧を抽出"""
        soup = BeautifulSoup(html, "lxml")
        race_ids = []
        for a in soup.find_all("a", href=True):
            match = re.search(r"/race/(\d{12,})/", a["href"])
            if match:
                race_ids.append(match.group(1))
        return list(dict.fromkeys(race_ids))

    # ------------------------------------------------------------------
    # ヘルスチェック
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """netkeiba.com がアクセス可能か確認"""
        try:
            html = self.fetch_page("/", cache_ttl=3600)
            return "netkeiba" in html.lower() or len(html) > 1000
        except Exception as e:
            self.logger.warning(f"Netkeiba health check failed: {e}")
            return False
