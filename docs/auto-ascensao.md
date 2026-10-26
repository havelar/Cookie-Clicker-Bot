# Auto Ascensão

## Contrato validado com o jogo

A integração foi verificada em modo somente leitura contra o runtime do Cookie
Clicker 2.053 disponível ao projeto. A bridge usa estas APIs nativas:

- `Game.OnAscend`, `Game.AscendTimer` e `Game.ReincarnateTimer` para distinguir
  jogo normal, transição e tela de ascensão;
- `Game.HowMuchPrestige(Game.cookiesReset + Game.cookiesEarned)` menos
  `Game.prestige` para calcular o ganho previsto;
- upgrades de `Game.UpgradesById` com `pool === "prestige"` e `upgrade.buy()`
  para a árvore celestial;
- `Game.Reincarnate(1)` e `Game.Ascend(1)` para as transições confirmadas;
- `Game.UpgradesInStore`, `upgrade.canBuy()` e `Game.storeBuyAll()` para usar o
  botão nativo “Comprar todos os upgrades”;
- `Game.ObjectsById`, `object.getPrice()`, `object.getSumPrice(n)` e
  `object.buy(n)` para construções.

Cada operação mutável revalida tela, alvo e recursos na mesma avaliação
JavaScript que executa a ação. O resultado só é aceito quando a mudança
esperada também é observada. Uma falha ou resposta ambígua encerra a máquina
em erro seguro; a operação não é repetida silenciosamente.

## Regra de compra

Heavenly Upgrades são comprados um por vez, começando pelo menor preço e depois
pelo menor identificador. Só entram na regra upgrades ainda não comprados,
acessíveis, com todos os pais comprados e sem funções de clique ou escolha
especial. Essa exclusão evita decisões ocultas em seletores e toggles.

Upgrades normais são comprados em uma única chamada a `Game.storeBuyAll()`, a
mesma função usada pelo botão nativo liberado por “Inspired checklist”. A
prévia reproduz a regra dessa função: ignora itens no cofre e os pools `toggle`
e `tech`. Depois da chamada, a bridge compara os upgrades antes e depois e só
aceita sucesso quando ao menos uma nova compra é observada. A ordem interna de
compra permanece a ordem oficial de `Game.UpgradesInStore`.

A compra de construções inclui todas as opções desbloqueadas que permitam ao
menos uma unidade. A ordem é decrescente por identificador de
`Game.ObjectsById`: na versão 2.053 isso prioriza as construções de maior nível,
sem excluir as básicas. Em uma única chamada à bridge, o runtime tenta comprar
até 100 unidades de cada construção nessa ordem. O ciclo atualiza o snapshot e
repete novos lotes enquanto ainda houver alguma compra possível. A regra está
centralizada em `app.core.auto_ascensao.planejar_lote_construcoes` e é coberta
por testes com snapshots sintéticos.

## Estados e segurança

Um ciclo começa obrigatoriamente na tela de ascensão, compra Heavenly Upgrades
seguros, reencarna, habilita o clicker existente, compra upgrades e construções,
aguarda o ganho mínimo de prestígio, desliga o clicker e só então ascende. O
clicker também fica desligado na árvore celestial e após parada ou erro, para
não enviar cliques físicos a outra tela. O ciclo termina quando a nova tela de
ascensão é observada. Ao atingir a quantidade alvo, a automação para nessa tela.

Os estados explícitos são: prévia, compra celestial, reencarnação, preparação,
produção e compras, espera de prestígio, ascensão, concluído, interrompido e
erro seguro. O progresso depende de snapshots e polling configurável, não de
esperas fixas. O intervalo padrão e mínimo é de 0,1 segundo. O timeout
interrompe sem forçar ascensão.

O controle começa em **Desligada**. **Ligar** inicia a execução após a confirmação
da ascensão; **Atualizar prévia** apenas lê o runtime e descreve o próximo passo.
**Desligar** impede que uma nova ação
mutável comece; uma chamada já entregue ao runtime não pode ser desfeita.

## Limitações

- A estratégia não otimiza ascensões de longo prazo nem seleciona upgrades que
  abrem diálogos, escolhas ou efeitos especiais.
- A validação manual feita durante o desenvolvimento foi somente leitura no
  runtime 2.053. Não foi executada uma ascensão real.
- A automação exige que o usuário abra a tela de ascensão antes do primeiro
  ciclo. Isso evita que a ativação acidental ascenda um jogo em andamento.
