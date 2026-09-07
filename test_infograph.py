import pathlib
from orochi_infograph import core

SAMPLE_MESSAGE = """◆FiNANCiE開運オロチトークン現在情報（2026年09月08日 06:00時点）
・オープン600日目
・メンバー数 22,645人（前日比 +2人）
・トークン価格 9.0969円（前日比 +0.0115円）
・24時間の売買 110枚（買い 73枚／売り 37枚）
・時価総額 26,381,054円
#CNPオロチ #開運オロチ..."""


def test_parse_metrics():
    metrics, title, title_timestamp = core.parse_metrics(
        SAMPLE_MESSAGE, target_keys=core.DEFAULT_TARGET_KEYS
    )

    assert title == "FiNANCiE開運オロチトークン現在情報"
    assert title_timestamp == "2026年09月08日 06:00時点"
    assert metrics["メンバー数"]["val"] == "22,645"
    assert metrics["メンバー数"]["unit"] == "人"
    assert metrics["メンバー数"]["diff"] == "+2人"
    assert metrics["メンバー数"]["label"] == "前日比"
    assert metrics["トークン価格"]["val"] == "9.0969"
    assert metrics["24時間の売買"]["val"] == "110"
    assert metrics["24時間の売買"]["breakdown"] == [("買い", "73枚"), ("売り", "37枚")]


def test_parse_metrics_weekly_label_and_plain_line():
    weekly = """◆FiNANCiE開運オロチトークン週報（2026年09月05日）
・メンバー数 22,643人（前週比 +15人）
・トークン価格 9.0854円（前週比 -0.2247円）
・今週の売買 4,249枚（買い 1,775枚／売り 2,473枚）
・時価総額 26,371,056円
#CNPオロチ #開運オロチ"""
    metrics, _, _ = core.parse_metrics(weekly)

    # 週報では差分ラベルが「前週比」になる（画像側もこれを描画に使う）
    assert metrics["メンバー数"]["label"] == "前週比"
    assert metrics["今週の売買"]["breakdown"] == [("買い", "1,775枚"), ("売り", "2,473枚")]
    # 括弧のない行も拾える
    assert metrics["時価総額"]["val"] == "26,371,056"
    assert "diff" not in metrics["時価総額"]


def test_build_image():
    metrics, title, title_timestamp = core.parse_metrics(
        SAMPLE_MESSAGE, target_keys=core.DEFAULT_TARGET_KEYS
    )
    buf = core.build_image(metrics, title, title_timestamp)
    assert buf is not None
    data = buf.getvalue()
    assert data.startswith(b"\x89PNG")

    out_path = pathlib.Path("test_output_infograph.png")
    out_path.write_bytes(data)
    assert out_path.exists()
    out_path.unlink()
