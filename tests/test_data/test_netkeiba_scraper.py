"""NetkeibaScraper のテスト"""

import pytest
from unittest.mock import MagicMock, patch

from keiba.data.production.scrapers.netkeiba_scraper import NetkeibaScraper
from keiba.data.production.exceptions import ScraperError
from keiba.utils.http_client import RateLimitedHttpClient


@pytest.fixture
def mock_client():
    client = MagicMock(spec=RateLimitedHttpClient)
    return client


@pytest.fixture
def scraper(mock_client):
    return NetkeibaScraper(mock_client)


# ------------------------------------------------------------------
# レース結果パース
# ------------------------------------------------------------------

SAMPLE_RACE_HTML = """
<html>
<head><title>サンライズステークス｜2025年01月06日 | netkeiba</title></head>
<body>
<div class="race_head">
<dl class="race_header">
<dt>サンライズステークス</dt>
<dd>
<span>3歳以上3勝クラス</span>
芝右 外1200m / 天候 : 曇 / 芝 : 良 / 発走 : 15:45
2025年01月06日 1回中山2日目
</dd>
</dl>
</div>
<table class="race_table_01">
<tr>
<th>着順</th><th>枠番</th><th>馬番</th><th>馬名</th><th>性齢</th>
<th>斤量</th><th>騎手</th><th>タイム</th><th>着差</th>
<th></th><th></th><th></th><th></th><th></th>
<th>通過</th><th>上り</th><th>単勝</th><th>人気</th>
<th>馬体重</th><th></th><th></th><th>調教師</th>
</tr>
<tr>
<td>1</td><td>6</td><td>12</td>
<td><a href="/horse/2020103962/">ステークホルダー</a></td>
<td>牡5</td><td>56</td>
<td><a href="/jockey/05211/">戸崎圭太</a></td>
<td>1:08.2</td><td></td>
<td></td><td></td><td></td><td></td><td></td>
<td>9-9</td><td>33.9</td><td>2.5</td><td>1</td>
<td>468(-4)</td><td></td><td></td><td>[東]斎藤誠</td>
</tr>
<tr>
<td>2</td><td>4</td><td>7</td>
<td><a href="/horse/2021102670/">イサチルシーサイド</a></td>
<td>牡4</td><td>55</td>
<td><a href="/jockey/05212/">木幡初也</a></td>
<td>1:08.2</td><td>ハナ</td>
<td></td><td></td><td></td><td></td><td></td>
<td>1-1</td><td>34.6</td><td>14.9</td><td>6</td>
<td>484(0)</td><td></td><td></td><td>[西]竹内正洋</td>
</tr>
</table>
</body>
</html>
"""


class TestParseRaceResults:
    def test_parses_race_header(self, scraper):
        result = scraper._parse_race_results(SAMPLE_RACE_HTML, "202506010211")
        race = result["race"]
        assert race["race_name"] == "サンライズステークス"
        assert race["distance"] == 1200
        assert race["track_type"] == "芝"
        assert race["weather"] == "曇"
        assert race["track_condition"] == "良"
        assert race["course"] == "中山"
        assert race["race_date"] == "2025-01-06"

    def test_parses_entries(self, scraper):
        result = scraper._parse_race_results(SAMPLE_RACE_HTML, "202506010211")
        entries = result["entries"]
        assert len(entries) == 2

    def test_first_entry_details(self, scraper):
        result = scraper._parse_race_results(SAMPLE_RACE_HTML, "202506010211")
        first = result["entries"][0]
        assert first["horse_name"] == "ステークホルダー"
        assert first["horse_id"] == "2020103962"
        assert first["finish_position"] == 1
        assert first["gender"] == "牡"
        assert first["age"] == 5
        assert first["weight_carried"] == 56.0
        assert first["jockey_name"] == "戸崎圭太"
        assert first["jockey_id"] == "05211"
        assert first["trainer_name"] == "斎藤誠"
        assert first["last_3f"] == 33.9
        assert first["passing_order"] == "9-9"
        assert first["odds"] == 2.5
        assert first["popularity"] == 1
        assert first["horse_weight"] == 468.0
        assert first["weight_change"] == -4.0

    def test_second_entry_running_style(self, scraper):
        """通過順 1-1 → 逃げ"""
        result = scraper._parse_race_results(SAMPLE_RACE_HTML, "202506010211")
        second = result["entries"][1]
        assert second["running_style"] == "逃げ"
        assert second["finish_time"] is not None

    def test_get_race_results_calls_fetch(self, scraper, mock_client):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_RACE_HTML
        mock_resp.encoding = "utf-8"
        mock_resp.status_code = 200
        mock_client.get.return_value = mock_resp

        result = scraper.get_race_results("202506010211")
        assert "race" in result
        mock_client.get.assert_called_once()

    def test_no_result_table_raises_error(self, scraper):
        html = "<html><body>No table here</body></html>"
        with pytest.raises(ScraperError, match="No result table"):
            scraper._parse_race_results(html, "test")


