"""Testa o espaçamento entre o início dos robôs sem abrir navegador."""
import asyncio

from app.bot.browser import BrowserManager
from app.core.config import Settings


def test_inicios_sao_espacados():
    manager = BrowserManager(Settings(bot_start_interval_s=0.2))

    async def rodar():
        relogio = asyncio.get_running_loop()
        inicios = []

        async def iniciar():
            await manager._aguardar_intervalo()
            inicios.append(relogio.time())

        await asyncio.gather(*(iniciar() for _ in range(3)))
        return inicios

    inicios = asyncio.run(rodar())
    intervalos = [b - a for a, b in zip(inicios, inicios[1:])]
    assert all(i >= 0.18 for i in intervalos)


def test_sem_intervalo_nao_espera():
    manager = BrowserManager(Settings(bot_start_interval_s=0))

    async def rodar():
        relogio = asyncio.get_running_loop()
        inicio = relogio.time()
        await asyncio.gather(*(manager._aguardar_intervalo() for _ in range(5)))
        return relogio.time() - inicio

    assert asyncio.run(rodar()) < 0.1
