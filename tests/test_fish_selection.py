import pytest
from zhenxun.plugins.zhenxun_plugin_fishing.backpack import (
    FishSelection,
    is_likely_misfire,
    parse_fish_selection,
)


class TestParseFishSelection:
    def test_all_keyword_quanbu(self):
        sel = parse_fish_selection("全部")
        assert sel.select_all is True
        assert sel.is_empty() is False

    def test_all_keyword_all(self):
        sel = parse_fish_selection("all")
        assert sel.select_all is True

    def test_all_keyword_suoyou(self):
        sel = parse_fish_selection("所有")
        assert sel.select_all is True

    def test_single_rarity_letter_sr(self):
        sel = parse_fish_selection("SR")
        assert sel.rarity_letters == ["SR"]
        assert sel.rarity_precise == []
        assert sel.numeric_ids == []

    def test_single_rarity_letter_n(self):
        sel = parse_fish_selection("N")
        assert sel.rarity_letters == ["N"]

    def test_single_rarity_letter_case_insensitive(self):
        sel = parse_fish_selection("sr")
        assert sel.rarity_letters == ["SR"]

    def test_wildcard_rarity_3(self):
        sel = parse_fish_selection("**3")
        assert sel.rarity_precise == ["SR"]
        assert sel.rarity_letters == []

    def test_wildcard_rarity_1(self):
        sel = parse_fish_selection("**1")
        assert sel.rarity_precise == ["N"]

    def test_wildcard_rarity_6(self):
        sel = parse_fish_selection("**6")
        assert sel.rarity_precise == ["UTR"]

    def test_wildcard_rarity_invalid_0(self):
        sel = parse_fish_selection("**0")
        assert sel.rarity_precise == []
        assert sel.is_empty() is True

    def test_wildcard_rarity_invalid_7(self):
        sel = parse_fish_selection("**7")
        assert sel.rarity_precise == []
        assert sel.is_empty() is True

    def test_wildcard_rarity_non_digit(self):
        sel = parse_fish_selection("**abc")
        assert sel.rarity_precise == []
        assert sel.is_empty() is True

    def test_single_numeric_id(self):
        sel = parse_fish_selection("111")
        assert sel.numeric_ids == ["111"]
        assert sel.rarity_letters == []
        assert sel.rarity_precise == []

    def test_batch_ids_comma(self):
        sel = parse_fish_selection("111,112,113")
        assert sel.numeric_ids == ["111", "112", "113"]

    def test_batch_ids_semicolon(self):
        sel = parse_fish_selection("111;112")
        assert sel.numeric_ids == ["111", "112"]

    def test_batch_ids_chinese_comma(self):
        sel = parse_fish_selection("111，112")
        assert sel.numeric_ids == ["111", "112"]

    def test_batch_ids_chinese_semicolon(self):
        sel = parse_fish_selection("111；112")
        assert sel.numeric_ids == ["111", "112"]

    def test_batch_ids_space(self):
        sel = parse_fish_selection("111 112")
        assert sel.numeric_ids == ["111", "112"]

    def test_mixed_wildcard_and_id(self):
        sel = parse_fish_selection("**3,124")
        assert sel.rarity_precise == ["SR"]
        assert sel.numeric_ids == ["124"]

    def test_mixed_rarity_letter_and_id(self):
        sel = parse_fish_selection("SR,111")
        assert sel.rarity_letters == ["SR"]
        assert sel.numeric_ids == ["111"]

    def test_mixed_rarity_letter_and_wildcard(self):
        sel = parse_fish_selection("SR,**5")
        assert sel.rarity_letters == ["SR"]
        assert sel.rarity_precise == ["UR"]

    def test_multiple_rarities(self):
        sel = parse_fish_selection("SR,SSR")
        assert sel.rarity_letters == ["SR", "SSR"]

    def test_multiple_wildcards(self):
        sel = parse_fish_selection("**3,**5")
        assert sel.rarity_precise == ["SR", "UR"]

    def test_all_rarities_method(self):
        sel = parse_fish_selection("SR,**3")
        assert sel.all_rarities() == ["SR"]

    def test_all_rarities_dedup(self):
        sel = FishSelection(rarity_letters=["SR"], rarity_precise=["SR"])
        assert sel.all_rarities() == ["SR"]

    def test_is_empty_true(self):
        sel = FishSelection()
        assert sel.is_empty() is True

    def test_is_empty_false_with_rarity(self):
        sel = FishSelection(rarity_letters=["SR"])
        assert sel.is_empty() is False

    def test_is_empty_false_with_id(self):
        sel = FishSelection(numeric_ids=["111"])
        assert sel.is_empty() is False

    def test_is_empty_false_with_select_all(self):
        sel = FishSelection(select_all=True)
        assert sel.is_empty() is False

    def test_empty_input(self):
        sel = parse_fish_selection("")
        assert sel.is_empty() is True

    def test_whitespace_only_input(self):
        sel = parse_fish_selection("   ")
        assert sel.is_empty() is True

    def test_all_in_mixed_input(self):
        sel = parse_fish_selection("全部,SR")
        assert sel.select_all is True

    def test_strip_input(self):
        sel = parse_fish_selection("  SR  ")
        assert sel.rarity_letters == ["SR"]

    def test_sell_fish_rarity_letter_sr_and_below_semantic(self):
        sel = parse_fish_selection("SR")
        assert sel.rarity_letters == ["SR"]
        assert sel.rarity_precise == []

    def test_sell_fish_wildcard_precise_semantic(self):
        sel = parse_fish_selection("**3")
        assert sel.rarity_precise == ["SR"]
        assert sel.rarity_letters == []

    def test_complex_mixed(self):
        sel = parse_fish_selection("SR,**5,111,112")
        assert sel.rarity_letters == ["SR"]
        assert sel.rarity_precise == ["UR"]
        assert sel.numeric_ids == ["111", "112"]

    def test_all_rarities_complex(self):
        sel = parse_fish_selection("SR,**3,SSR")
        assert sel.all_rarities() == ["SR", "SSR"]


