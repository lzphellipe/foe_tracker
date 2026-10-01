import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from foe.config import ConfigDetector, ConfigInventario  # noqa: E402
from foe.detector import Deteccao  # noqa: E402
from foe.inventario import Slot  # noqa: E402

T0 = datetime(2026, 9, 29, 8, 0, 0)


@pytest.fixture
def slots():
    return [
        Slot("CHV-10MM-01", "Chave combinada 10 mm", 0, (10, 10, 110, 60)),
        Slot("ALI-01", "Alicate universal", 1, (150, 10, 250, 60)),
        Slot("CHV-10MM-02", "Chave combinada 10 mm", 0, (10, 100, 110, 150)),
    ]


@pytest.fixture
def cfg_inv():
    return ConfigInventario(iou_minimo=0.3, quadros_confirmacao=3, alarme_ausencia_segundos=60)


@pytest.fixture
def cfg_det():
    return ConfigDetector(confianca_minima=0.25, confianca_aceita=0.6)


def det(slot: Slot, conf=0.9, dx=0):
    x1, y1, x2, y2 = slot.caixa
    return Deteccao(slot.classe_id, slot.nome, conf, (x1 + dx, y1, x2 + dx, y2))


def instante(i: int) -> datetime:
    return T0 + timedelta(seconds=i)
