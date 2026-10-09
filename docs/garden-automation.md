# Automação do Garden

## Escopo e segurança

A `Fazendeira`, em `app/core/fazendeira.py`, coordena a coleta das 34 sementes do
Garden. O controle começa em **Desligada**. **Ligar** inicia os ciclos automáticos;
**Desligar** impede novas ações e aguarda o lote em andamento terminar. O bot sempre cria um plano completo
antes de modificar o jogo e o modo **Simular próximo tick** nunca chama uma
operação mutável da bridge.

A estratégia funciona como reconciliação de estado:

- a cada tick escolhe uma meta e calcula o layout completo antes de agir;
- nunca remove espécies fora do catálogo, mesmo se outra automação solicitar
  uma limpeza ou colheita; descobertas ainda não desbloqueadas só podem ser
  colhidas maduras para liberar sua semente, nunca removidas como limpeza;
- preserva toda planta que já está na posição correta do layout;
- remove, mesmo imaturas, plantas erradas, plantas fora do layout e mutações
  indesejadas; se uma posição correta estava ocupada, limpa e replanta no mesmo
  plano;
- quando a mutação-alvo aparece, protege essa planta até ela amadurecer e já
  calcula a próxima meta como se sua semente estivesse desbloqueada;
- a cada snapshot, mantém uma lista derivada de todas as plantas presentes cuja
  semente ainda está bloqueada; nenhuma delas pode ser removida pelo layout
  seguinte, mesmo quando várias descobertas estão amadurecendo ao mesmo tempo;
- enquanto a meta cresce, prepara em paralelo todas as partes plantáveis do
  próximo layout; posições ocupadas pela meta e sementes ainda bloqueadas são
  deixadas pendentes;
- quando a meta amadurece, colhe-a primeiro e completa no mesmo plano os pontos
  do próximo layout que dependiam da semente recém-desbloqueada;
- pode selecionar fertilizante durante crescimento e lascas de madeira quando
  os pais da mutação estão maduros;
- descongela quando o crescimento precisa continuar, mas nunca congela
  automaticamente, pois isso pode matar Cheapcaps;
- não sacrifica o Garden, não compra upgrades e não altera saves.

## Círculos de Juicy queenbeet

Para Juicy queenbeet, cada centro precisa estar vazio e cercado por **oito
Queenbeets maduras**. No Garden 6×6, os quatro círculos são independentes. Se
um círculo perder um pai, as sobreviventes daquele círculo são colhidas e as
oito são replantadas juntas, em um único lote com orçamento validado antes da
primeira remoção. Os outros círculos são preservados. Se ainda houver outro
círculo pronto, Wood chips permanece ativo durante a renovação.

Uma descoberta ainda não desbloqueada ou espécie fora do catálogo bloqueia
a renovação de todo o círculo que ocupa: não se remove a planta protegida nem
se preenche apenas parte do grupo. O restante do Garden pode continuar sendo
preparado. A proteção também vale para Thumbcorn e Combo; Auto Ascensão é
bloqueada se apagaria espécies desconhecidas ou descobertas não desbloqueadas.

Plantar o círculo junto alinha o início do crescimento; variações aleatórias
de idade ainda podem fazer as oito plantas amadurecerem em ticks diferentes.

## Saldo insuficiente e retomada

Antes de limpar ou substituir o layout, a automação soma os preços atuais de
**todos os plantios pendentes**, usando o custo informado pelo próprio Garden.
Se não puder pagar o lote inteiro, preserva as plantas existentes e não começa
um plantio parcial. No próximo tick, lê novamente o estado e tenta retomar.

As colheitas maduras já previstas no plano continuam antes dessa decisão:
sementes novas não são perdidas por falta de dinheiro para o próximo layout,
e a colheita pode ajudar a financiá-lo. Plantas corretas e descobertas ainda
imaturas continuam protegidas pelas regras do planejador. Não há empréstimos,
gasto de lumps ou congelamento para resolver falta de saldo.

A conferência do saldo, dos preços e dos canteiros ocorre imediatamente antes
das remoções, na mesma chamada JavaScript que executa limpeza e plantio.
Banco e Simple Farm não podem gastar entre essa conferência e o lote. Se o
canteiro tiver mudado desde o planejamento ou uma semente não estiver
liberada, a limpeza não começa. Resultados inesperados durante o lote
interrompem as ações restantes, sem tentar restaurar o save.

A interface mostra **Garden: aguardando dinheiro** em amarelo, com custo,
saldo e quanto falta. É uma espera normal, não um erro; avisos iguais não
são repetidos no log a cada tick. Falhas reais continuam em vermelho.
A simulação também mostra o custo estimado e o saldo, sem executar ações.

## Modo Green, aching thumb

O checkbox **Green, aching thumb** prioriza temporariamente Thumbcorn para obter a
conquista de colher 1.000 plantas maduras. Ele também respeita a separação entre
planejamento e execução: com o controle em **Desligada**, o modo produz somente
prévia e jamais chama uma operação mutável da bridge.

Enquanto Thumbcorn ainda estiver bloqueado, a Fazendeira continua a coleção
normal e apenas informa que o modo está aguardando o desbloqueio; ela não limpa
o Garden, troca solo nem prepara canteiros para esse modo. Depois do desbloqueio,
o plano isolado preenche somente canteiros desbloqueados com Thumbcorn, preserva
as que ainda crescem e colhe somente Thumbcorn madura. Plantas diferentes podem
ser removidas exclusivamente quando a substituição por Thumbcorn estiver declarada
no mesmo plano; nunca são colhidas apenas para aumentar o contador. Canteiros de
Thumbcorn madura colhida são replantados no ciclo seguinte.

