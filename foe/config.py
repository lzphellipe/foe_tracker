"""Carregamento da configuração (config.yaml) em objetos tipados."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ConfigCamera:
    indice: int = 0
    largura: int = 1280
    altura: int = 720
    fps: int = 15


@dataclass
class ConfigAlinhamento:
    imagem_referencia: str = "dados/referencia.jpg"
    min_correspondencias: int = 25
    max_features: int = 2000
    usar_clahe: bool = True


@dataclass
class ConfigDetector:
    modelo: str = "modelos/ferramentas.pt"
    confianca_minima: float = 0.25
    confianca_aceita: float = 0.60
    dispositivo: str = "cpu"


@dataclass
class ConfigInventario:
    arquivo_slots: str = "dados/slots.json"
    iou_minimo: float = 0.30
    quadros_confirmacao: int = 8
    alarme_ausencia_segundos: int = 300


@dataclass
class ConfigBanco:
    caminho: str = "dados/foe.db"


@dataclass
class ConfigRelatorios:
    pasta_saida: str = "relatorios"


@dataclass
class Config:
    camera: ConfigCamera = field(default_factory=ConfigCamera)
    alinhamento: ConfigAlinhamento = field(default_factory=ConfigAlinhamento)
    detector: ConfigDetector = field(default_factory=ConfigDetector)
    inventario: ConfigInventario = field(default_factory=ConfigInventario)
    banco: ConfigBanco = field(default_factory=ConfigBanco)
    relatorios: ConfigRelatorios = field(default_factory=ConfigRelatorios)


def carregar_config(caminho: str | Path = "config.yaml") -> Config:
    """Lê o YAML; chaves ausentes usam os valores padrão."""
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    return Config(
        camera=ConfigCamera(**dados.get("camera", {})),
        alinhamento=ConfigAlinhamento(**dados.get("alinhamento", {})),
        detector=ConfigDetector(**dados.get("detector", {})),
        inventario=ConfigInventario(**dados.get("inventario", {})),
        banco=ConfigBanco(**dados.get("banco", {})),
        relatorios=ConfigRelatorios(**dados.get("relatorios", {})),
    )
