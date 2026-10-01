import cv2
import numpy as np

from foe.alinhamento import Alinhador
from foe.config import ConfigAlinhamento


def painel_sintetico(seed=7, w=640, h=480):
    """Imagem com textura suficiente para o ORB (simula um painel com ferramentas)."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 200, np.uint8)
    for _ in range(60):
        x, y = int(rng.integers(0, w - 60)), int(rng.integers(0, h - 40))
        cor = tuple(int(c) for c in rng.integers(0, 255, 3))
        if rng.random() < 0.5:
            cv2.rectangle(img, (x, y), (x + int(rng.integers(15, 60)), y + int(rng.integers(10, 40))), cor, -1)
        else:
            cv2.circle(img, (x + 20, y + 20), int(rng.integers(5, 20)), cor, -1)
    return img


def test_alinha_quadro_deslocado():
    ref = painel_sintetico()
    H_real = np.array([[1.0, 0.02, 12], [-0.015, 1.0, -8], [0, 0, 1]], np.float64)
    deslocado = cv2.warpPerspective(ref, H_real, (ref.shape[1], ref.shape[0]))

    res = Alinhador(ref, ConfigAlinhamento(min_correspondencias=20)).alinhar(deslocado)
    assert res.alinhado

    # A homografia estimada deve desfazer a real: H_est ≈ inv(H_real)
    pontos = np.float32([[100, 100], [500, 120], [320, 400]]).reshape(-1, 1, 2)
    ida = cv2.perspectiveTransform(pontos, H_real)
    volta = cv2.perspectiveTransform(ida, res.homografia)
    assert np.abs(volta - pontos).max() < 2.0


def test_quadro_sem_textura_nao_alinha():
    ref = painel_sintetico()
    vazio = np.full_like(ref, 128)
    res = Alinhador(ref, ConfigAlinhamento()).alinhar(vazio)
    assert not res.alinhado and res.homografia is None