# ------------------------------------------------------------------
# 馬過去成績パース
# ------------------------------------------------------------------

SAMPLE_HORSE_RESULTS_HTML = """
<html>
<body>
<table class="db_h_race_results nk_tb_common">
<tr>
<th>日付</th><th>開催</th><th>天気</th><th>R</th><th>レース名</th><th></th><th>頭数</th>
<th>枠番</th><th>馬番</th><th>オッズ</th><th>人気</th><th>着順</th><th>騎手</th><th>斤量</th>
<th>距離</th><th></th><th>馬場</th><th></th><th>タイム</th><th>着差</th>
<th></th><th></th><th></th><th></th><th>上がり指数</th><th>通過</th><th>ペース</th><th>上り</th><th>馬体重</th>
<th></th><th></th><th>勝ち馬</th><th>賞金</th>
</tr>
<tr>
<td>2025/04/12</td><td>3中山6</td><td>晴</td><td>11</td><td>春雷S(L)</td><td></td><td>16</td>
<td>7</td><td>13</td><td>27.9</td><td>10</td><td>11</td><td>横山琉人</td><td>54</td>
<td>芝1200</td><td></td><td>良</td><td></td><td>1:08.0</td><td>0.4</td>
<td></td><td></td><td></td><td></td><td>99</td><td>12-11</td><td></td><td>33.4</td><td>470(+6)</td>
<td></td><td></td><td>クラスペディア</td><td></td>
</tr>
</table>
</body>
</html>
"""


class TestParseHorseResults:
    def test_parses_past_performances(self, scraper):
        results = scraper._parse_horse_results(SAMPLE_HORSE_RESULTS_HTML)
        assert len(results) == 1

    def test_result_fields(self, scraper):
        results = scraper._parse_horse_results(SAMPLE_HORSE_RESULTS_HTML)
        r = results[0]
        assert r["race_date"] == "2025-04-12"
        assert r["course"] == "中山"
        assert r["distance"] == 1200
        assert r["track_type"] == "芝"
        assert r["track_condition"] == "良"
        assert r["finish_position"] == 11
        assert r["total_runners"] == 16
        assert r["jockey_name"] == "横山琉人"
        assert r["weight_carried"] == 54.0
        assert r["finish_time"] == 68.0
        assert r["odds"] == 27.9
        assert r["popularity"] == 10
        assert r["last_3f"] == 33.4
        assert r["passing_order"] == "12-11"
        assert r["running_style"] == "追込"
        assert r["race_name"] == "春雷S(L)"
        assert r["grade"] == "L"

    def test_empty_html_returns_empty_list(self, scraper):
        results = scraper._parse_horse_results("<html></html>")
        assert results == []


# ------------------------------------------------------------------
# 馬プロフィール
# ------------------------------------------------------------------

