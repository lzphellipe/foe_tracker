"""Captura de imagens por câmera USB (OpenCV)."""

from __future__ import annotations

import platform

import cv2
import numpy as np

from .config import ConfigCamera


class ErroCamera(RuntimeError):
    pass


class Camera:
    """Wrapper simples sobre cv2.VideoCapture, com reconexão."""

    def __init__(self, cfg: ConfigCamera):
        self.cfg = cfg
        self._cap: cv2.VideoCapture | None = None

    def abrir(self) -> None:
        # No Windows, o backend DirectShow abre câmeras USB mais rápido.
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.cfg.indice, backend)
        if not cap.isOpened():
            raise ErroCamera(f"Não foi possível abrir a câmera {self.cfg.indice}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.largura)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.altura)
        cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
        self._cap = cap

    def ler(self) -> np.ndarray:
        """Retorna um quadro BGR. Tenta reabrir uma vez se a leitura falhar."""
        if self._cap is None:
            self.abrir()
        ok, quadro = self._cap.read()
        if not ok:
            self.fechar()
            self.abrir()
            ok, quadro = self._cap.read()
            if not ok:
                raise ErroCamera("Falha na leitura do quadro")
        return quadro

    def fechar(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self):
        self.abrir()
        return self

    def __exit__(self, *exc):
        self.fechar()
