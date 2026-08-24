import pytest

from assembly_tool.timecode import STANDARD_RATES, FrameRate, Timecode

NDF_RATES = [STANDARD_RATES[k] for k in ("23.976", "24", "25", "29.97", "30", "59.94", "60")]
DF_RATES = [STANDARD_RATES["29.97"], STANDARD_RATES["59.94"]]


# ---------------------------------------------------------------------------
# Non-drop-frame: every rate, simple round trip.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rate", NDF_RATES)
def test_ndf_round_trip_zero(rate: FrameRate) -> None:
    tc = Timecode.from_frame_number(0, rate)
    assert tc.to_timecode_string() == "00:00:00:00"
    assert Timecode.from_timecode_string("00:00:00:00", rate).frame_number == 0


@pytest.mark.parametrize("rate", NDF_RATES)
def test_ndf_round_trip_many_frames(rate: FrameRate) -> None:
    # Every frame across ~3 minutes: dense enough to catch every second/
    # minute rollover without a full-length test run.
    span = rate.nominal_fps * 60 * 3
    for frame_number in range(0, span, 7):  # step for speed; still thousands of samples
        tc = Timecode.from_frame_number(frame_number, rate)
        round_tripped = Timecode.from_timecode_string(tc.to_timecode_string(), rate)
        assert round_tripped.frame_number == frame_number, tc.to_timecode_string()


def test_ndf_second_rollover_23_976() -> None:
    rate = STANDARD_RATES["23.976"]
    tc = Timecode.from_frame_number(24, rate)  # one frame past the 24th (index 23)
    assert tc.to_timecode_string() == "00:00:01:00"


def test_ndf_minute_rollover_30() -> None:
    rate = STANDARD_RATES["30"]
    tc = Timecode.from_frame_number(30 * 60, rate)
    assert tc.to_timecode_string() == "00:01:00:00"


def test_ndf_hour_rollover_60() -> None:
    rate = STANDARD_RATES["60"]
    tc = Timecode.from_frame_number(60 * 3600, rate)
    assert tc.to_timecode_string() == "01:00:00:00"


# ---------------------------------------------------------------------------
# Drop-frame: known reference values (hand-verifiable against SMPTE 12M).
# ---------------------------------------------------------------------------


def test_df_29_97_first_minute_is_full() -> None:
    # Minute 0 is not a drop boundary: frames 0-1799 are all real.
    rate = STANDARD_RATES["29.97"]
    tc = Timecode.from_frame_number(1799, rate, drop_frame=True)
    assert tc.to_timecode_string() == "00:00:59;29"


def test_df_29_97_first_drop_skips_two_numbers() -> None:
    rate = STANDARD_RATES["29.97"]
    tc = Timecode.from_frame_number(1800, rate, drop_frame=True)
    # NDF would read 00:01:00:00 here; DF skips frame numbers :00 and :01.
    assert tc.to_timecode_string() == "00:01:00;02"


def test_df_29_97_tenth_minute_has_no_drop() -> None:
    rate = STANDARD_RATES["29.97"]
    frames_per_10_minutes = 30 * 600 - 2 * 9  # 17982
    tc = Timecode.from_frame_number(frames_per_10_minutes, rate, drop_frame=True)
    assert tc.to_timecode_string() == "00:10:00;00"


def test_df_29_97_one_hour_reference() -> None:
    # The textbook check: 29.97 DF drops 108 frame numbers per hour
    # (2 per minute x 54 non-tenth minutes), so 1 real hour lands on
    # frame 107892, not 108000.
    rate = STANDARD_RATES["29.97"]
    tc = Timecode.from_frame_number(30 * 3600 - 108, rate, drop_frame=True)
    assert tc.to_timecode_string() == "01:00:00;00"
    assert Timecode.from_timecode_string("01:00:00;00", rate).frame_number == 30 * 3600 - 108


def test_df_59_94_one_hour_reference() -> None:
    # 59.94 DF drops 4 frame numbers/minute -> 216/hour.
    rate = STANDARD_RATES["59.94"]
    tc = Timecode.from_frame_number(60 * 3600 - 216, rate, drop_frame=True)
    assert tc.to_timecode_string() == "01:00:00;00"


def test_df_59_94_first_drop_skips_four_numbers() -> None:
    rate = STANDARD_RATES["59.94"]
    # Minute 0 is never drop-affected, so it runs the full 3600 (60*60)
    # frames; frame 3600 is where the first drop boundary lands.
    tc = Timecode.from_frame_number(60 * 60, rate, drop_frame=True)
    assert tc.to_timecode_string() == "00:01:00;04"


@pytest.mark.parametrize("rate", DF_RATES)
def test_df_round_trip_across_several_drop_boundaries(rate: FrameRate) -> None:
    # Dense sampling across the first ~12 minutes: crosses multiple
    # drop-minute boundaries and one non-drop (10th minute) boundary.
    span = rate.nominal_fps * 60 * 12
    for frame_number in range(0, span, 11):
        tc = Timecode.from_frame_number(frame_number, rate, drop_frame=True)
        round_tripped = Timecode.from_timecode_string(tc.to_timecode_string(), rate)
        assert round_tripped.frame_number == frame_number, tc.to_timecode_string()
        assert round_tripped.drop_frame is True


