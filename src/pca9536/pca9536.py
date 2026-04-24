import fcntl
import os
import re
from enum import Enum
from typing import Iterator, List, Optional, Tuple, TypeVar, Union

_T = TypeVar('_T')

I2C_SLAVE = 0x0703


def _resolve_bus_path(bus: Union[int, str]) -> str:
    if isinstance(bus, int):
        return f"/dev/i2c-{bus}"
    match = re.search(r"i2c-(\d+)", bus)
    if match:
        return f"/dev/i2c-{match.group(1)}"
    return bus


def _open_i2c(path: str, address: int) -> int:
    fd = os.open(path, os.O_RDWR)
    fcntl.ioctl(fd, I2C_SLAVE, address)
    return fd


class PinMode(Enum):
    output = 0
    input = 1


class PCA9536Pin:
    """A single pin of the PCA9536 GPIO expander."""

    def __init__(self, device: "PCA9536", index: int):
        self.device = device
        self.index = index

    @property
    def mode(self) -> PinMode:
        """Get or set the pin input/output mode.

        The mode is a PinMode object, either PinMode.input or PinMode.output.

        When setting the mode, the strings "input" and "output" can be used interchangeably
        with the values PinMode.input and PinMode.output, respectively."""
        return self.device.mode[self.index]

    @mode.setter
    def mode(self, value: Union[PinMode, str]) -> None:
        self.device.mode = self._value_to_list(value)

    @property
    def polarity_inversion(self) -> bool:
        """Get or set the polarity inversion.

        If the polarity inversion is True, polarity of the read bit is inverted:
        a low logic level will correspond to True, and a high logic level to False.

        The polarity inversion does not affect the output."""
        return self.device.polarity_inversion[self.index]

    @polarity_inversion.setter
    def polarity_inversion(self, value: bool) -> None:
        self.device.polarity_inversion = self._value_to_list(value)

    def read(self) -> bool:
        """Read the current logic level.

        If the polarity inversion if False, this returns True if the logic level is high,
        and low if it is False. If the polarity inversion is True, these values are inverted."""
        return self.device.read()[self.index]

    def write(self, value: bool) -> None:
        """Set the output logic level.

        Sets the output logic level to low if value is False, and to high if value is True.

        This only sets the output flip-flop of the GPIO expander. If the mode of the pin
        is set to input, this has no effect on the logic level."""
        self.device.write(*self._value_to_list(value))

    def _value_to_list(self, value: _T) -> Tuple[Optional[_T], Optional[_T], Optional[_T], Optional[_T]]:
        result: List[Optional[_T]] = [None, None, None, None]
        result[self.index] = value
        return (result[0], result[1], result[2], result[3])


