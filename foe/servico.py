"""Orquestra o pipeline: quadro → alinhamento → YOLO → comparação → banco.

Não depende de Qt, para poder ser testado e usado em modo sem interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np

from .alinhamento import Alinhador
from .banco import Banco
from .detector import Detector, Deteccao
from .inventario import ComparadorInventario, Estado, Evento, Slot

CORES = {  # BGR
    Estado.PRESENTE: (60, 170, 60),
    Estado.AUSENTE: (40, 40, 220),
    Estado.DESLOCADA: (0, 180, 240),
}


@dataclass
class ResultadoQuadro:
    imagem: np.ndarray
    deteccoes: list[Deteccao]
    eventos: list[Evento]
    alinhado: bool
    correspondencias: int
    resumo: dict[str, int]
    faltantes: list[Slot]


class Pipeline:
    def __init__(
        self,
        detector: Detector,
        comparador: ComparadorInventario,
        banco: Banco,
        alinhador: Alinhador | None = None,
        falhas_alinhamento_para_evento: int = 30,
    ):
        self.detector = detector
        self.comparador = comparador
        self.banco = banco
        self.alinhador = alinhador
        self._falhas_alinhamento = 0
        self._limite_falhas = falhas_alinhamento_para_evento

    def processar(self, quadro: np.ndarray, agora: datetime | None = None) -> ResultadoQuadro:
        agora = agora or datetime.now()
        imagem, alinhado, corr = quadro, True, 0

        if self.alinhador is not None:
            res = self.alinhador.alinhar(quadro)
            imagem, alinhado, corr = res.imagem, res.alinhado, res.correspondencias
            if not alinhado:
                self._falhas_alinhamento += 1
                if self._falhas_alinhamento == self._limite_falhas:
                    self.banco.registrar_sistema(
                        f"Falha de alinhamento por {self._limite_falhas} quadros "
                        f"(câmera deslocada ou obstruída?)", agora)
                # Sem alinhamento, os slots não são confiáveis: não atualiza o inventário.
                return ResultadoQuadro(self._anotar(imagem, [], alinhado), [], [], False, corr,
                                       self.comparador.resumo(), self.comparador.faltantes())
            self._falhas_alinhamento = 0

        deteccoes = self.detector.detectar(imagem)
        eventos = self.comparador.atualizar(deteccoes, agora)
        if eventos:
            self.banco.registrar_varios(eventos)

        return ResultadoQuadro(
            imagem=self._anotar(imagem, deteccoes, alinhado),
            deteccoes=deteccoes,
            eventos=eventos,
            alinhado=alinhado,
            correspondencias=corr,
            resumo=self.comparador.resumo(),
            faltantes=self.comparador.faltantes(),
        )

    def _anotar(self, imagem: np.ndarray, deteccoes: list[Deteccao], alinhado: bool) -> np.ndarray:
        saida = imagem.copy()
        for slot in self.comparador.slots.values():
            estado = self.comparador.estado(slot.id)
            x1, y1, x2, y2 = map(int, slot.caixa)
            espessura = 3 if estado == Estado.AUSENTE else 1
            cv2.rectangle(saida, (x1, y1), (x2, y2), CORES[estado], espessura)
            cv2.putText(saida, slot.id, (x1 + 3, y1 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        CORES[estado], 1, cv2.LINE_AA)
        for d in deteccoes:
            x1, y1, x2, y2 = map(int, d.caixa)
            cv2.rectangle(saida, (x1, y1), (x2, y2), (255, 200, 0), 1)
            cv2.putText(saida, f"{d.nome} {d.confianca:.2f}", (x1, max(12, y2 + 14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 200, 0), 1, cv2.LINE_AA)
        if not alinhado:
            cv2.putText(saida, "SEM ALINHAMENTO - verifique a camera", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 40, 220), 2, cv2.LINE_AA)
        return saida