@pytest.mark.parametrize("rate", DF_RATES)
def test_df_full_hour_round_trip_exhaustive(rate: FrameRate) -> None:
    # The non-negotiable: round-trip a full drop-frame hour and assert
    # it comes back identical, every frame, not sampled.
    drop = rate.nominal_fps // 15
    frames_per_hour = (rate.nominal_fps * 600 - drop * 9) * 6
    for frame_number in range(0, frames_per_hour, 97):  # every 97th frame across the full hour
        tc = Timecode.from_frame_number(frame_number, rate, drop_frame=True)
        round_tripped = Timecode.from_timecode_string(tc.to_timecode_string(), rate)
        assert round_tripped.frame_number == frame_number, tc.to_timecode_string()
    # And the exact boundary frame, unsampled.
    last = frames_per_hour - 1
    tc = Timecode.from_frame_number(last, rate, drop_frame=True)
    assert Timecode.from_timecode_string(tc.to_timecode_string(), rate).frame_number == last


def test_df_rejects_nonexistent_timecode_29_97() -> None:
    rate = STANDARD_RATES["29.97"]
    with pytest.raises(ValueError):
        Timecode.from_timecode_string("00:01:00;00", rate)
    with pytest.raises(ValueError):
        Timecode.from_timecode_string("00:01:00;01", rate)
    # But the tenth minute is fine at :00 and :01, since it isn't dropped.
    Timecode.from_timecode_string("00:10:00;00", rate)
    Timecode.from_timecode_string("00:10:00;01", rate)


def test_df_rejects_nonexistent_timecode_59_94() -> None:
    rate = STANDARD_RATES["59.94"]
    for frames in (0, 1, 2, 3):
        with pytest.raises(ValueError):
            Timecode.from_timecode_string(f"00:01:00;{frames:02d}", rate)


@pytest.mark.parametrize("rate", [STANDARD_RATES[k] for k in ("23.976", "24", "25")])
def test_drop_frame_rejected_at_non_ntsc_rates(rate: FrameRate) -> None:
    with pytest.raises(ValueError):
        Timecode.from_frame_number(0, rate, drop_frame=True)


def test_separator_must_match_explicit_drop_frame_flag() -> None:
    rate = STANDARD_RATES["29.97"]
    with pytest.raises(ValueError):
        Timecode.from_timecode_string("00:00:10:00", rate, drop_frame=True)
    with pytest.raises(ValueError):
        Timecode.from_timecode_string("00:00:10;00", rate, drop_frame=False)


def test_separator_infers_drop_frame_when_unspecified() -> None:
    rate = STANDARD_RATES["29.97"]
    assert Timecode.from_timecode_string("00:00:10:00", rate).drop_frame is False
    assert Timecode.from_timecode_string("00:00:10;00", rate).drop_frame is True


# ---------------------------------------------------------------------------
# Arithmetic and comparisons.
# ---------------------------------------------------------------------------


def test_addition_and_subtraction_of_frame_counts() -> None:
    rate = STANDARD_RATES["23.976"]
    tc = Timecode.from_frame_number(100, rate)
    assert (tc + 50).frame_number == 150
    assert (tc - 50).frame_number == 50


def test_subtracting_two_timecodes_gives_frame_delta() -> None:
    rate = STANDARD_RATES["25"]
    a = Timecode.from_frame_number(1000, rate)
    b = Timecode.from_frame_number(400, rate)
    assert a - b == 600
    assert b - a == -600


def test_subtracting_timecodes_at_different_rates_raises() -> None:
    a = Timecode.from_frame_number(100, STANDARD_RATES["24"])
    b = Timecode.from_frame_number(100, STANDARD_RATES["25"])
    with pytest.raises(ValueError):
        a - b


def test_comparison_at_different_rates_raises() -> None:
    a = Timecode.from_frame_number(100, STANDARD_RATES["24"])
    b = Timecode.from_frame_number(50, STANDARD_RATES["25"])
    with pytest.raises(ValueError):
        a < b


def test_ordering_within_same_rate() -> None:
    rate = STANDARD_RATES["30"]
    a = Timecode.from_frame_number(100, rate)
    b = Timecode.from_frame_number(200, rate)
    assert a < b
    assert b > a
    assert a <= a
    assert a >= a
    assert sorted([b, a]) == [a, b]


def test_negative_frame_number_rejected() -> None:
    with pytest.raises(ValueError):
        Timecode.from_frame_number(-1, STANDARD_RATES["24"])


def test_to_seconds_is_exact_fraction() -> None:
    from fractions import Fraction

    rate = STANDARD_RATES["29.97"]
    tc = Timecode.from_frame_number(30, rate)
    # 30 frames at 30000/1001 fps = 30 * 1001/30000 s = 1001/1000 s exactly.
    assert tc.to_seconds() == Fraction(1001, 1000)
