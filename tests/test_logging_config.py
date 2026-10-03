"""Logging must not crash when stdout is missing (Windows GUI)."""

import sys
from beezdesktop import logging_config


def test_setup_logging_with_none_stdout(monkeypatch, tmp_path):
    logging_config._initialized = False
    monkeypatch.setattr(logging_config, "LOG_DIR", tmp_path)
    monkeypatch.setattr(logging_config, "LOG_FILE", tmp_path / "beezdesktop.log")
    monkeypatch.setattr(sys, "__stdout__", None)
    monkeypatch.setattr(sys, "__stderr__", None)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    logger = logging_config.setup_logging("INFO")
    logger.info("started without a console")
    assert (tmp_path / "beezdesktop.log").is_file()
    logging_config._initialized = False
