# Atualização visual das ações no jogo

As ações de Garden, Stock Market, Simple Farm, Combo e Auto Ascensão passam
por `CookieClickerBridge._execute_game_action`. Novas ações que alterem o save
devem usar esse caminho, mantendo `execute_js` para consultas e os cliques
nativos de coleta, que já atualizam a interface do jogo.

O sincronizador de `app/bridge/visual_sync.py` roda na mesma avaliação JavaScript
depois da operação, inclusive quando parte dela foi aplicada antes de uma falha:

- Garden: atualiza e confere os destaques de solo, congelamento e efeito de gelo;
  processa o redesenho pendente do canteiro com `buildPlot` e dos efeitos com
  `computeEffs`.
- Pantheon: posiciona os espíritos nos slots aplicados, incluindo o espírito
  deslocado por uma troca, sem consumir outro worship swap.
- Dragão: atualiza o menu aberto quando as auras mudam, sem abrir menus fechados.
- Loja: processa os indicadores nativos de atualização de prédios e upgrades
  depois que o modo temporário de compra foi restaurado.
- Banco, mana, buffs, Sugar Lumps e transições de ascensão: continuam usando
  as APIs e a renderização nativa por frame. Não se chama `logic`, `tick`,
  `init` ou `load` para forçar atualização visual.

Elementos ausentes em telas fechadas não bloqueiam operações: ao abrir, o jogo
monta a interface a partir do estado atual. Falhas de sincronização em elementos
presentes geram aviso no resultado e no log, sem repetir compras, magias ou
sacrifícios. A validação da ação continua sendo feita contra o estado do jogo.

`tests/test_visual_sync_runtime.py` testa o DOM separado dos dados, incluindo
cooldown, descongelamento, troca de espíritos, menu de auras, falhas parciais e
ausência de interface.
