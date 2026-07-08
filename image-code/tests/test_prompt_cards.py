"""卡↔code 逐字核对（单一事实源协议的自动闸，B-3 门禁）。

image-prompt 各卡的 ```text 物化块 = 唯一事实源；code 里的常量是硬编码副本。
任何一边漂移 → 本测试红（替代历轮手跑的程序化核对）。卡目录不存在（如仅部署
image-code 的环境）则 skip。
"""

import re
from pathlib import Path

import pytest

from design_hub.application.listing import prompt_composer as pc

_PROMPT_ROOT = Path(__file__).resolve().parents[2] / "image-prompt"

pytestmark = pytest.mark.skipif(
    not _PROMPT_ROOT.is_dir(), reason="image-prompt 卡目录不在本环境（仅全仓 checkout 可核）"
)


def _blocks(rel: str) -> list[str]:
    text = (_PROMPT_ROOT / rel).read_text(encoding="utf-8")
    return re.findall(r"```text\n(.*?)\n```", text, re.S)


@pytest.mark.parametrize(
    ("folder", "const"),
    [
        ("food", "_FOOD_FIDELITY"),
        ("fashion", "_FASHION_FIDELITY"),
        ("beauty", "_BEAUTY_FIDELITY"),
        ("shoes", "_SHOES_FIDELITY"),
        ("digital", "_DIGITAL_FIDELITY"),
    ],
)
def test_category_fidelity_matches_card(folder: str, const: str) -> None:
    # 卡↔code 逐字闸（ISSUE-0060 扩 5 品类）：常量必等品类卡 ```text 块[0]。
    assert getattr(pc, const) == _blocks(f"category-cards/{folder}/通用.md")[0]


@pytest.mark.parametrize(
    ("card", "const"),
    [
        ("image-type-cards/白底.md", "_TYPE_WHITE_BG"),
        ("image-type-cards/场景.md", "_TYPE_SCENE"),
    ],
)
def test_image_type_blocks_match_cards(card: str, const: str) -> None:
    assert getattr(pc, const) == _blocks(card)[0]


def test_selling_blocks_match_card() -> None:
    blocks = _blocks("image-type-cards/卖点.md")
    assert pc._TYPE_SELLING == blocks[0]
    assert pc._TYPE_SELLING_TEXT_TPL == blocks[1]  # 模板：静态部分逐字（含 {overlay_texts} 槽字面）


def test_clone_blocks_match_card() -> None:
    blocks = _blocks("clone-mode-cards/复刻.md")
    assert pc._CLONE_REF_STYLE == blocks[0]
    assert pc._CLONE_FULL == blocks[1]


def test_edit_blocks_match_card() -> None:
    blocks = _blocks("edit-mode-cards/编辑.md")
    assert pc._EDIT_DELTA == blocks[0]
    assert pc._EDIT_FULL == blocks[1]


def test_selling_overlay_fill_format() -> None:
    """模板槽填充按卡内格式：全角引号包裹、顿号分隔。"""
    out = pc.ImageTypeRegistry().block("卖点", ("高山七彩花生", "原生态种植"))
    assert "「高山七彩花生」、「原生态种植」" in out
