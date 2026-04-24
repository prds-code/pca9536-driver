import os

from pytest import fixture, mark, raises

from pca9536.pca9536 import (
    I2C_SLAVE,
    PCA9536,
    PCA9536Pin,
    PinMode,
    _read_bits,
    _write_bits,
)

MOCK_FD = 5


@fixture(scope="function")
def mock_write(mocker):
    return mocker.patch("pca9536.pca9536.os.write")


def _patch_i2c(mocker, mock_write, read_value: int = 0xA5):
    mocker.patch("pca9536.pca9536.os.open", return_value=MOCK_FD)
    mocker.patch("pca9536.pca9536.fcntl.ioctl")
    mocker.patch("pca9536.pca9536.os.read", return_value=bytes([read_value]))
    mocker.patch("pca9536.pca9536.os.close")


class TestPCA9536:
    @fixture(scope="function")
    def device(self, mocker, mock_write) -> PCA9536:
        _patch_i2c(mocker, mock_write)
        return PCA9536(bus=1)

    def test_getitem(self, device: PCA9536):
        pin = device[2]
        assert isinstance(pin, PCA9536Pin)
        assert pin.device == device
        assert pin.index == 2
        with raises(IndexError):
            _ = device[4]

    def test_iter(self, device: PCA9536):
        for pin in device:
            assert isinstance(pin, PCA9536Pin)

    def test_mode(self, device: PCA9536):
        modes = device.mode
        assert modes == (PinMode.input, PinMode.output, PinMode.input, PinMode.output)

    @mark.parametrize(
        "value, write_byte",
        [
            (PinMode.input, 0xAF),
            (PinMode.output, 0xA0),
            ("input", 0xAF),
            ("output", 0xA0),
            (("input", "output", "output", "input"), 0xA9),
            ((PinMode.output, PinMode.input, None, None), 0xA6),
            ((None, None, None, None), 0xA5),
        ],
    )
    def test_set_mode(self, device: PCA9536, mock_write, value, write_byte):
        device.mode = value
        mock_write.assert_called_with(MOCK_FD, bytes([0x03, write_byte]))

    def test_polarity(self, device: PCA9536):
        assert device.polarity_inversion == (True, False, True, False)

    @mark.parametrize(
        "value, write_byte",
        [
            (True, 0xAF),
            (False, 0xA0),
            ((True, False, False, True), 0xA9),
            ((False, True, None, None), 0xA6),
            ((None, None, None, None), 0xA5),
        ],
    )
    def test_set_polarity(self, device: PCA9536, mock_write, value, write_byte):
        device.polarity_inversion = value
        mock_write.assert_called_with(MOCK_FD, bytes([0x02, write_byte]))

    def test_read(self, device: PCA9536):
        assert device.read() == (True, False, True, False)

    def test_write(self, device: PCA9536, mock_write):
        device.write(pin_0=True, pin_2=False)
        mock_write.assert_called_with(MOCK_FD, bytes([0x01, 0xA1]))


class TestPCA9536Pin:
    @fixture(scope="function")
    def pin(self, mocker, mock_write) -> PCA9536Pin:
        _patch_i2c(mocker, mock_write)
        device = PCA9536(bus=1)
        return device[2]

    def test_mode(self, pin: PCA9536Pin):
        assert pin.mode == PinMode.input

    def test_set_mode(self, pin: PCA9536Pin, mock_write):
        pin.mode = PinMode.output
        mock_write.assert_called_with(MOCK_FD, bytes([0x03, 0xA1]))

    def test_polarity(self, pin: PCA9536Pin):
        assert pin.polarity_inversion is True

    def test_set_polarity(self, pin: PCA9536Pin, mock_write):
        pin.polarity_inversion = False
        mock_write.assert_called_with(MOCK_FD, bytes([0x02, 0xA1]))

    def test_read(self, pin: PCA9536Pin):
        assert pin.read() is True

    def test_write(self, pin: PCA9536Pin, mock_write):
        pin.write(True)
        mock_write.assert_called_with(MOCK_FD, bytes([0x01, 0xA5]))


def test_read_bits(mocker):
    mock_read = mocker.patch("pca9536.pca9536.os.read", return_value=bytes([0xFF]))
    mocker.patch("pca9536.pca9536.os.write")
    assert _read_bits(fd=MOCK_FD, register=0x00, bitmask=0xAA) == 0xAA
    mock_read.assert_called_once_with(MOCK_FD, 1)


def test_write_bits(mocker):
    mocker.patch("pca9536.pca9536.os.read", return_value=bytes([0x55]))
    mock_write = mocker.patch("pca9536.pca9536.os.write")
    _write_bits(fd=MOCK_FD, register=0x00, value=0xAA, bitmask=0xF0)
    mock_write.assert_called_with(MOCK_FD, bytes([0x00, 0xA5]))


def test_probe_present(mocker):
    mocker.patch("pca9536.pca9536.os.open", return_value=MOCK_FD)
    mocker.patch("pca9536.pca9536.fcntl.ioctl")
    mocker.patch("pca9536.pca9536.os.read", return_value=bytes([0xA5]))
    mocker.patch("pca9536.pca9536.os.write")
    mocker.patch("pca9536.pca9536.os.close")
    device = PCA9536(bus=1)
    assert device.probe() is True


def test_probe_absent(mocker):
    mocker.patch("pca9536.pca9536.os.open", return_value=MOCK_FD)
    mocker.patch("pca9536.pca9536.fcntl.ioctl")
    mocker.patch("pca9536.pca9536.os.read", return_value=bytes([0xA5]))
    mock_write = mocker.patch("pca9536.pca9536.os.write")
    mocker.patch("pca9536.pca9536.os.close")
    device = PCA9536(bus=1)
    mock_write.side_effect = OSError("Remote I/O error")
    assert device.probe() is False


def test_probe_no_bus(mocker):
    mocker.patch("pca9536.pca9536.os.open", side_effect=[MOCK_FD, OSError("No such file")])
    mocker.patch("pca9536.pca9536.fcntl.ioctl")
    mocker.patch("pca9536.pca9536.os.read", return_value=bytes([0xA5]))
    mocker.patch("pca9536.pca9536.os.write")
    mocker.patch("pca9536.pca9536.os.close")
    device = PCA9536(bus=1)
    assert device.probe(bus=99) is False


def test_init_opens_device(mocker):
    mock_open = mocker.patch("pca9536.pca9536.os.open", return_value=MOCK_FD)
    mock_ioctl = mocker.patch("pca9536.pca9536.fcntl.ioctl")
    mocker.patch("pca9536.pca9536.os.read", return_value=bytes([0x00]))
    mocker.patch("pca9536.pca9536.os.write")
    mocker.patch("pca9536.pca9536.os.close")
    PCA9536(bus=1)
    mock_open.assert_called_once_with("/dev/i2c-1", os.O_RDWR)
    mock_ioctl.assert_called_once_with(MOCK_FD, I2C_SLAVE, 0x41)


def test_init_sysfs_path(mocker):
    mock_open = mocker.patch("pca9536.pca9536.os.open", return_value=MOCK_FD)
    mocker.patch("pca9536.pca9536.fcntl.ioctl")
    mocker.patch("pca9536.pca9536.os.read", return_value=bytes([0x00]))
    mocker.patch("pca9536.pca9536.os.write")
    mocker.patch("pca9536.pca9536.os.close")
    PCA9536(bus="/sys/bus/i2c/devices/i2c-3")
    mock_open.assert_called_once_with("/dev/i2c-3", os.O_RDWR)
