from lego_deal_scanner.setnum import extract_set_numbers

KNOWN = {"10300", "75192", "21318"}


def test_pulls_set_number_from_title():
    assert extract_set_numbers("LEGO 10300 DeLorean NEU OVP", KNOWN)[0] == "10300"


def test_ignores_bare_year():
    assert "2022" not in extract_set_numbers("Verkaufe Sammlung aus 2022, top Zustand", KNOWN)


def test_keeps_year_like_number_with_lego_context():
    assert "1989" in extract_set_numbers("LEGO 1989 Batwing seltenes Set", set())


def test_known_number_wins_ordering():
    nums = extract_set_numbers("Konvolut mit 999999 Steinen, dabei LEGO 75192", KNOWN)
    assert nums[0] == "75192"


def test_strips_dash_one_suffix():
    assert "21318" in extract_set_numbers("LEGO 21318-1 Baumhaus", KNOWN)