O snapshot consulta `Game.HasAchiev('Green, aching thumb')` sem mutar o jogo; esta
é a confirmação final. Quando presente e numérico, `M.harvests` também é exibido
como progresso informativo, mas nunca decide a conclusão. Se a versão do runtime
não expuser uma dessas APIs de modo seguro, o modo especial pausa antes de qualquer
ação Thumbcorn e informa o motivo. Ao confirmar a conquista, a interface desmarca
e persiste o checkbox, registra o resultado e volta de imediato ao planejamento
normal da coleção.

Para receitas com dois pais, a Fazendeira usa layouts genéricos em faixas no
canteiro inteiro. Pais iguais formam faixas de uma mesma semente; pais diferentes
alternam as duas sementes. A orientação e o deslocamento são escolhidos para
maximizar os espaços vazios que satisfazem a receita. Receitas que exigem quatro
ou mais vizinhos continuam usando anéis ao redor de um centro vazio.

No canteiro máximo 6×6, receitas de dois pais usam diretamente o setup de
referência com dez plantas. Para pais diferentes, as duas faixas são
`GYG.YG` e `GY.GYG`; os pontos permanecem vazios. As marcações vermelhas vistas
no diagrama de referência representam mutações indesejadas possíveis, não
sementes que devam ser plantadas. Em canteiros menores, o planejador continua
calculando uma variante compatível com os quadrados desbloqueados.

Receitas de alta contagem não são forçadas nesse padrão genérico. Para
**Golden clover**, o Garden 6×6 usa o setup otimizado específico de 20
**Ordinary clovers**, deixando 16 casas de mutação com pelo menos quatro pais
vizinhos:

```text
G.G..G
.GGGGG
GG....
....GG
GGGGG.
G..G.G
```

`G` representa **Ordinary clover** e `.` uma casa que deve permanecer vazia.
Em Gardens menores, a receita volta ao anel local de quatro Ordinary clovers.

Para **Juicy queenbeet**, o Garden 6×6 usa 32 **Queenbeets** e quatro centros
vazios. Cada centro fica cercado pelas oito Queenbeets exigidas pela receita:

```text
QQQQQQ
Q.QQ.Q
QQQQQQ
QQQQQQ
Q.QQ.Q
QQQQQQ
```

`Q` representa **Queenbeet**. Em Gardens menores, o planejador volta para um
anel local de oito plantas. **Shriekbulb** usa como receita preferencial três
**Duketaters** de qualquer idade (0,5%), em vez de cinco Queenbeets maduras
(0,1%). **Everdaisy** continua exigindo três **Tidygrasses** e três
**Elderworts** maduras. Ambas usam estratégias próprias de anel e nunca passam
pelo gerador genérico de dois pais.

Os nomes de sementes apresentados ao usuário seguem os nomes oficiais em inglês;
as explicações, mensagens, logs e documentação permanecem em português.

## Fonte das receitas e API validada

O catálogo central fica em `app/core/garden_catalog.py`. Ele foi conferido em
**27/09/2026** contra o JavaScript oficial servido em:

`https://orteil.dashnet.org/cookieclicker/minigameGarden.js`

Foram validadas as estruturas `M.plants`, `M.plantsById`, `M.getMuts`,
`M.soils`, `M.soilsById`, `M.plot`, `M.plotLimits`, `M.isTileUnlocked`,
`M.useTool`, `M.harvest`, `M.harvests`, `M.freeze`, `M.nextStep`, `M.stepT` e
`M.nextSoil`, além de `Game.HasAchiev` para confirmação da conquista.
O arquivo oficial não declara uma versão própria do minigame. Por isso, o
snapshot registra `Game.version` em tempo de execução e a data de validação é
a referência documental. Uma mudança futura nas receitas deve ser feita somente
no catálogo e nos testes associados.

## Fluxo

1. A bridge lê um snapshot imutável com sementes, solos, plantas, maturidade,
   canteiros, congelamento e próximos ticks.
2. A `Fazendeira` compara o snapshot com o catálogo e escolhe uma meta.
3. A prioridade favorece receitas prontas que liberam mais dependências;
   mutações já presentes no canteiro têm precedência.
4. Uma estratégia explicitamente mapeada para a planta gera o plano.
5. Em simulação, o fluxo termina. Com a automação ligada, todas
   as ações do plano são enviadas no mesmo tick e novamente validadas no
   JavaScript; não existe limite parcial de ações por ciclo.

## Sincronização com o tick

O minigame não expõe um evento público específico de “Garden tick”. Seu
`logic()` interno atualiza `M.nextStep` quando processa o jardim. A bridge lê
esse valor no mesmo snapshot das plantas e a interface agenda uma execução para
logo depois desse instante. O novo `M.nextStep` também funciona como token: a
`Fazendeira` recusa uma segunda execução real enquanto ele não mudar.

Se `M.nextStep` não puder ser lido por incompatibilidade ou carregamento
incompleto, a configuração **Fallback de consulta** é usada. Ela não substitui
o token: quando o token existe, continua impossível executar duas vezes no
mesmo tick.

## Limitações atuais

- A validação foi feita no código oficial, mas não em uma sessão conectada do
  jogo Steam; diferenças da versão embarcada aparecerão como falhas defensivas.
- O planejador usa uma receita preferencial por planta quando o runtime oferece
  alternativas. As alternativas ficam documentadas no catálogo.
- Clicar em **Ligar** inicia a limpeza de layouts
  antigos e de plantas que não correspondam ao objetivo atual.
- Probabilidades raras, principalmente a Juicy queenbeet, podem
  exigir muitos ticks. O snapshot, e não uma previsão local, é sempre a evidência
  de que uma semente foi concluída.
