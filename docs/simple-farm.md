# Simple Farm

O **Simple Farm** é um farm de apoio da aba **Combo**: acumula cookies enquanto
Garden, Banco e as coletas comuns continuam funcionando. Não exige uma
configuração específica do Pantheon.

## Execução

- Coleta Golden Cookies naturais e drops de Cookie Storm.
- Aproveita janelas fortes com cliques extras, preservando o clicker manual.
- Prevê `Click Frenzy` de `Force the Hand of Fate` na season atual. Procura e
  alinha primeiro Dual Cast quando a magia consecutiva traz um multiplicador complementar:
  `Building Special`, `Elder Frenzy` ou `Frenzy` ainda não ativo, em qualquer ordem.
- Não compra torres extras só para viabilizar Dual Cast. Se existir um par útil
  dentro do alcance, usa Haggler’s Charm para chegar nele, mesmo que um Click
  Frenzy isolado apareça antes.
- Quando precisa avançar o contador, usa `Haggler’s Charm` somente com mana cheia
  e fora de buffs de produção/clique. Essa magia pode dar desconto ou encarecer
  upgrades temporariamente; as compras sempre consultam o preço atual.
- Espera mana cheia e um multiplicador natural de produção com duração suficiente.
  Para duas magias, vende o mínimo necessário de Wizard Towers, lança a segunda,
  recompra **todas** as torres e só então abre os dois cookies. Calcula a mana
  conforme quantidade, nível e aura atuais, sem mudar esses ajustes.
- Se não houver par complementar viável dentro do alcance configurado, ou se a
  recompra não couber no orçamento, aproveita o primeiro Click Frenzy isolado.
  Se o primeiro resultado do par é apenas o multiplicador de apoio, replaneja
  antes de gastar qualquer recurso.
- Preserva mana se `Click Frenzy` ou `Dragonflight` já estiver ativo.
- Continua coletando e comprando mesmo sem previsão útil ou minigames desbloqueados.

Dual Cast significa duas magias, não dois multiplicadores de Click Frenzy.
Repetir Click Frenzy apenas prolonga o buff, portanto não motiva a venda de torres.
Building Special pode repetir um prédio já beneficiado; o prédio só é conhecido
quando o cookie abre, então o ganho adicional não é garantido.

A previsão considera a chance extra de backfire do primeiro cookie em tela.
Venda, segunda magia, recompra e abertura acontecem numa única avaliação do jogo:
Garden e Banco continuam ligados, mas não podem intercalar gastos no meio dessa
operação. Em caso de falha após a venda, tenta restaurar as torres antes de parar
com diagnóstico; uma recompra incompleta nunca é anunciada como sucesso.

## Caixa e compras

Por padrão, reserva **80% do maior saldo observado durante esta execução**.
A configuração aceita de 15% a 99%. Use 15% quando o objetivo for reinvestir
agressivamente; Garden e Banco continuam podendo gastar o saldo restante.
A reserva efetiva considera também `6.000 × CpS`, para Lucky.

A cada **15 segundos**, pode investir até **5% do saldo atual** (configurável
entre 1% e 20%), limitado ao excedente da reserva. Esse teto vale para a soma
de todas as compras do ciclo, não para cada item.

O Dual Cast é uma oportunidade rara e usa uma regra própria: o valor **integral**
da recompra precisa caber no excedente da reserva antes da venda, sem depender do
dinheiro recebido pela venda nem de ganhos futuros do combo. Ele não consome o
teto de compras de 15 segundos, mas depois do Dual Cast o farm aguarda 15 segundos
antes de novas compras. O custo líquido costuma ser menor, mas não é zero.
Compras sucessivas não reduzem a reserva percentual já estabelecida.

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

Os cinco valores da estratégia — alcance de magias, intervalo, duração mínima do
buff, reserva e teto de compras — são salvos automaticamente ao serem alterados
e voltam iguais no próximo início do aplicativo.

O retorno de construções é uma estimativa baseada no CpS atual por unidade;
não é uma simulação exata de todas as sinergias. Os logs mostram compras,
saldo, reserva e o motivo de aguardar quando não há orçamento.

## Convivência com outras automações

O Simple Farm coordena somente Golden Cookies e Grimoire: durante a execução,
o coletor comum de Golden Cookies e o spam de skills cedem essas duas tarefas
ao farm. Suas preferências não são alteradas e voltam a valer ao parar.
Fortunes, renas, wrinklers e coleta de lumps continuam conforme configurados.
Garden e Banco mantêm seus timers, workers e controles ativos.

O farm só vende Wizard Towers temporariamente para Dual Cast. Nunca gasta Sugar
Lumps, usa loans, vende outros prédios ou altera Garden,
Pantheon, auras, season ou Golden Switch. As automações independentes continuam
responsáveis por suas próprias ações. Auto Ascensão e Combo Endgame não rodam
junto, pois mudam o estado necessário para o farm.

O clicker extra só atua em buffs de clique ou combinações fortes de produção.
Um clicker ligado manualmente continua ligado quando o buff ou o farm termina.

## Interface

Passe o mouse no campo **ou no rótulo** de cada configuração para ler o tooltip.
Os nomes indicam a unidade e distinguem a verificação rápida das compras a cada
15 segundos. O acompanhamento mantém o layout anterior, mas mostra
**Próxima oportunidade** e **Magias**. A oportunidade informa se haverá uma ou
duas magias, a quantidade temporária de torres e o custo da recompra. O tooltip
explica a decisão; após executar, o log informa o custo líquido e a restauração.

Use **Atualizar prévia** para uma leitura sem ações. **Ligar** inicia o farm e
cria um backup antes de começar. **Desligar** encerra apenas o farm de apoio;
o controle mostra **Desligando…** até a operação atual terminar.
