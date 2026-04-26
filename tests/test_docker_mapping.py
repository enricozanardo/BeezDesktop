"""Smoke tests for shared.client_core.docker_mapping.

These guard the regression where production smart/storage/chain hosts were
silently rerouted to 127.0.0.1:5000 because their public IP was not in
DOCKER_NODE_MAP. We must always pass the public IP/hostname through unchanged
with the canonical 5000 / 5555 ports.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def docker_mapping():
    return importlib.import_module("shared.client_core.docker_mapping")


def test_local_chain1_resolves_to_loopback_http(docker_mapping):
    host, port = docker_mapping.resolve_node_address("chain1", use_zmq=False)
    assert host == "127.0.0.1"
    assert port == 5000


def test_local_chain1_resolves_to_loopback_zmq(docker_mapping):
    host, port = docker_mapping.resolve_node_address("chain1", use_zmq=True)
    assert host == "127.0.0.1"
    assert port == 5555


def test_public_ipv4_passes_through_unchanged(docker_mapping):
    host, port = docker_mapping.resolve_node_address("203.0.113.42", use_zmq=False)
    assert host == "203.0.113.42"
    assert port == 5000


def test_public_ipv4_zmq_uses_5555(docker_mapping):
    host, port = docker_mapping.resolve_node_address("203.0.113.42", use_zmq=True)
    assert host == "203.0.113.42"
    assert port == 5555


def test_public_hostname_passes_through(docker_mapping):
    host, port = docker_mapping.resolve_node_address("smart1.beez.example.com", use_zmq=False)
    assert host == "smart1.beez.example.com"
    assert port == 5000


def test_private_rfc1918_is_treated_as_local_compose(docker_mapping):
    """RFC1918 addresses still get the docker-mapping fallback (5000)."""
    host, port = docker_mapping.resolve_node_address("10.0.0.5", use_zmq=False)
    # Treated as local-ish: returned as-is on default port (no remap to loopback).
    assert host == "10.0.0.5"
    assert port == 5000