SAMPLE_HORSE_PROFILE_HTML = """
<html>
<head><title>ステークホルダー (Stakeholder) | 競走馬データ</title></head>
<body>
<table class="db_prof_table">
<tr><th>生年月日</th><td>2020年3月16日</td></tr>
<tr><th>調教師</th><td>斎藤誠(美浦)</td></tr>
</table>
<table class="blood_table">
<tr><td>ディープインパクト</td><td></td><td></td><td></td></tr>
<tr><td></td><td></td><td>キングカメハメハ</td><td></td></tr>
</table>
</body>
</html>
"""


class TestParseHorseProfile:
    def test_parses_profile(self, scraper):
        profile = scraper._parse_horse_profile(SAMPLE_HORSE_PROFILE_HTML, "2020103962")
        assert profile["horse_name"] == "ステークホルダー"
        assert profile["horse_id"] == "2020103962"
        assert profile["birth_year"] == 2020
        assert profile["trainer_name"] == "斎藤誠"
        assert profile["pedigree_sire"] == ""

    def test_missing_profile_fields(self, scraper):
        profile = scraper._parse_horse_profile("<html><head><title>テスト馬</title></head></html>", "H001")
        assert profile["horse_id"] == "H001"
        assert profile["trainer_name"] == ""


SAMPLE_PEDIGREE_HTML = """
<html><body>
<table class="blood_table">
<tr><td rowspan="16" class="b_ml"><a href="/horse/xxx/">ディープインパクト</a><br/>2002 鹿毛</td>
    <td rowspan="8" class="b_ml"><a href="/horse/xxx/">サンデーサイレンス</a></td>
    <td rowspan="4" class="b_ml"><a href="/horse/xxx/">Halo</a></td>
    <td rowspan="2" class="b_ml"><a href="/horse/xxx/">Hail to Reason</a></td>
    <td class="b_ml"><a href="/horse/xxx/">Turn-to</a></td></tr>
<tr><td class="b_fml"><a href="/horse/xxx/">Nocturnal</a></td></tr>
<tr><td rowspan="2" class="b_fml"><a href="/horse/xxx/">Cosmah</a></td>
    <td class="b_ml"><a href="/horse/xxx/">Cosmic Bomb</a></td></tr>
<tr><td class="b_fml"><a href="/horse/xxx/">Banish Fear</a></td></tr>
<tr><td rowspan="4" class="b_fml"><a href="/horse/xxx/">Wishing Well</a></td>
    <td rowspan="2" class="b_ml"><a href="/horse/xxx/">Understanding</a></td>
    <td class="b_ml"><a href="/horse/xxx/">Promised Land</a></td></tr>
<tr><td class="b_fml"><a href="/horse/xxx/">Pretty Ways</a></td></tr>
<tr><td rowspan="2" class="b_fml"><a href="/horse/xxx/">Mountain Flower</a></td>
    <td class="b_ml"><a href="/horse/xxx/">Edenwold</a></td></tr>
<tr><td class="b_fml"><a href="/horse/xxx/">Naullah</a></td></tr>
<tr><td rowspan="8" class="b_fml"><a href="/horse/xxx/">アルモネアイ</a></td>
    <td rowspan="4" class="b_ml"><a href="/horse/xxx/">キングカメハメハ</a></td>
    <td rowspan="2" class="b_ml"><a href="/horse/xxx/">Kingmambo</a></td>
    <td class="b_ml"><a href="/horse/xxx/">Mr. Prospector</a></td></tr>
<tr><td class="b_fml"><a href="/horse/xxx/">Miesque</a></td></tr>
<tr><td rowspan="2" class="b_fml"><a href="/horse/xxx/">マンファス</a></td>
    <td class="b_ml"><a href="/horse/xxx/">Last Tycoon</a></td></tr>
<tr><td class="b_fml"><a href="/horse/xxx/">Pilgrims Way</a></td></tr>
<tr><td rowspan="4" class="b_fml"><a href="/horse/xxx/">モモタロボー</a></td>
    <td rowspan="2" class="b_ml"><a href="/horse/xxx/">サクラユタカオー</a></td>
    <td class="b_ml"><a href="/horse/xxx/">テスコボーイ</a></td></tr>
<tr><td class="b_fml"><a href="/horse/xxx/">サクラトウコウ</a></td></tr>
<tr><td rowspan="2" class="b_fml"><a href="/horse/xxx/">モトユタカ</a></td>
    <td class="b_ml"><a href="/horse/xxx/">ユタカオー</a></td></tr>
<tr><td class="b_fml"><a href="/horse/xxx/">ミスモトユタカ</a></td></tr>
</table>
</body></html>
"""


