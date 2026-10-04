# Simple Farm

O **Simple Farm** é o modo econômico da aba **Combo**. Ele existe para acumular
cookies no começo da ascensão antes de preparar o combo endgame.

## O que ele faz

- mantém o autoclick desligado durante a produção comum e o ativa somente em
  janelas fortes de clique;
- pausa as outras automações enquanto detém o modo exclusivo;
- coleta Golden Cookies naturais;
- reconhece Cookie Storm e drena somente os drops da tempestade, sem parar o modo;
- procura, pela seed atual, o próximo par seguro de `Force the Hand of Fate`
  contendo pelo menos um `Click Frenzy`;
- alinha o contador com `Haggler's Charm`, uma vez por barra e somente com a
  mana completamente cheia;
- aguarda um multiplicador natural (`Frenzy`, `Dragon Harvest`,
  `Building Special`, `Click Frenzy` ou `Elder Frenzy`);
- executa o Dualcast vendendo e recomprando Wizard Towers na mesma operação;
- aproveita Godzamok automaticamente quando ele já está no slot Diamond;
- reinveste uma parcela configurável do excedente em upgrades e construções;
- cria um backup antes da execução real.

Os pontos mínimos de Dualcast seguem o nível das Wizard Towers. No nível 10,
por exemplo, o mínimo é `501 → 1`. Se houver mais de 501 torres, a operação
restaura exatamente a quantidade original depois do segundo cast.

## Garantias fixas

O Simple Farm não possui opções que relaxem estas regras:

- não gasta Sugar Lumps;
- não usa loans;
- não planta, colhe, congela nem troca o solo do Garden;
- não move espíritos do Pantheon;
- não troca auras, season ou Golden Switch;
- não executa o Dualcast se não puder garantir a recompra das torres;
- não usa o forecast enquanto Dragonflight estiver ativo.

O Pantheon é somente lido para exibição. A configuração manual recomendada é
`Godzamok / Mokalsium / Muridal`, respectivamente em Diamond, Ruby e Jade.

## Reinvestimento e caixa

Por padrão, o modo protege **30% do maior caixa observado** desde que foi
iniciado e limita cada ciclo de investimento a **10% do caixa atual**. A
reserva nunca diminui durante a sessão. O valor efetivamente protegido é o
maior entre:

- a reserva percentual;
- `6.000 × CpS`, para preservar um banco útil para Lucky;
- o preço necessário para recomprar todas as Wizard Towers do Dualcast.

O comprador tenta primeiro um upgrade normal e seguro. Kitten e upgrades de
clique recebem prioridade porque o autoclick explora as janelas mais fortes. Interações
especiais, toggles, pesquisas e upgrades guardados no cofre são ignorados.
`Sugar Frenzy` e `Chocolate egg` são bloqueados explicitamente: o primeiro
quebraria a garantia de zero lumps e o segundo deve ser preservado para o fim
da ascensão.
Quando nenhum upgrade cabe no orçamento, são compradas até 25 construções por
ciclo, sempre recalculando o melhor ganho de CpS por cookie gasto. Wizard
Towers só entram nessa compra enquanto faltarem torres para o ponto mínimo do
Dualcast; depois disso ficam protegidas contra crescimento desnecessário do
custo de recompra.

Compras são adiadas enquanto houver um multiplicador curto ativo, para não
atrasar o Dualcast ou a janela de cliques.

## Autoclick sob demanda

O clicker é ligado imediatamente antes do Dualcast e enquanto existir
`Click Frenzy`, `Dragonflight`, `Elder Frenzy`, `Cursed Finger` ou o buff de
Godzamok. Ele também é usado quando pelo menos dois multiplicadores de produção
estão empilhados. Um Frenzy isolado não mantém o clicker ligado. Assim que a
janela forte termina, o modo o desliga novamente.

## Uso

1. Abra **Combo → Simple Farm**.
2. Clique em **Atualizar prévia** para conferir o próximo par e os skips.
3. Marque **Habilitar execução real**.
4. Clique em **Iniciar Simple Farm** e confirme.
5. Use **Parar** quando quiser devolver o controle às demais automações.

O intervalo padrão é `0,2 s`. Isso permite reagir rapidamente a Golden Cookies
sem transformar o forecast em um loop excessivamente pesado.