class PCA9536:
    """Driver for the PCA9536 GPIO expander."""

    def __init__(self, bus: Union[int, str], address: int = 0x41) -> None:
        """Initialise the PCA9536.

        Args:
            bus: I2C bus — an integer (e.g. 1 for /dev/i2c-1), a /dev/i2c-N path,
                or a sysfs path containing i2c-N (e.g. /sys/bus/i2c/devices/i2c-1).
            address: The I2C address of the device. Defaults to 0x41."""
        self.address = address
        self._path = _resolve_bus_path(bus)
        self._fd: int = _open_i2c(self._path, self.address)
        self._pins: List[PCA9536Pin] = [PCA9536Pin(self, index) for index in range(4)]

    def __enter__(self) -> "PCA9536":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __getitem__(self, item: int) -> PCA9536Pin:
        return self._pins[item]

    def __iter__(self) -> Iterator[PCA9536Pin]:
        yield from self._pins

    def probe(self, bus: Optional[Union[int, str]] = None, address: int = 0x41) -> bool:
        """Detect whether a PCA9536 is present at the given bus and address.

        Returns True if the device acknowledges, False otherwise."""

        if bus is not None:
            path = _resolve_bus_path(bus)
        else:
            path = self._path

        try:
            fd = _open_i2c(path, address)
            try:
                os.write(fd, bytes(0))
                return True
            except OSError:
                return False
            finally:
                os.close(fd)
        except OSError:
            return False

    @property
    def mode(self) -> Tuple[PinMode, PinMode, PinMode, PinMode]:
        """Get or set the input/output mode of the pins.

        The mode is a tuple of four PinMode objects, each representing the mode of a pin.

        Setting the mode is done with either a single PinMode object to set the mode of all pins:

            device.mode = PinMode.input

        Or with a tuple of four PinMode objects:

            device.mode = PinMode.input, PinMode.input, PinMode.output, PinMode.output

        In such a tuple values can be None in order to leave them unchanged:

            device.mode = PinMode.input, PinMode.input, None, None

        When setting the mode, the strings "input" and "output" can be used interchangeably
        with the values PinMode.input and PinMode.output, respectively. E.g.:

            device.mode = "output"
            device.mode = PinMode.input, "output", "input", None
        """
        data = _read_bits(fd=self._fd, register=0x03, bitmask=0x0F)
        return (
            PinMode(data & 0x01),
            PinMode((data & 0x02) >> 1),
            PinMode((data & 0x04) >> 2),
            PinMode((data & 0x08) >> 3),
        )

    @mode.setter
    def mode(
        self,
        value: Union[
            PinMode,
            str,
            Tuple[
                Optional[Union[PinMode, str]],
                Optional[Union[PinMode, str]],
                Optional[Union[PinMode, str]],
                Optional[Union[PinMode, str]],
            ],
        ],
    ) -> None:
        if not isinstance(value, tuple):
            value = value, value, value, value
        values: List[Optional[PinMode]] = [
            PinMode[v] if isinstance(v, str) else v for v in value
        ]
        bitmask = _bools_to_bits(*(value is not None for value in values))
        mode = _bools_to_bits(*(value == PinMode.input for value in values))
        _write_bits(fd=self._fd, register=0x03, value=mode, bitmask=bitmask)

    @property
    def polarity_inversion(self) -> Tuple[bool, bool, bool, bool]:
        """Get or set the polarity inversion of the pins.

        The polarity inversion is a tuple of four booleans.

        If the polarity inversion of a pin is True, polarity of the read bit is inverted:
        a low logic level will correspond to True, and a high logic level to False.

        Setting the polarity inversion is done with either a single boolean to set all pins:

            device.polarity_inversion = False

        Or with a tuple of four booleans:

            device.polarity_inversion = False, False, True, True

        In such a tuple values can be None in order to leave them unchanged:

            device.polarity_inversion = False, None, True, True"""
        data = _read_bits(fd=self._fd, register=0x02, bitmask=0x0F)
        return (
            bool(data & 0x01),
            bool((data & 0x02) >> 1),
            bool((data & 0x04) >> 2),
            bool((data & 0x08) >> 3),
        )

    @polarity_inversion.setter
    def polarity_inversion(
        self,
        value: Union[
            bool,
            Tuple[
                Optional[bool],
                Optional[bool],
                Optional[bool],
                Optional[bool],
            ],
        ],
    ):
        if not isinstance(value, tuple):
            value = value, value, value, value
        bitmask = _bools_to_bits(*(value is not None for value in value))
        polarity = _bools_to_bits(*(value is True for value in value))
        _write_bits(fd=self._fd, register=0x02, value=polarity, bitmask=bitmask)

    def read(self) -> Tuple[bool, bool, bool, bool]:
        """Read the current logic levels.

        Returns a tuple of four booleans.

        If the polarity inversion if False, this returns True if the logic level is high,
        and low if it is False. If the polarity inversion is True, these values are inverted."""
        data = _read_bits(fd=self._fd, register=0x00, bitmask=0x0F)
        return _bits_to_bools(data)

    def write(
        self,
        pin_0: Optional[bool] = None,
        pin_1: Optional[bool] = None,
        pin_2: Optional[bool] = None,
        pin_3: Optional[bool] = None,
    ):
        """Set one or more output logic levels.

        Sets a output logic level to low if value is False, and to high if value is True.

        This only sets the output flip-flops of the GPIO expander. If the mode of the pin
        is set to input, this has no effect on the logic level."""
        pins = (pin_0, pin_1, pin_2, pin_3)
        value = _bools_to_bits(*(pin is True for pin in pins))
        bitmask = _bools_to_bits(*(pin is not None for pin in pins))
        _write_bits(fd=self._fd, register=0x01, value=value, bitmask=bitmask)


def _bools_to_bits(bool_0: bool, bool_1: bool, bool_2: bool, bool_3: bool) -> int:
    return (bool_0 * 0x01) | (bool_1 * 0x02) | (bool_2 * 0x04) | (bool_3 * 0x08)


def _bits_to_bools(bits: int) -> Tuple[bool, bool, bool, bool]:
    return (
        bool(bits & 0x01),
        bool(bits & 0x02),
        bool(bits & 0x04),
        bool(bits & 0x08),
    )


def _read_bits(fd: int, register: int, bitmask: int) -> int:
    os.write(fd, bytes([register]))
    return os.read(fd, 1)[0] & bitmask


def _write_bits(fd: int, register: int, value: int, bitmask: int) -> None:
    other_bits = _read_bits(fd=fd, register=register, bitmask=0xFF - bitmask)
    value_bits = value & bitmask
    os.write(fd, bytes([register, other_bits | value_bits]))