class TestParsePedigree:
    def test_parses_sire_and_dam(self, scraper):
        result = scraper._parse_pedigree(SAMPLE_PEDIGREE_HTML)
        assert result["pedigree_sire"] == "ディープインパクト"
        assert result["pedigree_dam"] == "アルモネアイ"
        assert result["pedigree_dam_sire"] == "キングカメハメハ"

    def test_no_blood_table(self, scraper):
        result = scraper._parse_pedigree("<html><body></body></html>")
        assert result == {}


# ------------------------------------------------------------------
# 騎手成績
# ------------------------------------------------------------------

SAMPLE_JOCKEY_HTML = """
<html>
<body>
<h1>戸崎圭太の成績</h1>
<p>通算成績: [32-28-20-40] 120戦32勝</p>
</body>
</html>
"""


class TestParseJockeyStats:
    def test_parses_jockey_stats(self, scraper):
        stats = scraper._parse_jockey_stats(SAMPLE_JOCKEY_HTML, "05211")
        assert stats["jockey_id"] == "05211"
        assert stats["wins"] == 32
        assert stats["total_rides"] == 120
        assert stats["win_rate"] == pytest.approx(32 / 120, abs=0.01)
        assert stats["place_rate"] == pytest.approx(60 / 120, abs=0.01)


# ------------------------------------------------------------------
# レースリスト
# ------------------------------------------------------------------

SAMPLE_RACE_LIST_HTML = """
<html>
<body>
<a href="/race/202506010211/">レース1</a>
<a href="/race/202506010210/">レース2</a>
<a href="/race/202506010211/">重複</a>
<a href="/horse/1234/">馬</a>
</body>
</html>
"""


class TestSearchRaces:
    def test_extracts_race_dates(self, scraper):
        html = """
        <html><body>
        <a href="/race/list/20250601/">6/1</a>
        <a href="/race/list/20250608/">6/8</a>
        <a href="/race/list/20250601/">dup</a>
        </body></html>
        """
        dates = scraper._parse_race_dates(html)
        assert dates == ["20250601", "20250608"]

    def test_extracts_race_ids_from_day(self, scraper):
        ids = scraper._parse_race_ids_from_day(SAMPLE_RACE_LIST_HTML)
        assert ids == ["202506010211", "202506010210"]

    def test_deduplicates_race_ids(self, scraper):
        ids = scraper._parse_race_ids_from_day(SAMPLE_RACE_LIST_HTML)
        assert ids.count("202506010211") == 1


# ------------------------------------------------------------------
# 脚質推定
# ------------------------------------------------------------------

class TestRunningStyleInference:
    def test_front_runner(self):
        assert NetkeibaScraper._infer_running_style("1-1") == "逃げ"

    def test_stalker(self):
        assert NetkeibaScraper._infer_running_style("3-3") == "先行"

    def test_midpack(self):
        assert NetkeibaScraper._infer_running_style("5-6") == "差し"

    def test_closer(self):
        assert NetkeibaScraper._infer_running_style("10-10") == "追込"

    def test_empty(self):
        assert NetkeibaScraper._infer_running_style("") == "差し"


# ------------------------------------------------------------------
# ヘルスチェック
# ------------------------------------------------------------------

class TestHealthCheck:
    def test_healthy(self, scraper, mock_client):
        mock_resp = MagicMock()
        mock_resp.text = "netkeiba database page"
        mock_resp.encoding = "utf-8"
        mock_client.get.return_value = mock_resp
        assert scraper.health_check() is True

    def test_unhealthy(self, scraper, mock_client):
        mock_client.get.side_effect = Exception("connection error")
        assert scraper.health_check() is False
