def test_version_is_single_source() -> None:
    from mcm_agent.version import __version__

    assert __version__ == "0.1.0"

    import mcm_agent.cli as cli

    assert cli.VERSION == __version__
