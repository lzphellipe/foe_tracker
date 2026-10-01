"""Pré-processamento e alinhamento do quadro atual à imagem de referência.

O painel/bancada pode sofrer pequenos deslocamentos (câmera esbarrada,
vibração). Para que as posições dos slots continuem válidas, cada quadro é
registrado na imagem de referência por homografia estimada com ORB + RANSAC.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import ConfigAlinhamento


def preprocessar(imagem: np.ndarray, usar_clahe: bool = True) -> np.ndarray:
    """Converte para cinza, reduz ruído e equaliza contraste (CLAHE)."""
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY) if imagem.ndim == 3 else imagem
    cinza = cv2.GaussianBlur(cinza, (3, 3), 0)
    if usar_clahe:
        cinza = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cinza)
    return cinza


@dataclass
class ResultadoAlinhamento:
    imagem: np.ndarray            # quadro já alinhado (BGR)
    homografia: np.ndarray | None # matriz 3x3, ou None se não alinhou
    correspondencias: int         # inliers do RANSAC
    alinhado: bool


class Alinhador:
    def __init__(self, referencia: np.ndarray, cfg: ConfigAlinhamento):
        self.cfg = cfg
        self.forma = referencia.shape[:2]
        self._orb = cv2.ORB_create(nfeatures=cfg.max_features)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        ref_proc = preprocessar(referencia, cfg.usar_clahe)
        self._kp_ref, self._desc_ref = self._orb.detectAndCompute(ref_proc, None)
        if self._desc_ref is None or len(self._kp_ref) < cfg.min_correspondencias:
            raise ValueError("Imagem de referência com poucos pontos de interesse")

    def alinhar(self, quadro: np.ndarray) -> ResultadoAlinhamento:
        proc = preprocessar(quadro, self.cfg.usar_clahe)
        kp, desc = self._orb.detectAndCompute(proc, None)
        if desc is None or len(kp) < self.cfg.min_correspondencias:
            return ResultadoAlinhamento(quadro, None, 0, False)

        # Teste de razão de Lowe para descartar correspondências ambíguas
        pares = self._matcher.knnMatch(desc, self._desc_ref, k=2)
        bons = [m for m, n in (p for p in pares if len(p) == 2) if m.distance < 0.75 * n.distance]
        if len(bons) < self.cfg.min_correspondencias:
            return ResultadoAlinhamento(quadro, None, len(bons), False)

        src = np.float32([kp[m.queryIdx].pt for m in bons]).reshape(-1, 1, 2)
        dst = np.float32([self._kp_ref[m.trainIdx].pt for m in bons]).reshape(-1, 1, 2)
        H, mascara = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        inliers = int(mascara.sum()) if mascara is not None else 0
        if H is None or inliers < self.cfg.min_correspondencias:
            return ResultadoAlinhamento(quadro, None, inliers, False)

        h, w = self.forma
        alinhada = cv2.warpPerspective(quadro, H, (w, h))
        return ResultadoAlinhamento(alinhada, H, inliers, True)
