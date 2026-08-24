"""Frame-accurate timecode.

Every cut point in this project is an integer frame number counted from
00:00:00:00. Never a float, never a rounded second. Frame rates are stored
as exact fractions (Fraction(30000, 1001), not 29.97) so nothing ever
accumulates rounding error across a long timeline.

Drop-frame (DF) timecode does not drop frames of picture. It periodically
skips frame *numbers* in the displayed HH:MM:SS:FF label so that timecode
duration tracks wall-clock duration for the NTSC-family rates (29.97,
59.94), which run at exactly 1000/1001 of their nominal integer rate. Non-
drop-frame (NDF) timecode never skips numbers, so at 29.97 NDF a timecode
of 01:00:00:00 is about 3.6 seconds of wall clock ahead of a real hour.
That drift is exactly why drop-frame exists, and why the two must never be
silently interchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class FrameRate:
    """An exact frame rate. Construct via the STANDARD_RATES registry."""

    rate: Fraction
    name: str

    @property
    def nominal_fps(self) -> int:
        """The integer rate used for timecode display (30 for 29.97, etc.)."""
        return round(self.rate)

    @property
    def is_ntsc(self) -> bool:
        return self.rate.denominator == 1001

    @property
    def drop_frame_capable(self) -> bool:
        # Drop-frame is only defined, by convention, for the 30- and
        # 60-nominal NTSC families. 23.976 (24-nominal) is always NDF.
        return self.is_ntsc and self.nominal_fps in (30, 60)

    def __str__(self) -> str:
        return self.name


STANDARD_RATES: dict[str, FrameRate] = {
    "23.976": FrameRate(Fraction(24000, 1001), "23.976"),
    "24": FrameRate(Fraction(24, 1), "24"),
    "25": FrameRate(Fraction(25, 1), "25"),
    "29.97": FrameRate(Fraction(30000, 1001), "29.97"),
    "30": FrameRate(Fraction(30, 1), "30"),
    "59.94": FrameRate(Fraction(60000, 1001), "59.94"),
    "60": FrameRate(Fraction(60, 1), "60"),
}


def _drop_frames_per_minute(nominal_fps: int) -> int:
    # SMPTE 12M: drop 2 frame numbers/minute at 30-nominal, 4 at 60-nominal.
    return nominal_fps // 15


def _frame_number_to_ndf_components(frame_number: int, nominal_fps: int) -> tuple[int, int, int, int]:
    frames = frame_number % nominal_fps
    total_seconds = frame_number // nominal_fps
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = (total_minutes // 60) % 24
    return hours, minutes, seconds, frames


def _ndf_components_to_frame_number(hours: int, minutes: int, seconds: int, frames: int, nominal_fps: int) -> int:
    return ((hours * 60 + minutes) * 60 + seconds) * nominal_fps + frames


def _frame_number_to_df_components(frame_number: int, nominal_fps: int) -> tuple[int, int, int, int]:
    drop = _drop_frames_per_minute(nominal_fps)
    frames_per_minute = nominal_fps * 60 - drop
    frames_per_10_minutes = nominal_fps * 600 - drop * 9

    ten_minute_blocks, remainder = divmod(frame_number, frames_per_10_minutes)
    if remainder < drop:
        adjustment = 0
    else:
        adjustment = drop * ((remainder - drop) // frames_per_minute)
    adjusted = frame_number + drop * 9 * ten_minute_blocks + adjustment

    return _frame_number_to_ndf_components(adjusted, nominal_fps)


def _df_components_to_frame_number(hours: int, minutes: int, seconds: int, frames: int, nominal_fps: int) -> int:
    drop = _drop_frames_per_minute(nominal_fps)
    total_minutes = hours * 60 + minutes

    if seconds == 0 and frames < drop and total_minutes % 10 != 0:
        raise ValueError(
            f"{hours:02d}:{minutes:02d}:{seconds:02d};{frames:02d} does not exist in drop-frame "
            f"timecode at {nominal_fps}-nominal fps: frame numbers 0-{drop - 1} are dropped at the "
            "start of every minute except every 10th minute."
        )

    frame_number_ndf = _ndf_components_to_frame_number(hours, minutes, seconds, frames, nominal_fps)
    dropped_so_far = drop * (total_minutes - total_minutes // 10)
    return frame_number_ndf - dropped_so_far


@dataclass(frozen=True)
class Timecode:
    """An absolute frame position on a timeline at a given rate.

    `frame_number` is the single source of truth. The HH:MM:SS:FF string is
    a display derived from it, never the other way around during arithmetic.
    """

    frame_number: int
    rate: FrameRate
    drop_frame: bool = False

    def __post_init__(self) -> None:
        if self.frame_number < 0:
            raise ValueError(f"frame_number must be non-negative, got {self.frame_number}")
        if self.drop_frame and not self.rate.drop_frame_capable:
            raise ValueError(
                f"drop-frame timecode is not defined at {self.rate} fps "
                "(only 29.97 and 59.94 support drop-frame)"
            )

    @classmethod
    def from_frame_number(cls, frame_number: int, rate: FrameRate, drop_frame: bool = False) -> Timecode:
        return cls(frame_number, rate, drop_frame)

    @classmethod
    def from_timecode_string(cls, tc_string: str, rate: FrameRate, drop_frame: bool | None = None) -> Timecode:
        """Parse "HH:MM:SS:FF" (NDF) or "HH:MM:SS;FF" (DF).

        If `drop_frame` is not given explicitly, it is inferred from the
        separator before the frames field (';' = drop-frame, ':' = non-drop).
        """
        parts = tc_string.replace(";", ":").split(":")
        if len(parts) != 4:
            raise ValueError(f"expected HH:MM:SS:FF or HH:MM:SS;FF, got {tc_string!r}")
        hours, minutes, seconds, frames = (int(p) for p in parts)

        inferred_drop_frame = ";" in tc_string
        if drop_frame is None:
            drop_frame = inferred_drop_frame
        elif drop_frame != inferred_drop_frame:
            raise ValueError(
                f"separator in {tc_string!r} implies drop_frame={inferred_drop_frame} "
                f"but drop_frame={drop_frame} was requested explicitly"
            )

        if frames < 0 or frames >= rate.nominal_fps:
            raise ValueError(f"frame field {frames} out of range for {rate} fps (0-{rate.nominal_fps - 1})")

        if drop_frame:
            if not rate.drop_frame_capable:
                raise ValueError(f"drop-frame timecode is not defined at {rate} fps")
            frame_number = _df_components_to_frame_number(hours, minutes, seconds, frames, rate.nominal_fps)
        else:
            frame_number = _ndf_components_to_frame_number(hours, minutes, seconds, frames, rate.nominal_fps)

        return cls(frame_number, rate, drop_frame)

    def to_timecode_string(self) -> str:
        if self.drop_frame:
            hours, minutes, seconds, frames = _frame_number_to_df_components(self.frame_number, self.rate.nominal_fps)
            separator = ";"
        else:
            hours, minutes, seconds, frames = _frame_number_to_ndf_components(self.frame_number, self.rate.nominal_fps)
            separator = ":"
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{frames:02d}"

    def to_seconds(self) -> Fraction:
        """Exact wall-clock time as a Fraction, for interop math (e.g. audio sync)."""
        return Fraction(self.frame_number) / self.rate.rate

    def __str__(self) -> str:
        return self.to_timecode_string()

    def __repr__(self) -> str:
        return f"Timecode({self.frame_number}, {self.rate}, drop_frame={self.drop_frame})"

    def __add__(self, frames: int) -> Timecode:
        if not isinstance(frames, int):
            return NotImplemented
        return Timecode(self.frame_number + frames, self.rate, self.drop_frame)

    def __radd__(self, frames: int) -> Timecode:
        return self.__add__(frames)

    def __sub__(self, other: Timecode | int) -> Timecode | int:
        if isinstance(other, Timecode):
            self._check_comparable(other)
            return self.frame_number - other.frame_number
        if isinstance(other, int):
            return Timecode(self.frame_number - other, self.rate, self.drop_frame)
        return NotImplemented

    def _check_comparable(self, other: Timecode) -> None:
        if self.rate != other.rate:
            raise ValueError(f"cannot compare/subtract timecodes at different rates: {self.rate} vs {other.rate}")

    def __lt__(self, other: Timecode) -> bool:
        if not isinstance(other, Timecode):
            return NotImplemented
        self._check_comparable(other)
        return self.frame_number < other.frame_number

    def __le__(self, other: Timecode) -> bool:
        if not isinstance(other, Timecode):
            return NotImplemented
        self._check_comparable(other)
        return self.frame_number <= other.frame_number

    def __gt__(self, other: Timecode) -> bool:
        if not isinstance(other, Timecode):
            return NotImplemented
        self._check_comparable(other)
        return self.frame_number > other.frame_number

    def __ge__(self, other: Timecode) -> bool:
        if not isinstance(other, Timecode):
            return NotImplemented
        self._check_comparable(other)
        return self.frame_number >= other.frame_number
