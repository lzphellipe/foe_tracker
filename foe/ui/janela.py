"""Interface PyQt5: câmera ao vivo, faltantes, indicadores, histórico e exportação."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
from PyQt5.QtCore import QDateTime, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDateTimeEdit, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..banco import Banco
from ..camera import Camera, ErroCamera
from ..inventario import TipoEvento
from ..relatorios import exportar_csv, gerar_relatorio_html
from ..servico import Pipeline, ResultadoQuadro

COR_EVENTO = {
    "RETIRADA": "#d97706", "DEVOLUCAO": "#15803d", "MOVIMENTACAO": "#2563eb",
    "FALHA_DETECCAO": "#7c3aed", "ALARME": "#b91c1c", "SISTEMA": "#475569",
}


class TrabalhadorVisao(QThread):
    """Roda câmera + pipeline fora da thread da interface."""

    quadro_pronto = pyqtSignal(object)   # ResultadoQuadro
    erro = pyqtSignal(str)

    def __init__(self, camera: Camera, pipeline: Pipeline):
        super().__init__()
        self.camera = camera
        self.pipeline = pipeline
        self._rodando = False

    def run(self):
        self._rodando = True
        try:
            self.camera.abrir()
            while self._rodando:
                quadro = self.camera.ler()
                self.quadro_pronto.emit(self.pipeline.processar(quadro))
        except ErroCamera as e:
            self.erro.emit(str(e))
        finally:
            self.camera.fechar()

    def parar(self):
        self._rodando = False
        self.wait(3000)


class Indicador(QLabel):
    def __init__(self, titulo: str, cor: str):
        super().__init__()
        self.titulo, self.cor = titulo, cor
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(64)
        self.definir("—")

    def definir(self, valor):
        self.setText(f"<div style='font-size:26px;font-weight:bold;color:{self.cor}'>{valor}</div>"
                     f"<div style='font-size:11px;color:#555'>{self.titulo}</div>")


class JanelaPrincipal(QMainWindow):
    def __init__(self, camera: Camera, pipeline: Pipeline, banco: Banco, pasta_relatorios: str):
        super().__init__()
        self.banco = banco
        self.pasta_relatorios = Path(pasta_relatorios)
        self.setWindowTitle("FOE Tracker — Controle de Ferramentas")
        self.resize(1360, 800)

        abas = QTabWidget()
        abas.addTab(self._aba_monitoramento(), "Monitoramento")
        abas.addTab(self._aba_historico(), "Histórico e relatórios")
        abas.currentChanged.connect(lambda i: i == 1 and self._carregar_historico())
        self.setCentralWidget(abas)

        self.trabalhador = TrabalhadorVisao(camera, pipeline)
        self.trabalhador.quadro_pronto.connect(self._ao_receber_quadro)
        self.trabalhador.erro.connect(lambda m: QMessageBox.critical(self, "Câmera", m))
        self.trabalhador.start()

    # ---------------- Aba 1 ----------------
    def _aba_monitoramento(self) -> QWidget:
        self.video = QLabel("Aguardando câmera…")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(800, 450)
        self.video.setStyleSheet("background:#111;color:#aaa")

        self.ind_total = Indicador("Total", "#334155")
        self.ind_presentes = Indicador("Presentes", "#15803d")
        self.ind_ausentes = Indicador("Ausentes", "#b91c1c")
        self.ind_deslocadas = Indicador("Fora do slot", "#d97706")
        grade = QGridLayout()
        for i, w in enumerate([self.ind_total, self.ind_presentes, self.ind_ausentes, self.ind_deslocadas]):
            grade.addWidget(w, i // 2, i % 2)
        caixa_ind = QGroupBox("Estado do inventário")
        caixa_ind.setLayout(grade)

        self.status_alinhamento = QLabel()
        self.faltantes = QListWidget()
        caixa_falt = QGroupBox("Ferramentas faltantes")
        lf = QVBoxLayout(caixa_falt)
        lf.addWidget(self.faltantes)

        self.eventos_recentes = QListWidget()
        btn_reconhecer = QPushButton("Reconhecer alarmes")
        btn_reconhecer.clicked.connect(self._reconhecer_alarmes)
        caixa_ev = QGroupBox("Eventos recentes")
        le = QVBoxLayout(caixa_ev)
        le.addWidget(self.eventos_recentes)
        le.addWidget(btn_reconhecer)

        lateral = QVBoxLayout()
        lateral.addWidget(caixa_ind)
        lateral.addWidget(self.status_alinhamento)
        lateral.addWidget(caixa_falt, 2)
        lateral.addWidget(caixa_ev, 3)

        raiz = QWidget()
        h = QHBoxLayout(raiz)
        h.addWidget(self.video, 3)
        h.addLayout(lateral, 1)
        return raiz

    def _ao_receber_quadro(self, r: ResultadoQuadro):
        rgb = cv2.cvtColor(r.imagem, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        self.video.setPixmap(QPixmap.fromImage(img).scaled(
            self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self.ind_total.definir(r.resumo["TOTAL"])
        self.ind_presentes.definir(r.resumo["PRESENTE"])
        self.ind_ausentes.definir(r.resumo["AUSENTE"])
        self.ind_deslocadas.definir(r.resumo["DESLOCADA"])
        if self.trabalhador.pipeline.alinhador is None:
            self.status_alinhamento.setText("<span style='color:#555'>● Alinhamento desativado</span>")
        elif r.alinhado:
            self.status_alinhamento.setText(f"<span style='color:#15803d'>● Alinhado</span> "
                                            f"({r.correspondencias} pontos)")
        else:
            self.status_alinhamento.setText("<span style='color:#b91c1c'>● Sem alinhamento — "
                                            "inventário congelado</span>")

        self.faltantes.clear()
        for s in r.faltantes:
            desde = self.trabalhador.pipeline.comparador.ausente_desde(s.id)
            self.faltantes.addItem(f"{s.id} — {s.nome}  (desde {desde:%H:%M:%S})" if desde else s.id)

        for e in r.eventos:
            item = QListWidgetItem(f"{e.momento:%H:%M:%S}  {e.tipo.value:<14} {e.slot_id}  {e.ferramenta}")
            item.setForeground(QColor(COR_EVENTO.get(e.tipo.value, "#000")))
            self.eventos_recentes.insertItem(0, item)
            if e.tipo == TipoEvento.ALARME:
                QApplication.beep()
        while self.eventos_recentes.count() > 200:
            self.eventos_recentes.takeItem(self.eventos_recentes.count() - 1)

    def _reconhecer_alarmes(self):
        pendentes = [e for e in self.banco.eventos(tipos=["ALARME"]) if not e.reconhecido]
        for e in pendentes:
            self.banco.reconhecer_alarme(e.id)
        QMessageBox.information(self, "Alarmes", f"{len(pendentes)} alarme(s) reconhecido(s).")

    # ---------------- Aba 2 ----------------
    def _aba_historico(self) -> QWidget:
        agora = QDateTime.currentDateTime()
        self.f_inicio = QDateTimeEdit(agora.addDays(-1))
        self.f_fim = QDateTimeEdit(agora)
        for f in (self.f_inicio, self.f_fim):
            f.setCalendarPopup(True)
            f.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.f_tipo = QComboBox()
        self.f_tipo.addItems(["Todos", "RETIRADA", "DEVOLUCAO", "MOVIMENTACAO",
                              "FALHA_DETECCAO", "ALARME", "SISTEMA"])

        btn_filtrar = QPushButton("Filtrar")
        btn_csv = QPushButton("Exportar CSV")
        btn_rel = QPushButton("Gerar relatório")
        btn_filtrar.clicked.connect(self._carregar_historico)
        btn_csv.clicked.connect(self._exportar_csv)
        btn_rel.clicked.connect(self._gerar_relatorio)

        filtros = QHBoxLayout()
        for rotulo, w in [("De", self.f_inicio), ("Até", self.f_fim), ("Tipo", self.f_tipo)]:
            filtros.addWidget(QLabel(rotulo))
            filtros.addWidget(w)
        filtros.addStretch()
        for b in (btn_filtrar, btn_csv, btn_rel):
            filtros.addWidget(b)

        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(["Momento", "Tipo", "ID", "Ferramenta", "Confiança", "Detalhe"])
        self.tabela.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)

        raiz = QWidget()
        v = QVBoxLayout(raiz)
        v.addLayout(filtros)
        v.addWidget(self.tabela)
        return raiz

    def _filtros(self):
        inicio = self.f_inicio.dateTime().toPyDateTime()
        fim = self.f_fim.dateTime().toPyDateTime()
        tipo = self.f_tipo.currentText()
        return inicio, fim, None if tipo == "Todos" else [tipo]

    def _carregar_historico(self):
        inicio, fim, tipos = self._filtros()
        eventos = self.banco.eventos(inicio=inicio, fim=fim, tipos=tipos, limite=5000)
        self.tabela.setRowCount(len(eventos))
        for i, e in enumerate(eventos):
            valores = [f"{e.momento:%d/%m/%Y %H:%M:%S}", e.tipo, e.ferramenta_id or "—",
                       e.ferramenta or "—", f"{e.confianca:.2f}" if e.confianca is not None else "—",
                       e.detalhe]
            for j, v in enumerate(valores):
                item = QTableWidgetItem(v)
                if j == 1:
                    item.setForeground(QColor(COR_EVENTO.get(e.tipo, "#000")))
                self.tabela.setItem(i, j, item)

    def _exportar_csv(self):
        inicio, fim, tipos = self._filtros()
        padrao = self.pasta_relatorios / f"eventos_{datetime.now():%Y%m%d_%H%M}.csv"
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", str(padrao), "CSV (*.csv)")
        if caminho:
            exportar_csv(self.banco.eventos(inicio=inicio, fim=fim, tipos=tipos), caminho)
            QMessageBox.information(self, "Exportação", f"Arquivo salvo em:\n{caminho}")

    def _gerar_relatorio(self):
        inicio, fim, _ = self._filtros()
        caminho = gerar_relatorio_html(
            self.banco, inicio, fim, self.pasta_relatorios / f"relatorio_{datetime.now():%Y%m%d_%H%M}.html")
        QMessageBox.information(self, "Relatório", f"Relatório gerado em:\n{caminho}")

    def closeEvent(self, ev):
        self.trabalhador.parar()
        self.banco.fechar()
        super().closeEvent(ev)
