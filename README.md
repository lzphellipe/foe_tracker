# FOE Tracker

Sistema de controle e rastreamento de ferramentas com visão computacional, para apoiar a atualização contínua do inventário F.O.E. (*Foreign Object Elimination*).

Uma câmera USB observa o painel ou a bancada. Cada quadro é alinhado à imagem de referência, as ferramentas são detectadas com YOLO e o estado atual é comparado com o estado de referência. Retiradas, devoluções, movimentações, falhas de detecção e alarmes vão para um banco SQLite e aparecem numa interface PyQt5.

## Arquitetura

```
Câmera USB ──► camera.py ──► alinhamento.py ──► detector.py ──► inventario.py ──► banco.py
 (OpenCV)                    (CLAHE + ORB +      (YOLO)          (slots, IoU,       (SQLite)
                              homografia)                         histerese)            │
                                         └──────── servico.py (Pipeline) ◄─────────────┘
                                                        │
                                   ui/janela.py (PyQt5, QThread) ──► relatorios.py (CSV/HTML)
```

| Módulo | Responsabilidade |
|---|---|
| `foe/camera.py` | Captura de quadros por câmera USB, com reconexão |
| `foe/alinhamento.py` | Pré-processamento (cinza, blur, CLAHE) e registro do quadro na referência por ORB + RANSAC |
| `foe/detector.py` | Inferência YOLO; devolve classe, nome, confiança e caixa |
| `foe/inventario.py` | Associa detecções aos *slots*, confirma mudanças por N quadros e gera eventos |
| `foe/banco.py` | Esquema SQLite, gravação e consultas filtradas |
| `foe/relatorios.py` | Exportação CSV (padrão Excel pt-BR) e relatório HTML do período |
| `foe/servico.py` | Pipeline completo, independente de Qt |
| `foe/ui/janela.py` | Interface: vídeo anotado, indicadores, faltantes, eventos, histórico |

## Regras de comparação

Cada ferramenta tem um **slot**: a caixa onde ela fica na imagem de referência. A cada quadro:

1. Cada detecção vai para o slot de **mesma classe** com maior IoU (acima de `iou_minimo`). Assim duas chaves iguais são distinguidas pela posição.
2. Cada slot recebe uma observação:
   - **PRESENTE**: confiança ≥ `confianca_aceita`.
   - **INCERTA**: confiança entre `confianca_minima` e `confianca_aceita`.
   - **DESLOCADA**: a ferramenta foi vista na bancada, mas fora do seu slot.
   - **AUSENTE**: não foi vista.
3. O estado só muda depois de `quadros_confirmacao` observações seguidas iguais. Isso evita falso alarme quando a mão do técnico passa na frente.
4. Eventos gerados:

| Transição | Evento |
|---|---|
| PRESENTE/DESLOCADA → AUSENTE | `RETIRADA` |
| AUSENTE → PRESENTE ou DESLOCADA | `DEVOLUCAO` |
| PRESENTE ↔ DESLOCADA | `MOVIMENTACAO` |
| INCERTA por N quadros | `FALHA_DETECCAO` (o estado não muda) |
| AUSENTE por mais de `alarme_ausencia_segundos` | `ALARME` (uma vez por retirada) |
| Falha de alinhamento prolongada | `SISTEMA` (o inventário fica congelado) |

## Banco de dados (SQLite)

- **`ferramentas`**: `id` (código FOE), `nome`, `classe_id`, `caixa` (JSON), `ativo`, `cadastrada_em`
- **`eventos`**: `id`, `momento` (ISO 8601), `tipo`, `ferramenta_id`, `ferramenta`, `confianca`, `detalhe`, `reconhecido`

O esquema completo está em `foe/banco.py`, com índices por data, tipo e ferramenta.

## Como usar

```bash
pip install -r requirements.txt

# 1. Treinar o modelo (ver seção abaixo) e salvar em modelos/ferramentas.pt
# 2. Fotografar o painel completo, com todas as ferramentas nos slots
python main.py capturar-referencia
# 3. Gerar os slots a partir da referência e revisar dados/slots.json
python main.py gerar-slots
# 4. Monitorar
python main.py executar
```

Os parâmetros ficam em `config.yaml`.

Em `dados/slots.json`, troque os IDs genéricos (`FER-001`…) pelos códigos reais do inventário FOE:

```json
[{"id": "CHV-10MM-01", "nome": "Chave combinada 10 mm", "classe_id": 0, "caixa": [120, 80, 310, 140]}]
```

## Treinamento do YOLO

1. **Coleta.** Tire de 150 a 300 fotos por ferramenta com a própria câmera USB. Varie a iluminação, a posição dentro e fora do slot, a oclusão parcial (mão) e o fundo com painel vazio.
2. **Rotulagem** no formato YOLO. Ferramentas possíveis: Label Studio, CVAT ou Roboflow. Use uma classe por *tipo* de ferramenta (ex.: `chave_10mm`, `alicate_universal`). O ID individual vem do slot, não da classe.
3. **Treino:**
   ```bash
   yolo detect train data=dataset.yaml model=yolov8n.pt imgsz=640 epochs=100 patience=20
   ```
4. **Validação.** Veja precisão, recall e mAP@0.5 no conjunto de teste. Ajuste `confianca_aceita` olhando a curva precisão–recall.

## Testes

```bash
pytest -q
```

| Arquivo | O que verifica |
|---|---|
| `test_inventario.py` | IoU; estado estável; oclusão breve sem falso alarme; retirada e devolução; alarme único no tempo certo; confiança baixa → falha sem mudar estado; ferramenta fora do slot; ferramentas iguais distinguidas pelo slot |
| `test_alinhamento.py` | Recupera homografia de quadro deslocado (erro < 2 px); rejeita quadro sem textura |
| `test_banco_relatorios_servico.py` | Gravação e filtros no SQLite; reconhecimento de alarme; CSV; tempo médio fora; relatório HTML; pipeline persistindo eventos; inventário congelado sem alinhamento |

### Testes de campo sugeridos para a versão inicial

| Teste | Métrica |
|---|---|
| Detecção no conjunto de teste | Precisão, recall, mAP@0.5 por classe |
| Retirada/devolução reais (ex.: 50 ciclos) | % de eventos corretos; falsos positivos e falsos negativos |
| Oclusão por mão durante 1–3 s | Nº de falsas retiradas (meta: 0) |
| Variação de luz (lâmpada acesa/apagada, luz lateral) | Taxa de alinhamento e de detecção |
| Deslocamento da câmera (± alguns cm) | Alinhamento mantido; eventos corretos |
| Desempenho | FPS e latência da retirada até o registro |
| Operação contínua (ex.: 8 h) | Estabilidade, memória, integridade do banco |
