import importlib


def test_import_package():
    """Basic smoke test: package imports and version present."""
    m = importlib.import_module("fluentytdl")
    assert hasattr(m, "__version__")
    assert isinstance(m.__version__, str)


def test_config_example_exists():
    import pathlib

    p = pathlib.Path(__file__).resolve().parents[1] / "config.example.json"
    assert p.exists(), "config.example.json must exist"
