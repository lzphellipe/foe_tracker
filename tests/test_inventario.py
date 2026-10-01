from conftest import det, instante

from foe.inventario import ComparadorInventario, Estado, TipoEvento, iou


def todas(slots, **kw):
    return [det(s, **kw) for s in slots]


def rodar(comp, deteccoes, quadros, inicio=0):
    eventos = []
    for i in range(quadros):
        eventos += comp.atualizar(deteccoes, instante(inicio + i))
    return eventos


def test_iou():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert abs(iou((0, 0, 10, 10), (5, 0, 15, 10)) - 1 / 3) < 1e-9


def test_estado_inicial_estavel_sem_eventos(slots, cfg_inv, cfg_det):
    comp = ComparadorInventario(slots, cfg_inv, cfg_det)
    assert rodar(comp, todas(slots), 10) == []
    assert comp.resumo()["PRESENTE"] == 3


def test_oclusao_breve_nao_gera_retirada(slots, cfg_inv, cfg_det):
    comp = ComparadorInventario(slots, cfg_inv, cfg_det)
    sem_alicate = [det(slots[0]), det(slots[2])]
    eventos = rodar(comp, sem_alicate, 2) + rodar(comp, todas(slots), 5, inicio=2)
    assert eventos == []
    assert comp.estado("ALI-01") == Estado.PRESENTE


def test_retirada_e_devolucao(slots, cfg_inv, cfg_det):
    comp = ComparadorInventario(slots, cfg_inv, cfg_det)
    sem_alicate = [det(slots[0]), det(slots[2])]
    ev = rodar(comp, sem_alicate, 3)
    assert [(e.tipo, e.slot_id) for e in ev] == [(TipoEvento.RETIRADA, "ALI-01")]
    assert [s.id for s in comp.faltantes()] == ["ALI-01"]

    ev = rodar(comp, todas(slots), 3, inicio=3)
    assert [(e.tipo, e.slot_id) for e in ev] == [(TipoEvento.DEVOLUCAO, "ALI-01")]
    assert comp.faltantes() == []


def test_alarme_uma_unica_vez(slots, cfg_inv, cfg_det):
    comp = ComparadorInventario(slots, cfg_inv, cfg_det)
    sem_alicate = [det(slots[0]), det(slots[2])]
    rodar(comp, sem_alicate, 3)                           # retirada confirmada em t=2
    ev = rodar(comp, sem_alicate, 100, inicio=3)          # até t=102
    alarmes = [e for e in ev if e.tipo == TipoEvento.ALARME]
    assert len(alarmes) == 1
    assert alarmes[0].momento == instante(62)             # 60 s após t=2


def test_confianca_baixa_gera_falha_sem_mudar_estado(slots, cfg_inv, cfg_det):
    comp = ComparadorInventario(slots, cfg_inv, cfg_det)
    fraca = [det(slots[0]), det(slots[1], conf=0.4), det(slots[2])]
    ev = rodar(comp, fraca, 5)
    assert [e.tipo for e in ev] == [TipoEvento.FALHA_DETECCAO]
    assert comp.estado("ALI-01") == Estado.PRESENTE


def test_ferramenta_fora_do_slot_gera_movimentacao(slots, cfg_inv, cfg_det):
    comp = ComparadorInventario(slots, cfg_inv, cfg_det)
    deslocado = [det(slots[0]), det(slots[1], dx=300), det(slots[2])]
    ev = rodar(comp, deslocado, 3)
    assert [(e.tipo, e.slot_id) for e in ev] == [(TipoEvento.MOVIMENTACAO, "ALI-01")]
    assert comp.estado("ALI-01") == Estado.DESLOCADA
    assert comp.faltantes() == []  # está na bancada; não conta como faltante


def test_ferramentas_iguais_sao_distinguidas_pelo_slot(slots, cfg_inv, cfg_det):
    comp = ComparadorInventario(slots, cfg_inv, cfg_det)
    so_primeira_chave = [det(slots[0]), det(slots[1])]
    ev = rodar(comp, so_primeira_chave, 3)
    assert [(e.tipo, e.slot_id) for e in ev] == [(TipoEvento.RETIRADA, "CHV-10MM-02")]
