"""サンプルWeb調査コンテンツ"""

from datetime import datetime

SAMPLE_WEB_CONTENT = {
    "race_id": "20260607-Tokyo-11",
    "researched_at": datetime(2026, 6, 6, 18, 0, 0).isoformat(),
    "track_tendencies": [
        "東京芝2400mは内枠がやや有利な傾向",
        "前走好位差しの馬が好走例が多い",
        "逃げ馬はスローペースになれば残せる可能性あり",
    ],
    "weather_forecast": "当日は晴れ予報。馬場状態は良見込み。",
    "horse_intel": [
        {
            "horse_id": "H001",
            "horse_name": "サンライズインパクト",
            "training_reports": ["美浦坂路で好時計をマーク", "追い切り動き軽快"],
            "connections_comments": ["田中調教師：距離延長は問題ないとのこと", "武豊騎手：状態は前走以上"],
            "news_items": [
                {"source": "競馬ブック", "title": "ダービー最終追い切り好調", "content": "サンライズインパクトが美浦坂路で12秒0の好時計", "relevance": 0.9, "date": "2026-06-05"},
            ],
            "notable_factors": ["3連勝中で勢いがある", "距離適性は未知数だが血統的には問題なし"],
        },
        {
            "horse_id": "H002",
            "horse_name": "ミッドナイトブレイド",
            "training_reports": ["栗東CWコースで併せ馬で先着", "最終追いは軽め"],
            "connections_comments": ["佐藤調教師：前走の反応は良かった", "川田騎手：もう一つ上積みがある"],
            "news_items": [
                {"source": "スポーツニッポン", "title": "順調にダービーへ", "content": "青葉賞2着から順調にステップアップ", "relevance": 0.7, "date": "2026-06-04"},
            ],
            "notable_factors": ["安定した成績", "2400mの実績あり"],
        },
        {
            "horse_id": "H003",
            "horse_name": "ゴールデンアロー",
            "training_reports": ["美浦南Wで強めに追われ好反応"],
            "connections_comments": ["鈴木調教師：GI経験はプラスになる"],
            "news_items": [],
            "notable_factors": ["GI出走経験あり", "先行して粘り込むタイプ"],
        },
        {
            "horse_id": "H004",
            "horse_name": "ロイヤルストライク",
            "training_reports": ["栗東坂路で数字向上", "馬体重増加傾向"],
            "connections_comments": ["高橋調教師：馬体が成長している", "デムーロ騎手：末脚は一流"],
            "news_items": [
                {"source": "日刊スポーツ", "title": "大駆け期待のロイヤルストライク", "content": "上がり最速の末脚に注目", "relevance": 0.6, "date": "2026-06-03"},
            ],
            "notable_factors": ["上がり3ハロンの速さは出走馬中トップクラス", "馬体重が増加傾向"],
        },
        {
            "horse_id": "H005",
            "horse_name": "ウィンドヴォイス",
            "training_reports": ["美浦南Wで時計を出している", "動き良好"],
            "connections_comments": ["伊藤調教師：牝馬ですが力はあります", "ルメール騎手：距離は持つ"],
            "news_items": [
                {"source": "デイリー Sport", "title": "牝馬のダービー制覇なるか", "content": "フローラS勝ち馬がダービーに挑戦", "relevance": 0.8, "date": "2026-06-05"},
            ],
            "notable_factors": ["フローラS勝利で勢いあり", "牝馬のダービーは過去好走例が少ない点に注意"],
        },
        {
            "horse_id": "H006",
            "horse_name": "サンダーボルトキッド",
            "training_reports": ["栗東CWで普通め", "最終追いは軽め"],
            "connections_comments": ["山田調教師：距離が少し長いかもしれない"],
            "news_items": [],
            "notable_factors": ["馬体重が急増（+8kg）", "距離への不安あり"],
        },
        {
            "horse_id": "H007",
            "horse_name": "フロストナイト",
            "training_reports": ["美浦坂路で好時計", "動き良し"],
            "connections_comments": ["中村調教師：最後の一脚に期待"],
            "news_items": [],
            "notable_factors": ["追込の一発に期待", "馬体重減少が気掛かり（-6kg）"],
        },
        {
            "horse_id": "H008",
            "horse_name": "ムーンライトダンス",
            "training_reports": ["美浦南Wで普通め", "状態良好"],
            "connections_comments": ["小林調教師：展開が向けば"],
            "news_items": [],
            "notable_factors": ["後方から追込むスタイル", "東京2400mは展開次第"],
        },
        {
            "horse_id": "H009",
            "horse_name": "ブレイブハート",
            "training_reports": ["美浦坂路で軽め調整"],
            "connections_comments": ["加藤調教師：叩き上げで上積みある"],
            "news_items": [],
            "notable_factors": ["キャリア豊富", "重賞実績がやや物足りない"],
        },
        {
            "horse_id": "H010",
            "horse_name": "スカイブルーグラス",
            "training_reports": ["栗東CWで時計良くない"],
            "connections_comments": ["斎藤調教師：少し疲れがあるかも"],
            "news_items": [
                {"source": "競馬ブック", "title": "体調にやや不安", "content": "スカイブルーグラスが馬体重減少、調教でも一分を要す", "relevance": 0.7, "date": "2026-06-06"},
            ],
            "notable_factors": ["馬体重大幅減（-8kg）", "調教時計が良くない", "体調に不安要素"],
        },
    ],
}
