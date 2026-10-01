"""Persistência em SQLite: cadastro de ferramentas e log de eventos."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .inventario import Evento, Slot

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ferramentas (
    id          TEXT PRIMARY KEY,          -- identificador FOE (ex.: CHV-10MM-01)
    nome        TEXT NOT NULL,
    classe_id   INTEGER NOT NULL,          -- classe do modelo YOLO
    caixa       TEXT NOT NULL,             -- JSON [x1,y1,x2,y2] na imagem de referência
    ativo       INTEGER NOT NULL DEFAULT 1,
    cadastrada_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eventos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    momento       TEXT NOT NULL,           -- ISO 8601
    tipo          TEXT NOT NULL CHECK (tipo IN
                  ('RETIRADA','DEVOLUCAO','MOVIMENTACAO','FALHA_DETECCAO','ALARME','SISTEMA')),
    ferramenta_id TEXT REFERENCES ferramentas(id),  -- NULL para eventos de sistema
    ferramenta    TEXT,
    confianca     REAL,
    detalhe       TEXT,
    reconhecido   INTEGER NOT NULL DEFAULT 0     -- alarme confirmado pelo operador
);

CREATE INDEX IF NOT EXISTS ix_eventos_momento ON eventos(momento);
CREATE INDEX IF NOT EXISTS ix_eventos_tipo    ON eventos(tipo);
CREATE INDEX IF NOT EXISTS ix_eventos_ferr    ON eventos(ferramenta_id);
"""


@dataclass
class RegistroEvento:
    id: int
    momento: datetime
    tipo: str
    ferramenta_id: str | None
    ferramenta: str | None
    confianca: float | None
    detalhe: str
    reconhecido: bool


class Banco:
    """Acesso ao SQLite, seguro para uso a partir da thread de visão e da UI."""

    def __init__(self, caminho: str | Path):
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(caminho), check_same_thread=False)
        self._con.execute("PRAGMA foreign_keys = ON")
        self._con.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.Lock()
        with self._lock, self._con:
            self._con.executescript(ESQUEMA)

    def fechar(self) -> None:
        self._con.close()

    # ---------- ferramentas ----------
    def sincronizar_ferramentas(self, slots: list[Slot]) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._con:
            self._con.execute("UPDATE ferramentas SET ativo = 0")
            self._con.executemany(
                """INSERT INTO ferramentas (id, nome, classe_id, caixa, ativo, cadastrada_em)
                   VALUES (?, ?, ?, ?, 1, ?)
                   ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, classe_id=excluded.classe_id,
                                                 caixa=excluded.caixa, ativo=1""",
                [(s.id, s.nome, s.classe_id, json.dumps(list(s.caixa)), agora) for s in slots],
            )

    # ---------- eventos ----------
    def registrar(self, evento: Evento) -> int:
        return self.registrar_varios([evento])[0]

    def registrar_varios(self, eventos: list[Evento]) -> list[int]:
        ids = []
        with self._lock, self._con:
            for e in eventos:
                cur = self._con.execute(
                    """INSERT INTO eventos (momento, tipo, ferramenta_id, ferramenta, confianca, detalhe)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (e.momento.isoformat(timespec="seconds"), e.tipo.value,
                     e.slot_id or None, e.ferramenta, e.confianca, e.detalhe),
                )
                ids.append(cur.lastrowid)
        return ids

    def registrar_sistema(self, detalhe: str, momento: datetime | None = None) -> None:
        with self._lock, self._con:
            self._con.execute(
                "INSERT INTO eventos (momento, tipo, detalhe) VALUES (?, 'SISTEMA', ?)",
                ((momento or datetime.now()).isoformat(timespec="seconds"), detalhe),
            )

    def reconhecer_alarme(self, evento_id: int) -> None:
        with self._lock, self._con:
            self._con.execute("UPDATE eventos SET reconhecido = 1 WHERE id = ?", (evento_id,))

    def eventos(
        self,
        inicio: datetime | None = None,
        fim: datetime | None = None,
        tipos: list[str] | None = None,
        ferramenta_id: str | None = None,
        limite: int | None = None,
    ) -> list[RegistroEvento]:
        sql = "SELECT id, momento, tipo, ferramenta_id, ferramenta, confianca, detalhe, reconhecido FROM eventos WHERE 1=1"
        params: list = []
        if inicio:
            sql += " AND momento >= ?"
            params.append(inicio.isoformat(timespec="seconds"))
        if fim:
            sql += " AND momento <= ?"
            params.append(fim.isoformat(timespec="seconds"))
        if tipos:
            sql += f" AND tipo IN ({','.join('?' * len(tipos))})"
            params.extend(tipos)
        if ferramenta_id:
            sql += " AND ferramenta_id = ?"
            params.append(ferramenta_id)
        sql += " ORDER BY momento DESC, id DESC"
        if limite:
            sql += " LIMIT ?"
            params.append(limite)
        with self._lock:
            linhas = self._con.execute(sql, params).fetchall()
        return [
            RegistroEvento(r[0], datetime.fromisoformat(r[1]), r[2], r[3], r[4], r[5], r[6] or "", bool(r[7]))
            for r in linhas
        ]
