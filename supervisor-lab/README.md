# Supervisor Lab — estudo independente

Nome de trabalho, não identidade final de produto. Este diretório não é um clone
de SMAG, SMAG-ReX ou FineCore e não contém código transplantado.

## Objetivo

Qualificar um supervisor pequeno e substituível, inicialmente com FineCore por
adaptador. Selecionar mecanismos isolados, não combinar frameworks inteiros.

## Estado

- DESIGN_PROPOSED: contrato e protocolo inicial.
- IMPLEMENTED: nenhum supervisor/adaptador neste laboratório.
- EXECUTED: somente testes upstream focados, registrados em SOURCES.json.
- FineCore integrado: NOT_EXECUTED.
- Ganho comparativo: NOT_MEASURED.
- Nenhuma publicação, merge ou promoção autorizada por estes documentos.

## Leitura

1. COUPLING-MAP.md — seams reais do FineCore, lacunas e comparação CLI/SDK.
2. CONTRACT.md — rascunho de autoridade e lifecycle, não contrato aprovado.
3. scenarios.json — critérios observáveis por cenário, ainda não executados.
4. SOURCES.json — revisões, caminhos e testes observados.

## Sequência proposta

1. Revisar o mapa de acoplamento antes de escolher transporte ou escrever código.
2. Especificar a qualificação dos seams e as restrições necessárias.
3. Somente após isso escolher CLI ou bridge SDK; nenhuma escolha está aprovada.
4. Implementação e execução comparativa são etapas futuras, separadas.
5. Não portar mecanismos nem promover candidatos por testes upstream.

Não executar experimentos com credenciais reais, rede irrestrita ou repositórios
de trabalho como alvo. A ausência de custo medido deve permanecer UNKNOWN_COST.
