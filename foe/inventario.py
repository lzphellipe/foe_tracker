"""Comparação entre o estado de referência (slots) e o estado atual.

Cada ferramenta tem um *slot*: a caixa onde ela deve estar na imagem de
referência. A cada quadro, as detecções do YOLO são associadas aos slots
(mesma classe + IoU mínimo). Para evitar falsos alarmes por oclusão
momentânea (mão do técnico passando, reflexo), uma mudança de estado só é
confirmada após N quadros consecutivos com a mesma observação (histerese).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from .config import ConfigDetector, ConfigInventario
from .detector import Caixa, Deteccao


class Estado(str, Enum):
    PRESENTE = "PRESENTE"
    AUSENTE = "AUSENTE"
    DESLOCADA = "DESLOCADA"  # vista na bancada, mas fora do seu slot


class Observacao(str, Enum):
    PRESENTE = "PRESENTE"
    AUSENTE = "AUSENTE"
    DESLOCADA = "DESLOCADA"
    INCERTA = "INCERTA"  # detectada com confiança baixa


class TipoEvento(str, Enum):
    RETIRADA = "RETIRADA"
    DEVOLUCAO = "DEVOLUCAO"
    MOVIMENTACAO = "MOVIMENTACAO"
    FALHA_DETECCAO = "FALHA_DETECCAO"
    ALARME = "ALARME"


@dataclass(frozen=True)
class Slot:
    id: str          # ex.: "CHV-10MM-01" (identificador do inventário FOE)
    nome: str        # ex.: "Chave combinada 10 mm"
    classe_id: int   # classe YOLO correspondente
    caixa: Caixa


@dataclass(frozen=True)
class Evento:
    tipo: TipoEvento
    slot_id: str
    ferramenta: str
    momento: datetime
    confianca: float | None = None
    detalhe: str = ""


@dataclass
class _Rastreio:
    confirmado: Estado = Estado.PRESENTE
    candidato: Observacao | None = None
    contagem: int = 0
    contagem_incerta: int = 0
    ausente_desde: datetime | None = None
    alarmado: bool = False
    ultima_confianca: float | None = None


def iou(a: Caixa, b: Caixa) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    uniao = area_a + area_b - inter
    return inter / uniao if uniao > 0 else 0.0


def carregar_slots(caminho: str | Path) -> list[Slot]:
    """Formato: [{"id": ..., "nome": ..., "classe_id": ..., "caixa": [x1,y1,x2,y2]}]"""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return [Slot(d["id"], d["nome"], int(d["classe_id"]), tuple(d["caixa"])) for d in dados]


def salvar_slots(slots: list[Slot], caminho: str | Path) -> None:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text(
        json.dumps(
            [{"id": s.id, "nome": s.nome, "classe_id": s.classe_id, "caixa": list(s.caixa)} for s in slots],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def slots_de_deteccoes(deteccoes: list[Deteccao], prefixo: str = "FER") -> list[Slot]:
    """Gera o estado de referência a partir das detecções do painel completo."""
    ordenadas = sorted(deteccoes, key=lambda d: (d.caixa[1], d.caixa[0]))
    return [
        Slot(f"{prefixo}-{i:03d}", d.nome, d.classe_id, d.caixa)
        for i, d in enumerate(ordenadas, start=1)
    ]


class ComparadorInventario:
    def __init__(self, slots: list[Slot], cfg_inv: ConfigInventario, cfg_det: ConfigDetector):
        self.slots = {s.id: s for s in slots}
        self.cfg = cfg_inv
        self.conf_aceita = cfg_det.confianca_aceita
        self._rastreio = {s.id: _Rastreio() for s in slots}

    # ---------- consulta ----------
    def estado(self, slot_id: str) -> Estado:
        return self._rastreio[slot_id].confirmado

    def faltantes(self) -> list[Slot]:
        return [self.slots[i] for i, r in self._rastreio.items() if r.confirmado == Estado.AUSENTE]

    def resumo(self) -> dict[str, int]:
        cont = {e.value: 0 for e in Estado}
        for r in self._rastreio.values():
            cont[r.confirmado.value] += 1
        cont["TOTAL"] = len(self._rastreio)
        return cont

    def ausente_desde(self, slot_id: str) -> datetime | None:
        return self._rastreio[slot_id].ausente_desde

    # ---------- processamento ----------
    def _observar(self, deteccoes: list[Deteccao]) -> dict[str, tuple[Observacao, float | None]]:
        # 1) cada detecção vai para o slot de mesma classe com maior IoU
        melhor_por_slot: dict[str, Deteccao] = {}
        soltas: list[Deteccao] = []
        for d in deteccoes:
            candidatos = [
                (iou(d.caixa, s.caixa), s.id)
                for s in self.slots.values()
                if s.classe_id == d.classe_id
            ]
            candidatos = [c for c in candidatos if c[0] >= self.cfg.iou_minimo]
            if not candidatos:
                soltas.append(d)
                continue
            _, sid = max(candidatos)
            atual = melhor_por_slot.get(sid)
            if atual is None or d.confianca > atual.confianca:
                melhor_por_slot[sid] = d

        # 2) classifica cada slot
        soltas_confiaveis = [d for d in soltas if d.confianca >= self.conf_aceita]
        obs: dict[str, tuple[Observacao, float | None]] = {}
        for sid, slot in self.slots.items():
            d = melhor_por_slot.get(sid)
            if d is not None:
                tipo = Observacao.PRESENTE if d.confianca >= self.conf_aceita else Observacao.INCERTA
                obs[sid] = (tipo, d.confianca)
                continue
            fora = next((x for x in soltas_confiaveis if x.classe_id == slot.classe_id), None)
            if fora is not None:
                soltas_confiaveis.remove(fora)
                obs[sid] = (Observacao.DESLOCADA, fora.confianca)
            else:
                obs[sid] = (Observacao.AUSENTE, None)
        return obs

    def atualizar(self, deteccoes: list[Deteccao], agora: datetime | None = None) -> list[Evento]:
        agora = agora or datetime.now()
        eventos: list[Evento] = []
        n = self.cfg.quadros_confirmacao

        for sid, (obs, conf) in self._observar(deteccoes).items():
            r = self._rastreio[sid]
            slot = self.slots[sid]
            r.ultima_confianca = conf

            if obs == Observacao.INCERTA:
                # Não altera o estado; registra falha se persistir
                r.contagem_incerta += 1
                if r.contagem_incerta == n:
                    eventos.append(Evento(TipoEvento.FALHA_DETECCAO, sid, slot.nome, agora, conf,
                                          f"confiança abaixo de {self.conf_aceita:.2f} por {n} quadros"))
                r.candidato, r.contagem = None, 0
            else:
                r.contagem_incerta = 0
                novo = Estado(obs.value)
                if novo == r.confirmado:
                    r.candidato, r.contagem = None, 0
                else:
                    if r.candidato == obs:
                        r.contagem += 1
                    else:
                        r.candidato, r.contagem = obs, 1
                    if r.contagem >= n:
                        eventos.extend(self._transicao(sid, r, novo, conf, agora))

            # Alarme por ausência prolongada
            if (r.confirmado == Estado.AUSENTE and not r.alarmado and r.ausente_desde
                    and (agora - r.ausente_desde).total_seconds() >= self.cfg.alarme_ausencia_segundos):
                r.alarmado = True
                eventos.append(Evento(TipoEvento.ALARME, sid, slot.nome, agora, None,
                                      f"ausente há mais de {self.cfg.alarme_ausencia_segundos} s"))
        return eventos

    def _transicao(self, sid, r: _Rastreio, novo: Estado, conf, agora) -> list[Evento]:
        slot = self.slots[sid]
        anterior = r.confirmado
        r.confirmado, r.candidato, r.contagem = novo, None, 0
        eventos = []
        if novo == Estado.AUSENTE:
            r.ausente_desde, r.alarmado = agora, False
            eventos.append(Evento(TipoEvento.RETIRADA, sid, slot.nome, agora, None,
                                  f"{anterior.value} -> AUSENTE"))
        elif novo == Estado.PRESENTE:
            r.ausente_desde, r.alarmado = None, False
            tipo = TipoEvento.DEVOLUCAO if anterior == Estado.AUSENTE else TipoEvento.MOVIMENTACAO
            eventos.append(Evento(tipo, sid, slot.nome, agora, conf, f"{anterior.value} -> PRESENTE"))
        else:  # DESLOCADA: está na bancada, mas fora do slot
            r.ausente_desde, r.alarmado = None, False
            tipo = TipoEvento.DEVOLUCAO if anterior == Estado.AUSENTE else TipoEvento.MOVIMENTACAO
            eventos.append(Evento(tipo, sid, slot.nome, agora, conf,
                                  f"{anterior.value} -> DESLOCADA (fora do slot)"))
        return eventos
