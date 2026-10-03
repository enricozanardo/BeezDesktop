"""Packaged app icons must be real Beez assets, not BeeWare/Timbrapp defaults."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "src" / "beezdesktop" / "resources"


def test_macos_icns_is_present_and_nontrivial():
    icns = RES / "beezdesktop.icns"
    assert icns.is_file(), "briefcase needs beezdesktop.icns or it ships the Toga default icon"
    assert icns.stat().st_size > 20_000


def test_windows_ico_is_multisize():
    ico = RES / "beezdesktop.ico"
    assert ico.is_file()
    assert ico.stat().st_size > 10_000


def test_png_master_is_1024():
    png = RES / "beezdesktop-1024.png"
    assert png.is_file()
    assert png.stat().st_size > 5_000
