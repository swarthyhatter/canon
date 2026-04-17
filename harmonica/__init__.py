# Start here — Canon has two layers: harmonica/ (REST client) and agent/ (KG logic).
# HarmonicaClient is the only public export from this layer.
# → next: harmonica/client.py:21
from .client import HarmonicaClient

__all__ = ["HarmonicaClient"]
