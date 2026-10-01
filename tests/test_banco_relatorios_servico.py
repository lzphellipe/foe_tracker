import csv
from datetime import timedelta

import numpy as np
from conftest import T0, det, instante

from foe.banco import Banco
from foe.inventario import ComparadorInventario, Evento, TipoEvento
from foe.relatorios import exportar_csv, gerar_relatorio_html, resumir
from foe.servico import Pipeline


def banco_com(slots):
    b = Banco(":memory:")
    b.sincronizar_ferramentas(slots)
    return b


def test_registrar_e_filtrar(slots):
    b = banco_com(slots)
    b.registrar_varios([
        Evento(TipoEvento.RETIRADA, "ALI-01", "Alicate universal", instante(0)),
        Evento(TipoEvento.DEVOLUCAO, "ALI-01", "Alicate universal", instante(90), 0.91),
        Evento(TipoEvento.ALARME, "CHV-10MM-02", "Chave combinada 10 mm", instante(200)),
    ])
    b.registrar_sistema("teste", instante(5))
    assert len(b.eventos()) == 4
    assert [e.tipo for e in b.eventos(tipos=["ALARME"])] == ["ALARME"]
    assert len(b.eventos(ferramenta_id="ALI-01")) == 2
    assert len(b.eventos(inicio=instante(60), fim=instante(120))) == 1

    alarme = b.eventos(tipos=["ALARME"])[0]
    b.reconhecer_alarme(alarme.id)
    assert b.eventos(tipos=["ALARME"])[0].reconhecido


def test_csv_e_relatorio(slots, tmp_path):
    b = banco_com(slots)
    b.registrar_varios([
        Evento(TipoEvento.RETIRADA, "ALI-01", "Alicate universal", instante(0)),
        Evento(TipoEvento.DEVOLUCAO, "ALI-01", "Alicate universal", instante(120), 0.88),
        Evento(TipoEvento.RETIRADA, "CHV-10MM-02", "Chave combinada 10 mm", instante(130)),
    ])
    eventos = b.eventos()

    arq = exportar_csv(eventos, tmp_path / "ev.csv")
    with arq.open(encoding="utf-8-sig") as f:
        linhas = list(csv.reader(f, delimiter=";"))
    assert linhas[0][2] == "tipo" and len(linhas) == 4
    assert "0,88" in [c for l in linhas for c in l]

    r = resumir(eventos, T0, instante(300))
    assert r.tempo_medio_fora["ALI-01 — Alicate universal"] == timedelta(seconds=120)
    assert r.nao_devolvidas == ["CHV-10MM-02 — Chave combinada 10 mm"]

    html = gerar_relatorio_html(b, T0, instante(300), tmp_path / "rel.html").read_text(encoding="utf-8")
    assert "CHV-10MM-02" in html and "00:02:00" in html


class DetectorFalso:
    def __init__(self):
        self.saida = []

    def detectar(self, imagem):
        return self.saida


class AlinhadorFalho:
    def alinhar(self, quadro):
        from foe.alinhamento import ResultadoAlinhamento
        return ResultadoAlinhamento(quadro, None, 0, False)


def test_pipeline_persiste_eventos(slots, cfg_inv, cfg_det):
    b = banco_com(slots)
    detector = DetectorFalso()
    pipe = Pipeline(detector, ComparadorInventario(slots, cfg_inv, cfg_det), b)
    quadro = np.zeros((200, 300, 3), np.uint8)

    detector.saida = [det(slots[0]), det(slots[2])]
    for i in range(3):
        r = pipe.processar(quadro, instante(i))
    assert [s.id for s in r.faltantes] == ["ALI-01"]
    assert [e.tipo for e in b.eventos()] == ["RETIRADA"]
    assert r.imagem.shape == quadro.shape


def test_sem_alinhamento_congela_inventario(slots, cfg_inv, cfg_det):
    b = banco_com(slots)
    pipe = Pipeline(DetectorFalso(), ComparadorInventario(slots, cfg_inv, cfg_det), b,
                    alinhador=AlinhadorFalho(), falhas_alinhamento_para_evento=5)
    quadro = np.zeros((200, 300, 3), np.uint8)
    for i in range(10):
        r = pipe.processar(quadro, instante(i))
    # Detector não vê nada, mas sem alinhamento nada vira "retirada"
    assert r.faltantes == [] and not r.alinhado
    assert [e.tipo for e in b.eventos()] == ["SISTEMA"]
