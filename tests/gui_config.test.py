import gui_config


def test_window_dimensions_are_positive():
    assert gui_config.WINDOW_WIDTH > 0
    assert gui_config.WINDOW_HEIGHT > 0
    assert gui_config.WINDOW_MIN_WIDTH > 0
    assert gui_config.WINDOW_MIN_HEIGHT > 0


def test_colors_dict_has_all_keys():
    expected = {"BG", "PANEL", "ACCENT", "FG", "FG_DIM", "BTN_BG", "BTN_ACT", "START", "START_FG", "START_HO"}
    assert expected == set(gui_config.COLORS.keys())


def test_fonts_are_tuples():
    fonts = [
        gui_config.FONT_DEFAULT,
        gui_config.FONT_LABEL,
        gui_config.FONT_SMALL,
        gui_config.FONT_MONO,
        gui_config.FONT_BUTTON_LARGE,
        gui_config.FONT_LISTBOX,
    ]
    for font in fonts:
        assert isinstance(font, tuple)
