"""Detecção de ferramentas com YOLO (Ultralytics)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .config import ConfigDetector

Caixa = tuple[float, float, float, float]  # x1, y1, x2, y2 em pixels


@dataclass(frozen=True)
class Deteccao:
    classe_id: int
    nome: str
    confianca: float
    caixa: Caixa


class Detector(Protocol):
    """Qualquer detector que devolva uma lista de Deteccao (facilita testes)."""

    def detectar(self, imagem: np.ndarray) -> list[Deteccao]: ...


class DetectorYOLO:
    def __init__(self, cfg: ConfigDetector):
        from ultralytics import YOLO  # import tardio: testes não exigem o pacote

        self.cfg = cfg
        self._modelo = YOLO(cfg.modelo)
        self.nomes: dict[int, str] = self._modelo.names

    def detectar(self, imagem: np.ndarray) -> list[Deteccao]:
        resultado = self._modelo.predict(
            imagem,
            conf=self.cfg.confianca_minima,
            device=self.cfg.dispositivo,
            verbose=False,
        )[0]
        saida: list[Deteccao] = []
        for caixa in resultado.boxes:
            cid = int(caixa.cls.item())
            saida.append(
                Deteccao(
                    classe_id=cid,
                    nome=self.nomes.get(cid, str(cid)),
                    confianca=float(caixa.conf.item()),
                    caixa=tuple(float(v) for v in caixa.xyxy[0].tolist()),
                )
            )
        return saida
