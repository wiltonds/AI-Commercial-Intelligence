import pytest


@pytest.fixture(autouse=True)
def _log_isolado(tmp_path, monkeypatch):
    """Nenhum teste grava no log de atualizações real."""
    import src.tools.log_atualizacoes as log
    monkeypatch.setattr(log, "ARQ_LOG", tmp_path / "LOG_ATUALIZACOES.csv")
