"""Exportação CSV e relatórios de período."""

from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .banco import Banco, RegistroEvento

CAMPOS_CSV = ["id", "momento", "tipo", "ferramenta_id", "ferramenta", "confianca", "detalhe", "reconhecido"]


def exportar_csv(eventos: list[RegistroEvento], caminho: str | Path) -> Path:
    """CSV com ';' e UTF-8 com BOM, para abrir direto no Excel em pt-BR."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(CAMPOS_CSV)
        for e in eventos:
            w.writerow([
                e.id, e.momento.isoformat(sep=" "), e.tipo, e.ferramenta_id or "", e.ferramenta or "",
                f"{e.confianca:.2f}".replace(".", ",") if e.confianca is not None else "",
                e.detalhe, "sim" if e.reconhecido else "não",
            ])
    return caminho


@dataclass
class ResumoPeriodo:
    inicio: datetime
    fim: datetime
    por_tipo: Counter = field(default_factory=Counter)
    retiradas_por_ferramenta: Counter = field(default_factory=Counter)
    tempo_medio_fora: dict[str, timedelta] = field(default_factory=dict)
    nao_devolvidas: list[str] = field(default_factory=list)
    alarmes_pendentes: int = 0


def resumir(eventos: list[RegistroEvento], inicio: datetime, fim: datetime) -> ResumoPeriodo:
    r = ResumoPeriodo(inicio, fim)
    em_ordem = sorted(eventos, key=lambda e: (e.momento, e.id))
    aberta: dict[str, datetime] = {}
    duracoes: dict[str, list[timedelta]] = defaultdict(list)

    for e in em_ordem:
        r.por_tipo[e.tipo] += 1
        if e.tipo == "ALARME" and not e.reconhecido:
            r.alarmes_pendentes += 1
        if not e.ferramenta_id:
            continue
        rotulo = f"{e.ferramenta_id} — {e.ferramenta}"
        if e.tipo == "RETIRADA":
            r.retiradas_por_ferramenta[rotulo] += 1
            aberta[rotulo] = e.momento
        elif e.tipo == "DEVOLUCAO" and rotulo in aberta:
            duracoes[rotulo].append(e.momento - aberta.pop(rotulo))

    r.tempo_medio_fora = {k: sum(v, timedelta()) / len(v) for k, v in duracoes.items()}
    r.nao_devolvidas = sorted(aberta)
    return r


def _fmt(td: timedelta) -> str:
    s = int(td.total_seconds())
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def gerar_relatorio_html(banco: Banco, inicio: datetime, fim: datetime, caminho: str | Path) -> Path:
    eventos = banco.eventos(inicio=inicio, fim=fim)
    r = resumir(eventos, inicio, fim)
    esc = html.escape

    def tabela(cab, linhas):
        th = "".join(f"<th>{esc(c)}</th>" for c in cab)
        tr = "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in l) + "</tr>" for l in linhas)
        return f"<table><tr>{th}</tr>{tr or '<tr><td colspan=9>—</td></tr>'}</table>"

    corpo = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Relatório FOE</title>
<style>
body{{font-family:Arial,sans-serif;margin:32px;color:#222}}
h1{{font-size:22px}} h2{{font-size:16px;margin-top:28px;border-bottom:1px solid #ccc}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #ccc;padding:4px 8px;text-align:left}} th{{background:#f0f0f0}}
.alerta{{color:#b00020;font-weight:bold}}
</style></head><body>
<h1>Relatório de controle de ferramentas — F.O.E.</h1>
<p>Período: {inicio:%d/%m/%Y %H:%M} a {fim:%d/%m/%Y %H:%M} · Gerado em {datetime.now():%d/%m/%Y %H:%M}</p>
<h2>Eventos por tipo</h2>
{tabela(["Tipo", "Quantidade"], sorted(r.por_tipo.items()))}
<h2>Ferramentas não devolvidas no período</h2>
<p class="{'alerta' if r.nao_devolvidas else ''}">{len(r.nao_devolvidas)} ferramenta(s)</p>
{tabela(["Ferramenta"], [[n] for n in r.nao_devolvidas])}
<h2>Retiradas por ferramenta</h2>
{tabela(["Ferramenta", "Retiradas", "Tempo médio fora"],
        [[k, v, _fmt(r.tempo_medio_fora[k]) if k in r.tempo_medio_fora else "—"]
         for k, v in r.retiradas_por_ferramenta.most_common()])}
<h2>Alarmes pendentes de reconhecimento: {r.alarmes_pendentes}</h2>
<h2>Eventos</h2>
{tabela(["Momento", "Tipo", "Ferramenta", "Confiança", "Detalhe"],
        [[f"{e.momento:%d/%m %H:%M:%S}", e.tipo, e.ferramenta or "—",
          f"{e.confianca:.2f}" if e.confianca is not None else "—", e.detalhe] for e in eventos])}
</body></html>"""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(corpo, encoding="utf-8")
    return caminho