class TestIsLikelyMisfire:
    def test_long_chinese_only_text_is_misfire(self):
        assert is_likely_misfire("道具组合是这个游戏充值服务爽点") is True

    def test_short_chinese_not_in_keywords_is_misfire(self):
        assert is_likely_misfire("道具") is True

    def test_empty_input_not_misfire(self):
        assert is_likely_misfire("") is False

    def test_whitespace_only_not_misfire(self):
        assert is_likely_misfire("   ") is False

    def test_no_chinese_not_misfire(self):
        assert is_likely_misfire("SR") is False

    def test_numeric_id_not_misfire(self):
        assert is_likely_misfire("111") is False

    def test_wildcard_rarity_not_misfire(self):
        assert is_likely_misfire("**3") is False

    def test_all_keyword_quanbu_not_misfire(self):
        assert is_likely_misfire("全部") is False

    def test_all_keyword_suoyou_not_misfire(self):
        assert is_likely_misfire("所有") is False

    def test_all_keyword_all_not_misfire(self):
        assert is_likely_misfire("all") is False

    def test_mixed_valid_selector_with_chinese_not_misfire(self):
        assert is_likely_misfire("SR,道具") is False

    def test_mixed_numeric_with_chinese_not_misfire(self):
        assert is_likely_misfire("111 鱼") is False

    def test_mixed_all_keyword_with_chinese_not_misfire(self):
        assert is_likely_misfire("全部,其他") is False

    def test_chinese_with_invalid_wildcard_is_misfire(self):
        assert is_likely_misfire("**道具") is True

    def test_strips_whitespace(self):
        assert is_likely_misfire("  道具组合  ") is True

    def test_invalid_rarity_letter_with_chinese_is_misfire(self):
        assert is_likely_misfire("XX鱼") is True
