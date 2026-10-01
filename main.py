"""Ponto de entrada do FOE Tracker.

Uso:
    python main.py capturar-referencia   # fotografa o painel completo
    python main.py gerar-slots           # cria dados/slots.json com o YOLO
    python main.py executar              # abre a interface de monitoramento
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

from foe.config import carregar_config


def capturar_referencia(cfg) -> None:
    from foe.camera import Camera

    destino = Path(cfg.alinhamento.imagem_referencia)
    destino.parent.mkdir(parents=True, exist_ok=True)
    print("Posicione TODAS as ferramentas nos slots. [ESPAÇO] captura, [ESC] cancela.")
    with Camera(cfg.camera) as cam:
        while True:
            quadro = cam.ler()
            cv2.imshow("Referencia", quadro)
            tecla = cv2.waitKey(1) & 0xFF
            if tecla == 27:
                break
            if tecla == 32:
                cv2.imwrite(str(destino), quadro)
                print(f"Referência salva em {destino}")
                break
    cv2.destroyAllWindows()


def gerar_slots(cfg) -> None:
    from foe.detector import DetectorYOLO
    from foe.inventario import salvar_slots, slots_de_deteccoes

    ref = cv2.imread(cfg.alinhamento.imagem_referencia)
    if ref is None:
        sys.exit("Imagem de referência não encontrada. Rode 'capturar-referencia' antes.")
    deteccoes = [d for d in DetectorYOLO(cfg.detector).detectar(ref)
                 if d.confianca >= cfg.detector.confianca_aceita]
    slots = slots_de_deteccoes(deteccoes)
    salvar_slots(slots, cfg.inventario.arquivo_slots)
    print(f"{len(slots)} slots gravados em {cfg.inventario.arquivo_slots}.")
    print("Revise o arquivo e troque os IDs genéricos (FER-001…) pelos códigos do inventário FOE.")


def executar(cfg) -> None:
    from PyQt5.QtWidgets import QApplication

    from foe.alinhamento import Alinhador
    from foe.banco import Banco
    from foe.camera import Camera
    from foe.detector import DetectorYOLO
    from foe.inventario import ComparadorInventario, carregar_slots
    from foe.servico import Pipeline
    from foe.ui.janela import JanelaPrincipal

    ref = cv2.imread(cfg.alinhamento.imagem_referencia)
    if ref is None:
        sys.exit("Imagem de referência não encontrada. Rode 'capturar-referencia' antes.")
    slots = carregar_slots(cfg.inventario.arquivo_slots)

    banco = Banco(cfg.banco.caminho)
    banco.sincronizar_ferramentas(slots)
    banco.registrar_sistema(f"Sistema iniciado com {len(slots)} ferramentas")

    pipeline = Pipeline(
        detector=DetectorYOLO(cfg.detector),
        comparador=ComparadorInventario(slots, cfg.inventario, cfg.detector),
        banco=banco,
        alinhador=Alinhador(ref, cfg.alinhamento),
    )

    app = QApplication(sys.argv)
    janela = JanelaPrincipal(Camera(cfg.camera), pipeline, banco, cfg.relatorios.pasta_saida)
    janela.show()
    sys.exit(app.exec_())


def main() -> None:
    p = argparse.ArgumentParser(description="FOE Tracker")
    p.add_argument("comando", choices=["capturar-referencia", "gerar-slots", "executar"])
    p.add_argument("--config", default="config.yaml")
    args = p.parse_args()
    cfg = carregar_config(args.config)
    {"capturar-referencia": capturar_referencia, "gerar-slots": gerar_slots,
     "executar": executar}[args.comando](cfg)


if __name__ == "__main__":
    main()
