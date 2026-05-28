from design_hub.domain.enums import Style

_COLOR: dict[Style, str] = {
    Style.LUXURY: "黑金 #1a1a1a + 暖金 #c9a86a + 深红 #6b2020",
    Style.NORDIC: "鼠尾草绿 #b2c2a8 + 牛皮纸 #d4c4a0 + 奶油白 #f5f0e6",
    Style.GUOCHAO: "中国红 #E60012 + 鎏金 #d4af37 + 墨黑 #1c1c1c",
    Style.TECH: "深空蓝 #0a1428 + 电光紫 #8b5cf6 + 冷银 #c0c8d0",
    Style.FRESH: "薄荷绿 #a8d8c0 + 浅木色 #d9c9b0 + 白 #ffffff",
    Style.SPORT: "电光橙 #ff6b1a + 冷灰 #4a5057 + 黑 #1a1a1a",
    Style.FESTIVE: "正红 #c8102e + 金 #f0c419 + 暖白 #fff8e7",
}


class ColorLibrary:
    """词库 A：风格 → 色卡（HEX/具名色）。"""

    def get(self, style: Style) -> str:
        if style not in _COLOR:
            raise KeyError(f"No color card for style {style}")
        return _COLOR[style]
