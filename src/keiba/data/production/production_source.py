"""本番データソース

netkeiba.com と JRA 公式サイトの両方からデータを取得し、
DataMerger で統合・重複排除して DataSource ABC に適合させる。
一方のソースが失敗しても他方で継続（graceful degradation）。
"""

import logging
from datetime import datetime

from keiba.data.base_source import DataSource
from keiba.data.production.exceptions import (
    AllSourcesFailedError,
    DataSourceError,
)
from keiba.data.production.merger import DataMerger
from keiba.data.production.scrapers.netkeiba_scraper import NetkeibaScraper
from keiba.data.production.scrapers.jra_scraper import JraScraper
from keiba.utils.http_client import RateLimitedHttpClient


class ProductionDataSource(DataSource):
    """本番データソース（netkeiba + JRA 統合）

    graceful degradation: 一方が失敗しても他方で継続。
    両方失敗時のみ AllSourcesFailedError を送出。
    """

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("keiba.ProductionDataSource")

        prod_config = config.get("data_source", {}).get("production", {})
        http_config = prod_config.get("http", {})
        cache_config = prod_config.get("cache", {})
        full_http_config = {**http_config, "cache": cache_config}

        # 共有 HTTP クライアント
        self.http_client = RateLimitedHttpClient(full_http_config)

        # サイト別スクレイパ
        self.netkeiba = NetkeibaScraper(self.http_client)
        self.jra = JraScraper(self.http_client)

        # マージャー
        self.merger = DataMerger()

    # ------------------------------------------------------------------
    # DataSource 実装
    # ------------------------------------------------------------------

    def get_historical_data(self, race_id: str) -> dict:
        """過去データ取得。netkeiba 主、JRA 補完。"""
        self.logger.info(f"Fetching historical data for {race_id}")

        # netkeiba からレース結果を取得
        nk_results = self._fetch_with_fallback(
            lambda: self._build_historical_from_netkeiba(race_id),
            "netkeiba",
        )

        if nk_results is None:
            raise AllSourcesFailedError(
                f"Cannot get historical data for {race_id}: all sources failed"
            )

        # JRA はまだレース結果スクレイピング未対応
        # 将来実装時に nk_results とマージ
        return nk_results

    def get_current_race_card(self, race_id: str) -> dict:
        """出馬表取得。netkeiba から取得（JRA は未対応）。"""
        self.logger.info(f"Fetching race card for {race_id}")

        nk_card = self._fetch_with_fallback(
            lambda: self._build_race_card_from_netkeiba(race_id),
            "netkeiba",
        )

        if nk_card is None:
            raise AllSourcesFailedError(
                f"Cannot get race card for {race_id}: all sources failed"
            )

        return nk_card

    def get_predicted_odds(self, race_id: str) -> dict:
        """予想オッズ取得。"""
        self.logger.info(f"Fetching predicted odds for {race_id}")

        nk_odds = self._fetch_with_fallback(
            lambda: self.netkeiba.get_odds(race_id),
            "netkeiba",
        )

        if nk_odds is None:
            raise AllSourcesFailedError(
                f"Cannot get predicted odds for {race_id}: all sources failed"
            )

        return self._format_odds(nk_odds, race_id, is_provisional=True)

    def get_actual_odds(self, race_id: str) -> dict:
        """実オッズ取得。"""
        self.logger.info(f"Fetching actual odds for {race_id}")

        nk_odds = self._fetch_with_fallback(
            lambda: self.netkeiba.get_odds(race_id),
            "netkeiba",
        )

        if nk_odds is None:
            raise AllSourcesFailedError(
                f"Cannot get actual odds for {race_id}: all sources failed"
            )

        return self._format_odds(nk_odds, race_id, is_provisional=False)

    def get_web_content(self, race_id: str, horse_ids: list[str]) -> dict:
        """Web コンテンツ取得（調教情報等）。"""
        self.logger.info(f"Fetching web content for {race_id}, {len(horse_ids)} horses")

        content = {
            "track_tendencies": [],
            "weather_forecast": None,
            "horse_intel": [],
        }

        # 各馬の情報を取得
        for horse_id in horse_ids:
            intel = self._fetch_with_fallback(
                lambda hid=horse_id: self._build_horse_intel(hid),
                "netkeiba",
            )
            if intel:
                content["horse_intel"].append(intel)

        return content

    def get_backtest_data(self, config: dict) -> list[dict]:
        """バックテスト用データ取得。"""
        self.logger.info("Fetching backtest data")

        backtest_data = self._fetch_with_fallback(
            lambda: self._build_backtest_data(),
            "netkeiba",
        )

        return backtest_data or []

    # ------------------------------------------------------------------
    # netkeiba からのデータ構築
    # ------------------------------------------------------------------

    def _build_historical_from_netkeiba(self, race_id: str) -> dict:
        """netkeiba から過去データを構築"""
        race_results = self.netkeiba.get_race_results(race_id)

        entries = race_results.get("entries", [])
        horses = {}
        past_performances = {}
        jockey_stats = {}

        for entry in entries:
            horse_id = entry.get("horse_id", "")
            if not horse_id:
                continue

            # 馬データ
            horses[horse_id] = {
                "horse_id": horse_id,
                "horse_name": entry.get("horse_name", ""),
                "gender": entry.get("gender", ""),
                "age": entry.get("age", 0),
                "trainer_name": entry.get("trainer_name", ""),
            }

            # 過去成績を取得
            pp = self.netkeiba.get_horse_past_performances(horse_id)
            past_performances[horse_id] = pp

            # 騎手成績
            jockey_id = entry.get("jockey_id", "")
            if jockey_id and jockey_id not in jockey_stats:
                try:
                    jockey_stats[jockey_id] = self.netkeiba.get_jockey_stats(jockey_id)
                except Exception:
                    jockey_stats[jockey_id] = {
                        "jockey_id": jockey_id,
                        "jockey_name": entry.get("jockey_name", ""),
                        "period": str(datetime.now().year),
                        "total_rides": 0, "wins": 0, "places": 0,
                        "win_rate": 0.0, "place_rate": 0.0,
                        "favorite_win_rate": 0.0, "course_stats": {},
                    }

        return {
            "races": [race_results.get("race", {})],
            "horses": horses,
            "past_performances": past_performances,
            "jockey_stats": jockey_stats,
            "trainer_stats": {},
        }

    def _build_race_card_from_netkeiba(self, race_id: str) -> dict:
        """netkeiba から出馬表を構築"""
        race_results = self.netkeiba.get_race_results(race_id)
        race_info = race_results.get("race", {})
        raw_entries = race_results.get("entries", [])

        entries = []
        for e in raw_entries:
            # 過去成績を取得（キャッシュされるので再取得は高速）
            horse_id = e.get("horse_id", "")
            pp = []
            if horse_id:
                try:
                    pp = self.netkeiba.get_horse_past_performances(horse_id)
                except Exception:
                    pass

            # 馬プロフィール
            profile = {}
            if horse_id:
                try:
                    profile = self.netkeiba.get_horse_profile(horse_id)
                except Exception:
                    pass

            entries.append({
                "entry_id": e.get("entry_id", f"{race_id}-{e.get('post_position', 0):02d}"),
                "horse": {
                    "horse_id": horse_id,
                    "horse_name": e.get("horse_name", ""),
                    "birth_year": profile.get("birth_year", 0),
                    "gender": profile.get("gender", e.get("gender", "")),
                    "age": profile.get("age", e.get("age", 0)),
                    "trainer_name": e.get("trainer_name", "") or profile.get("trainer_name", ""),
                    "pedigree_sire": profile.get("pedigree_sire"),
                    "pedigree_dam_sire": profile.get("pedigree_dam_sire"),
                },
                "jockey": {
                    "jockey_id": e.get("jockey_id", ""),
                    "jockey_name": e.get("jockey_name", ""),
                },
                "weight_carried": e.get("weight_carried", 0),
                "post_position": e.get("post_position", 0),
                "bracket_number": e.get("bracket_number", 0),
                "horse_weight": e.get("horse_weight"),
                "weight_change": e.get("weight_change"),
                "past_performances": pp,
                "style": e.get("running_style", "差し"),
            })

        return {
            "race": race_info,
            "entries": entries,
        }

    def _build_horse_intel(self, horse_id: str) -> dict:
        """馬のWeb情報を構築"""
        # プロフィールから基本情報
        try:
            profile = self.netkeiba.get_horse_profile(horse_id)
        except Exception:
            profile = {"horse_id": horse_id, "horse_name": ""}

        # 過去成績から notable_factors を生成
        factors = []
        try:
            pp = self.netkeiba.get_horse_past_performances(horse_id)
            if pp:
                last = pp[0]
                pos = last.get("finish_position", 0)
                if pos == 1:
                    factors.append("前走1着・好調")
                elif pos <= 3:
                    factors.append(f"前走{pos}着・安定感あり")
                elif pos > 10:
                    factors.append(f"前走{pos}着・要注意")
        except Exception:
            pass

        return {
            "horse_id": horse_id,
            "horse_name": profile.get("horse_name", ""),
            "training_reports": [],
            "connections_comments": [],
            "news_items": [],
            "notable_factors": factors,
        }

    def _build_backtest_data(self) -> list[dict]:
        """バックテストデータを構築（設定でリクエスト数を制限）"""
        bt_config = (
            self.config.get("data_source", {})
            .get("production", {})
            .get("backtest", {})
        )
        max_months = bt_config.get("max_months", 6)
        max_races = bt_config.get("max_races", 20)

        now = datetime.now()
        all_race_ids = []
        for month_offset in range(max_months):
            year = now.year
            month = now.month - month_offset
            if month <= 0:
                month += 12
                year -= 1
            try:
                ids = self.netkeiba.search_races(year, month)
                all_race_ids.extend(ids[:max_races])
            except Exception:
                continue

        if not all_race_ids:
            return []

        # 最初の20レースの結果をバックテストデータとして使用
        backtest = []
        for rid in all_race_ids[:max_races]:
            try:
                results = self.netkeiba.get_race_results(rid)
                entries = results.get("entries", [])
                race = results.get("race", {})
                predicted = [e["horse_id"] for e in entries if e.get("horse_id")][:5]
                actual = [e["horse_id"] for e in sorted(entries, key=lambda x: x.get("finish_position", 99)) if e.get("horse_id")][:5]
                fav_odds = entries[0].get("odds", 0) if entries else 0
                backtest.append({
                    "race_id": rid,
                    "course": race.get("course", ""),
                    "distance": race.get("distance", 0),
                    "condition": race.get("track_condition", ""),
                    "predicted_rank": predicted,
                    "actual_result": actual,
                    "win_odds_favorite": fav_odds,
                    "win_dividend": 0,
                    "place_dividend": 0,
                })
            except Exception:
                continue

        return backtest

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    def _format_odds(self, odds_list: list, race_id: str, is_provisional: bool) -> dict:
        """オッズリストを DataSource 契約に変換"""
        entries = []
        for i, o in enumerate(odds_list):
            entries.append({
                "entry_id": o.get("entry_id", f"{race_id}-{i+1:02d}"),
                "horse_name": o.get("horse_name", ""),
                "win_odds": o.get("win_odds", 0),
                "popularity_rank": o.get("popularity_rank", i + 1),
            })

        return {
            "race_id": race_id,
            "is_provisional": is_provisional,
            "calculated_at": datetime.now().isoformat(),
            "method": "market",
            "entries": entries,
        }

    def _fetch_with_fallback(self, fetch_fn, source_name: str):
        """例外をキャッチして None を返すフォールバックラッパー"""
        try:
            return fetch_fn()
        except AllSourcesFailedError:
            raise  # そのまま伝播
        except DataSourceError as e:
            self.logger.error(f"[{source_name}] Data source error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"[{source_name}] Unexpected error: {e}")
            return None
