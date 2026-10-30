"""Condiciones de la tarea programada de Windows (tiendas `solo_local`).

La tarea la lanza el Programador de tareas cada 30 minutos sin ventana. Antes de
hacer ninguna petición se comprueba la batería y que no haya otra instancia.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

log = logging.getLogger(__name__)


class _EstadoEnergia(ctypes.Structure):  # SYSTEM_POWER_STATUS de la API de Windows
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def energia() -> tuple[bool | None, int | None]:
    """(enchufado, % batería). None = desconocido (sin batería o fuera de Windows)."""
    if sys.platform != "win32":
        return None, None
    e = _EstadoEnergia()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(e)):
        return None, None
    enchufado = {0: False, 1: True}.get(e.ACLineStatus)
    pct = None if e.BatteryLifePercent == 255 else e.BatteryLifePercent
    return enchufado, pct


def prioridad_baja() -> bool:
    """Modo segundo plano de Windows: baja a la vez la prioridad de CPU, disco y memoria
    de este proceso (PROCESS_MODE_BACKGROUND_BEGIN), para no notarse con el PC ocupado."""
    if sys.platform != "win32":
        return False
    k32 = ctypes.WinDLL("kernel32")
    # Tipos explícitos: el HANDLE es de 64 bits y ctypes lo truncaría a int de 32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    return bool(k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00100000))


def bateria_suficiente(enchufado: bool | None, pct: int | None, minimo: int) -> bool:
    """Solo se salta el ciclo si va con batería y está por debajo del mínimo."""
    return not (enchufado is False and pct is not None and pct < minimo)


class Cerrojo:
    """Una sola instancia: bloqueo del sistema sobre un archivo, que se libera
    solo si el proceso muere (no deja cerrojos huérfanos)."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self._f = None

    def adquirir(self) -> bool:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.ruta, "a+b")
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self._f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._f.close()
            self._f = None
            return False
        return True

    def liberar(self) -> None:
        if self._f:
            self._f.close()  # cerrar el archivo suelta el bloqueo
            self._f = None


def log_a_archivo(ruta: Path) -> None:
    """Sin ventana no hay consola: el log va a un archivo rotativo (3 × 1 MB)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    h = RotatingFileHandler(ruta, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                                     "%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(h)
