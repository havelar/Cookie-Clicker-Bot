# Simple Farm

O **Simple Farm** é um farm de apoio da aba **Combo**: acumula cookies enquanto
Garden, Banco e as coletas comuns continuam funcionando. Não exige uma
configuração específica do Pantheon.

## Execução

- Coleta Golden Cookies naturais e drops de Cookie Storm.
- Aproveita janelas fortes com cliques extras, preservando o clicker manual.
- Prevê um único `Click Frenzy` de `Force the Hand of Fate` na season atual.
- Quando precisa avançar o contador, usa `Haggler’s Charm` somente com mana cheia
  e fora de buffs de produção/clique. Essa magia pode dar desconto ou encarecer
  upgrades temporariamente; as compras sempre consultam o preço atual.
- Lança e abre um único FtHoF com mana cheia e um multiplicador natural de
  produção ainda durando o mínimo configurado. Não vende nem recompra torres.
- Preserva mana se `Click Frenzy` ou `Dragonflight` já estiver ativo.
- Continua coletando e comprando mesmo sem previsão útil ou minigames desbloqueados.

O antigo “Duplo Click Frenzy” foi removido. Repetir o mesmo buff não cria dois
multiplicadores de clique independentes; isso não justifica vender/recomprar
centenas de torres neste farm.

## Caixa e compras

Por padrão, reserva **80% do maior saldo observado durante esta execução**.
A configuração aceita de 60% a 99%, garantindo que o farm preserve a maioria.
A reserva efetiva considera também `6.000 × CpS`, para Lucky.

A cada **15 segundos**, pode investir até **5% do saldo atual** (configurável
entre 1% e 20%), limitado ao excedente da reserva. Esse teto vale para a soma
de todas as compras do ciclo, não para cada item. Compras sucessivas não
reduzem a reserva percentual já estabelecida.

Exemplo: com 1 milhão de cookies, o padrão protege 800 mil e permite gastar
até 50 mil no ciclo. Se o Banco ou Garden reduzir o saldo a 700 mil, o farm
continua coletando, mas suspende suas próprias compras até recuperar caixa.
A reserva não bloqueia o dinheiro das outras automações. Ao parar e iniciar
o farm novamente, a referência passa a ser o saldo da nova execução.

Dentro do orçamento:

1. Até metade pode comprar um upgrade de produção. Upgrades de cookies com
   bônus global em % vêm primeiro; depois kittens, upgrades de construções e
   de clique. Entre upgrades percentuais da mesma classe, prefere maior bônus
   por preço quando a potência é numérica; potências calculadas usam uma
   estimativa conservadora.
2. O restante pode comprar até 25 construções, priorizando o ganho estimado de
   CpS por cookie gasto. Se não houver upgrade elegível, todo o orçamento pode
   ir para construções. Não há meta obrigatória de Wizard Towers.

Toggles, pesquisas, upgrades no cofre, ações especiais, compras com lumps e
Chocolate egg ficam fora do comprador. Durante buffs úteis, compras aguardam.
O saldo e os preços são conferidos novamente no jogo dentro da mesma operação,
pois Garden e Banco podem ter gasto desde a leitura anterior.

O retorno de construções é uma estimativa baseada no CpS atual por unidade;
não é uma simulação exata de todas as sinergias. Os logs mostram compras,
saldo, reserva e o motivo de aguardar quando não há orçamento.

## Convivência com outras automações

O Simple Farm coordena somente Golden Cookies e Grimoire: durante a execução,
o coletor comum de Golden Cookies e o spam de skills cedem essas duas tarefas
ao farm. Suas preferências não são alteradas e voltam a valer ao parar.
Fortunes, renas, wrinklers e coleta de lumps continuam conforme configurados.
Garden e Banco mantêm seus timers, workers e controles ativos.

O farm nunca gasta Sugar Lumps, usa loans, vende construções ou altera Garden,
Pantheon, auras, season ou Golden Switch. As automações independentes continuam
responsáveis por suas próprias ações. Auto Ascensão e Combo Endgame não rodam
junto, pois mudam o estado necessário para o farm.

O clicker extra só atua em buffs de clique ou combinações fortes de produção.
Um clicker ligado manualmente continua ligado quando o buff ou o farm termina.

## Interface

Passe o mouse no campo **ou no rótulo** de cada configuração para ler o tooltip.
Os nomes indicam a unidade e distinguem a verificação rápida das compras a cada
15 segundos. O acompanhamento mantém o layout anterior, mas mostra
**Próxima oportunidade** e **Magias**, em vez de Dualcast.

Use **Atualizar prévia** para uma leitura sem ações. Para executar, marque
**Habilitar execução real** e clique em **Iniciar Simple Farm**. O bot cria um
backup antes de começar. **Parar** encerra apenas o farm de apoio.
