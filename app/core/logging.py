"""Configuração de logging estruturado simples."""
import logging


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    # Reduz ruído de bibliotecas
    logging.getLogger("asyncio").setLevel(logging.WARNING)
