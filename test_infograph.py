import pathlib
from orochi_infograph import core

SAMPLE_MESSAGE = """◆FiNANCiE開運オロチトークン現在情報（2026年06月16日 06:00時点）
・オープン516日目
・メンバー数 22,725人（前日比 -9人）
・トークン価格 11.9909円（前日比 -0.0037円）
・トークン在庫 50,018枚（前日比 +8枚）
#CNPオロチ #開運オロチ..."""


def test_parse_metrics():
    metrics, title, title_timestamp = core.parse_metrics(
        SAMPLE_MESSAGE, target_keys=core.DEFAULT_TARGET_KEYS
    )

    assert title == "FiNANCiE開運オロチトークン現在情報"
    assert title_timestamp == "2026年06月16日 06:00時点"
    assert metrics["メンバー数"]["val"] == "22,725"
    assert metrics["メンバー数"]["unit"] == "人"
    assert metrics["メンバー数"]["diff"] == "-9人"
    assert metrics["トークン価格"]["val"] == "11.9909"
    assert metrics["トークン在庫"]["diff"] == "+8枚"


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
