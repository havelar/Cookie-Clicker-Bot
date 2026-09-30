# Estudo técnico — combo para “And a little extra”

## Escopo, evidência e conclusão executiva

Este documento especifica, mas **não implementa**, um futuro looper para buscar a conquista “And a little extra”. Nenhuma magia, venda, compra, troca de aura ou espírito, loan, Golden Switch, Sugar Frenzy, colheita, clique, ascensão ou alteração de save foi executada durante o estudo.

As afirmações são identificadas assim:

- **Runtime**: observado em consulta CDP somente leitura ao Cookie Clicker 2.053 em 29/09/2026.
- **Guia**: procedimento ou estimativa dos guias locais e externos; precisa ser revalidado contra a versão efetivamente executada.
- **Hipótese**: proposta de arquitetura ou política para implementação futura; ainda não validada no jogo.

**Recomendação atualizada:** preparar um **Grail modificado planejado**, `Frenzy + Dragon Harvest + 3 Building Specials + Elder Frenzy + Click Frenzy`, usando dois BS naturais e o Quadcast sazonal previsto nos casts totais `1222–1225`. O save possui `1.205` Sugar Lumps, três swaps do Pantheon e requisitos para liberar os três loans; recursos não são o gargalo. A rota demanda um Sugar Lump para a recarga do Grimoire e outro, opcional mas recomendado, para Sugar Frenzy. O antigo Dualcast sem lump continua útil como teste, porém não é a recomendação final para fechar `1e72` com margem.

## 0. Plano mestre do save observado

### O que falta e o que “todos” significa

O runtime listou **21 conquistas não ganhas**. Elas se dividem em:

- **12 conquistas normais obtíveis:** quatro marcos de cookies por ascensão até `1e72`, `1e56` CpS, cinco marcos de prédios, `Green, aching thumb` e a colheita de um Caramelized Sugar Lump;
- **5 shadow achievements obtíveis:** `Seven horseshoes`, `All-natural cane sugar`, `When the cookies ascend just right`, `Third-party` e `Cheated cookies taste awful`;
- **4 conquistas de Dungeons:** ids `96–99`, marcadas pelo próprio conteúdo atual como “not technically achievable yet”. Dungeons não estão disponíveis no Cookie Clicker 2.053; portanto, concluir literalmente as 21 sem console/modificação do estado é impossível nessa versão.

Shadow achievements não contam para a porcentagem normal nem dão leite. `Third-party` exige carregar um add-on e `Cheated cookies taste awful` exige uma alteração reconhecida como cheat; nenhuma das duas deve ser disparada silenciosamente por automação.

| Grupo | Conquistas ausentes | Rota |
| --- | --- | --- |
| Produção normal | `What do you get for the baker who has everything`, `Bottomless pit`, `Rainy day fund`, `And a little extra`, `Speed's the name of the game` | Um combo acima de `1e72`; o marco de CpS deve ocorrer durante os buffs. |
| Prédios normais | `Everyone everywhere all at once`, `Where is my mind`, `Introspection`, `Sexcentennial and a half`, `Septcentennial` | Comprar 700 de cada prédio depois do combo. |
| Garden/lump normal | `Green, aching thumb`, `Maillard reaction` | 1.000 plantas maduras; colher um Caramelized Sugar Lump. |
| Shadows obtíveis | `Seven horseshoes`, `All-natural cane sugar`, `When the cookies ascend just right`, `Third-party`, `Cheated cookies taste awful` | Grind de Golden Cookies; Golden Lump; ascensão exata; add-on/cheat somente com autorização. |
| Dungeons indisponíveis | `Getting even with the oven`, `Now this is pod-smashing`, `Chirped out`, `Follow the white rabbit` | Sem rota legítima em 2.053. |

### Estado decisivo em 29/09/2026

| Item | Valor observado |
| --- | ---: |
| Cookies assados nesta ascensão | `1,1626e61` |
| Meta | `1e72` |
| CpS sem buff no snapshot final | `2,4742e55` |
| Poder de clique base observado | `9,2207e54` |
| Ritmo nominal do clicker do bot | `200 cliques/s` (`0,005 s`) |
| Wizard Towers | `726`, nível `10`, mana `116/116` |
| Seed / casts totais | `eqomd` / `1014` |
| Sugar Lumps | `1.205`; lump atual normal |
| Pantheon | três swaps, três slots vazios |
| Garden | nível 10, `24/34` seeds, Golden Clover/Nursetulip/Whiskerbloom disponíveis |
| Stock Market | escritório nível 0; Bank e Cursor nível 10/15, 936 Cursors |
| Golden Cookies clicados | `12.690`; faltam `15.087` para Seven horseshoes |
| Plantas maduras colhidas | `1`; faltam `999` |

Para `Septcentennial`, faltam comprar **704 prédios**: 7 Chancemakers, 13 Alchemy Labs, 33 Portals, 52 Time Machines, 26 Fractal Engines, 67 Javascript Consoles, 80 Idleverses, 204 Cortex Bakers e 222 Yous. A produção do combo deve vir antes dessas compras.

### Previsão exata do Grimoire

A previsão foi calculada localmente a partir de `Game.seed`, `spellsCastTotal` e do código carregado do FtHoF em 2.053. Nenhuma spell foi lançada. A sequência recomendada exige **Valentine's Day ou Easter** durante os quatro casts; as duas seasons consomem o mesmo sorteio extra do shimmer.

| Cast total | Shimmers anteriores | Resultado previsto | Uso |
| ---: | ---: | --- | --- |
| `1222` | 0 | `blood frenzy` / Elder Frenzy, por backfire | clicar por último entre os buffs, por ser curto |
| `1223` | 1 | Click Frenzy | janela de cliques |
| `1224` | 2 | Frenzy | redundante; deixar em tela para Dragon's Fortune |
| `1225` | 3 | Building Special | terceiro BS do combo |

Esses quatro resultados também foram verificados com e sem `Supreme Intellect`. A previsão deixa de ser confiável se o contador, a seed, a versão, a season ou a presença de Dragonflight mudar. Dragonflight **não pode estar ativo durante os casts**, pois ele remove Click Frenzy da lista normal do FtHoF.

O caminho até a janela é avançar exatamente **208 casts**, de `1014` para `1222`, usando spells baratas e conferindo o contador após cada lote. Com a política declarada pelo usuário de no máximo uma recarga por lump a cada 15 minutos, isso pode ser preparado em algumas horas; não é necessário gastar centenas de lumps. O looper deve parar em `1222` e bloquear qualquer automação concorrente do Grimoire.

Há uma janela rápida alternativa em `1017–1019`, após apenas três skips: em Valentine/Easter ela produz `CF → CF → EF` quando os três cookies ficam em tela. Ela permitiria `F + DH + 2BS + EF + CF`, mas tem margem menor; deve ser tratada como plano B, não consumir a única Sugar Frenzy da ascensão sem estimativa atualizada.

### Combo escolhido e margem conservadora

O alvo é:

`F + DH + 2BS naturais + (EF + CF + F + BS do Quadcast)`

ou, removendo o Frenzy redundante:

`F + DH + 3BS + EF + CF + 1 cookie preservado`

O menor prédio atual tem 478 unidades, logo um BS pessimista vale aproximadamente `48,8×`. Usando o poder de clique observado, três BS nesse piso, apenas seis segundos e os 200 cliques/s nominais:

- núcleo `F × DH × 3BS × EF × CF`: aproximadamente `6,31e12×` por clique;
- produção de cliques antes dos multiplicadores finais: aproximadamente `6,99e70`;
- com Golden Switch `1,5×`, Sugar Frenzy `3×`, os três loans `3,6×`, Radiant Appetite `2×` e apenas um cookie em tela para Dragon's Fortune `2,23×`: aproximadamente **`5,05e72`**.

Esse piso já é cerca de `5×` a meta e ainda exclui Godzamok, Mokalsium e Garden de produção. Ele só é válido se os três BS permanecerem fortes: nunca vender, durante Godzamok, o tipo de prédio associado a qualquer BS ativo. A taxa real do clicker deve ser medida antes da tentativa; se ficar abaixo do piso aceito, Godzamok fornece a margem adicional.

### Preparação, na ordem

1. Exportar um save de backup. Desligar Auto Ascensão, auto-Grimoire e coletor automático de Golden Cookies.
2. Avançar spells até `spellsCastTotal = 1222`, sem ultrapassar. Confirmar seed `eqomd` e versão `2.053` antes e depois.
3. Subir o escritório do Stock Market até liberar os três loans. O save já atende aos requisitos de Bank/Cursor e quantidade de Cursors; fazer isso antes da janela crítica.
4. Configurar Pantheon sem gastar lump: Godzamok em Diamond, Mokalsium em Ruby e Muridal em Jade. Como há três swaps, os slots podem ser preparados agora e permanecer assim.
5. Usar Garden nível 10 em Clay com Golden Clovers e Nursetulips maduras para frequência. Equipar Reaper of Fields e Epoch Manipulator enquanto busca naturais.
6. Estender Frenzy e acumular, nessa ordem prática, Dragon Harvest e **dois Building Specials distintos**, com tempo suficiente para o Quadcast e a janela final. Recomeçar se um deles estiver perto de expirar.
7. Trocar para Valentine's Day ou Easter. Confirmar que não há Dragonflight e que não há shimmer estranho em tela.
8. Depois do último natural: ligar Golden Switch, trocar as auras para Dragon's Fortune + Radiant Appetite, congelar o Garden e ativar Sugar Frenzy.
9. Ativar os três loans perto da janela; o Pawnshop loan é o mais curto e deve ser o último deles.

### Execução crítica

1. Ajustar Wizard Towers para a rota nível 10 `601 → 1` e confirmar custos/mana no runtime. Pela fórmula 2.053, são `108` de mana máxima e custo `67` em 601, depois `34` e custo `27` em 1 com Supreme Intellect; sem a aura, os custos esperados são `74` e `30`, e a rota ainda fecha.
2. Cast `1222` (EF), vender até 1 torre e cast `1223` (CF).
3. Recomprar 600 torres, gastar **um** Sugar Lump para recarregar mana, cast `1224` (F), vender novamente até 1 e cast `1225` (BS).
4. Não clicar nenhum shimmer durante o Quadcast. Confirmar os quatro resultados por `force`.
5. Vender em lote os prédios baratos autorizados para Godzamok, excluindo Temple, Wizard Tower e todos os tipos associados aos três BS.
6. Clicar o BS de FtHoF, depois CF e **EF por último**. Deixar o Frenzy redundante em tela para Dragon's Fortune.
7. Iniciar imediatamente o clicker e parar antes de EF ou Devastation expirar.
8. Confirmar por duas leituras `Game.cookiesEarned >= 1e72` e a conquista id `593`. Só então recomprar e comprar os prédios até 700.

### Fechamento das demais conquistas

1. **Mesmo combo:** os quatro marcos de produção até `1e72` e o marco de `1e56` CpS devem cair em cascata.
2. **Depois do combo:** comprar 700 de cada prédio fecha `Everyone everywhere all at once`, `Where is my mind`, `Introspection`, `Sexcentennial and a half` e `Septcentennial`.
3. **Garden:** plantar 36 Baker's Wheats, colher apenas maduras e repetir 28 ciclos; faltam 999 colheitas. É uma automação separada do combo.
4. **Caramelized/Golden lump:** manter o jogo aberto, Grandmapocalypse apaziguado e Dragon's Curve + Reality Bending quando um novo lump for escolhido. Caramelized fecha a conquista normal; Golden fecha a shadow. Lumps de Garden, `Sweet` e sacrifício não contam como Golden Sugar Lump.
5. **Seven horseshoes:** faltam 15.087 cliques. O modo passivo usa frequência máxima e auto-coleta; o método rápido de Dragon Orbs + Skruuia + Cookie Chains é estimado pelo wiki em cerca de 270 cliques/h, ainda aproximadamente 56 horas ativas para o saldo atual.
6. **When the cookies ascend just right:** fazer somente depois das conquistas desta ascensão; em uma nova ascensão, ajustar o **saldo** para exatamente `1.000.000.000.000` e ascender.
7. **Third-party/Cheated:** opcionais e isoladas, com consentimento explícito, pois exigem add-on/cheat.
8. **Dungeons:** aguardar uma versão que disponibilize o recurso; não há rota legítima em 2.053.

## 1. Objetivo e métrica correta

### Requisito exato

- **Runtime:** `Game.BankAchievements` contém a conquista de id `593`, nome `And a little extra`, descrição exibida “Bake 1 trevigintillion cookies in one ascension” e `threshold = 1e72`.
- **Runtime:** o ciclo nativo de achievements percorre `Game.BankAchievements` e concede cada item quando `Game.cookiesEarned >= threshold`. Portanto, a condição relevante é **assar pelo menos `1e72` cookies na ascensão corrente**.
- **Runtime:** o achievement estava `won = false` e `Game.HasAchiev('And a little extra') = false` na consulta.

### Quatro números que não podem ser confundidos

| Conceito | Campo observado | Significado | Serve como critério? |
| --- | --- | --- | --- |
| Cookies baked this ascension | `Game.cookiesEarned` | Total produzido desde a última ascensão. Gastar cookies não o reduz. | **Sim**; é a métrica do achievement. |
| Saldo atual | `Game.cookies` | Cookies disponíveis para compras, plantas, Golden Switch e demais custos. | Não; pode ser muito menor que o total assado. |
| Cookies totais | `Game.cookiesReset + Game.cookiesEarned` | Produção acumulada nas ascensões anteriores mais a atual. | Não; serve para progressão/prestígio, não para esta conquista. |
| Prestígio | `Game.prestige` e ganho calculado por `Game.HowMuchPrestige(...)` | Nível de prestígio já possuído e ganho projetado ao ascender. | Não; é consequência da produção acumulada. |

No snapshot final do estudo, o saldo era `1,0767e59`, os cookies assados nesta ascensão eram `1,1626e61` e o CpS sem buff era `2,4742e55`. O alvo ainda é cerca de `8,60e10` vezes o total assado na ascensão corrente. Isso demonstra por que a rota final usa três BS, EF e CF em vez de depender apenas do 100% Consistency reduzido.

## 2. Inventário de fontes

### Guias locais obrigatórios

Os arquivos em `docs/guides/` foram lidos integralmente, incluindo texto, tabelas e imagens relevantes, e não foram alterados.

| Fonte | Objetivo do guia | Técnicas abordadas | Relevância para este estudo |
| --- | --- | --- | --- |
| `DUALCASTING GUIDE.txt` | Registrar pontos convenientes de Dualcasting por nível de Wizard Tower. | Primeiro FtHoF, venda de torres, segundo FtHoF e tempos de regeneração; variante “lookas regen”. | Fonte local da tabela que deve orientar diagnóstico, nunca valores cegamente executáveis. |
| `Cookie Clicker v2.058 endgame combo guide.docx` | Explicar combos late/endgame sem savescumming e sem planner. | Scrying, preparação, Garden, Quadcasting, rotas de Grimoire, Godzamok, 100% Consistency, Double BS e Grail. | Principal fonte da sequência `F + DH + BS + CF + Golden Cookies preservados`. |
| `Cookie Clicker advanced combo guide.docx` | Catálogo de combos e fundamentos avançados. | Probabilidades aproximadas de FtHoF, auras, Golden Switch, loans, Sugar Frenzy, scrying, Dual/Quad/Hexcasting e Dragonflight. | Sustenta a escolha do 100% Consistency e os fallbacks. |
| `Combo Guide.docx` | Guia progressivo de earlygame a lategame. | Flexible Magic Cap, Dualcasting, Krumblor, Pantheon, Garden, otimizações antes e durante o combo. | Explica por que Dualcasting reduz custo ao reduzir a mana máxima e contextualiza Godzamok/Mokalsium/Holobore. |
| `SAVESCUMMING COMBO GUIDE.docx` | Execução de combos com savescumming e FtHoF Planner. | Quadcasts e casts maiores, multitabbing, Garden/offline ticking, rotas planejadas e Grail modificado. | Útil como teto de potência e como catálogo de riscos; não deve ser adotado silenciosamente pelo looper principal. |
| `the art of deriving information from and for gambler's fever dream.docx` | Explicar scrying e correlações de Gambler's Fever Dream. | GFD, RA confirm, preconfirming, offsets, ranges, alinhamento e previsão. | Define as condições que mantêm um scry válido e por que a previsão depende de seed, contador de spells, season, Dragonflight e condições de prédios. |

### Fontes externas

Consultadas em **29/09/2026**:

1. [Cookie Clicker advanced combo guide — Google Docs](https://docs.google.com/document/d/1vt8LsZin3wzfr3E5Awc5dOWjwye0VSq0l4WOpH7z2oQ/edit?tab=t.0#heading=h.jfnjciyaqkt2). O acesso visual pelo mecanismo web não estava disponível, mas o endpoint público de exportação em texto respondeu com o documento integral. O conteúdo coincide com o guia local avançado quanto a Dualcasting, 100% Consistency, Dragon's Fortune e Grail.
2. [Endgame combo guide — Cookie Clicker Wiki](https://cookieclicker.wiki.gg/wiki/Endgame_combo_guide). A página e a API fecharam a conexão ou retornaram `403`; foi possível consultar apenas o conteúdo indexado pelo mecanismo de busca. Esse índice confirmou a estrutura do 100% Consistency, o uso de quatro Golden Cookies preservados e a comparação com Double BS/Grail. As instruções detalhadas deste estudo, portanto, usam prioritariamente o `.docx` local v2.058.
3. [Grimoire — Cookie Clicker Wiki](https://cookieclicker.wiki.gg/wiki/Grimoire). Também bloqueado para abertura completa, mas o índice consultado confirmou a definição de Dualcasting, o custo base de FtHoF e tabelas de pontos convenientes. Há divergências de alguns números em relação ao guia local; por isso a futura automação deve calcular custos no runtime.
4. [Achievements — Cookie Clicker Wiki](https://cookieclicker.wiki.gg/wiki/Achievements). Confirma que shadow achievements não contam para a porcentagem normal nem concedem leite.
5. [Dungeons — Cookie Clicker Wiki](https://cookieclicker.wiki.gg/wiki/Dungeons). Confirma que as quatro conquistas de Dungeons são classificadas como “not technically achievable yet” na versão atual.
6. [Sugar Lumps — Cookie Clicker Wiki](https://cookieclicker.wiki.gg/wiki/Sugar_Lumps). Confirma tipos, efeitos, seleção ao nascer do próximo lump e que fontes alternativas fornecem lumps normais.
7. [Golden Cookie Achievements — Cookie Clicker Wiki](https://cookieclicker.wiki.gg/wiki/Golden_Cookie_Achievements). Confirma o alvo de 27.777 e compara a espera passiva com a estratégia ativa de Dragon Orbs/Chains.

### Hierarquia de confiança

1. Para a conquista e os campos de estado, vale o **runtime 2.053 observado**.
2. Para a estratégia, valem os **guias**, lembrando que o principal guia local declara versão 2.058, enquanto o runtime Steam observado é 2.053.
3. Para a arquitetura futura, valem as **hipóteses** deste documento, que exigem testes e simulação antes de qualquer comando mutável.

## 3. Combo recomendado

### Núcleo “100% Consistency”

**Guia:** a forma canônica é `F + DH + BS + CF + 4GC`:

1. manter um Frenzy longo;
2. obter naturalmente Dragon Harvest e depois Building Special, normalmente com Golden Clovers e Nursetulips maduras em Clay, `Epoch Manipulator` e `Reaper of Fields`;
3. ter um `Click Frenzy` previamente scryed como próximo resultado conhecido de FtHoF;
4. executar a rota de Grimoire e identificar inequivocamente qual cookie é o CF;
5. depois de o último Golden Cookie natural já ter surgido, ligar Golden Switch e os multiplicadores finais;
6. clicar apenas o CF e deixar os demais Golden/Wrath Cookies em tela;
7. trocar para `Dragon's Fortune + Radiant Appetite`, ativar os demais multiplicadores e executar a janela de cliques.

O nome “100% Consistency” é condicional: significa que, **dado um CF scryed ainda válido e uma execução correta**, o efeito-chave é garantido pelo procedimento do guia. Não significa que o setup apareça instantaneamente, que a execução humana/bot seja infalível ou que o ganho alcance `1e72` em qualquer save.

### Por que continua sendo uma boa baseline para o looper

- **Guia:** o alvo de scry, Click Frenzy, é muito mais comum e simples que Elder Frenzy.
- **Guia:** os três buffs-base são obtidos de naturais; o resultado crucial de FtHoF é conhecido antes da janela crítica.
- **Hipótese:** a máquina de estados pode separar uma espera longa e segura de uma janela mutável curta, com precondições verificáveis.
- **Hipótese:** falhas são mais fáceis de classificar: scry inválido, buff expirado, shimmer ausente, mana/custo divergente ou ação não confirmada.
- **Guia:** a potência é relevante — “centenas de milhares de anos de CpS” no contexto do guia — sem a raridade extrema do Grail.

### Baseline sem Sugar Lump

Um Dualcast faz dois FtHoF com a mesma barra de mana:

1. cast com muitas Wizard Towers;
2. venda controlada até um segundo ponto;
3. confirmação de nova mana máxima e novo custo;
4. segundo cast com a mana restante.

Se um dos dois casts for o CF scryed, o outro pode fornecer um resultado adicional ou ficar em tela para `Dragon's Fortune`. Um natural posterior também pode ser preservado. Porém:

- dois casts, dos quais um é clicado como CF, deixam no máximo um FtHoF não clicado;
- com um natural adicional preservado, a rota típica terá dois cookies em tela, não quatro;
- chegar a quatro sem Sugar Lump exige fontes adicionais, como Fortune, Dragon Orbs ou eventos de duplicação, que não são 100% repetíveis e podem interferir no setup;
- Quadcasting é “Dualcast + recarga por Sugar Lump + Dualcast” e foge do requisito de não usar lump na obtenção dos resultados adicionais de FtHoF.

Assim, o looper deve chamar a rota de `100% Consistency sem lump` apenas de **variante reduzida**, nunca de `+4GC`. Ela é adequada para validar o executor, mas foi superada como tentativa final pela rota planejada da seção 0.

### Fallbacks e comparação com Grail

| Rota | Potência | Repetibilidade | Uso recomendado |
| --- | --- | --- | --- |
| `F + CF`, `F + BS + CF` ou `F + DH + CF` | Menor | Alta | Setup combo, validação inicial do detector e saves ainda distantes do endgame. |
| `F + DH + BS + CF` com Dualcast e 1–2 cookies preservados | Alta | Alta após scry | Baseline de validação sem Sugar Lump. |
| `F + DH + BS + CF + 4GC` canônico | Mais alta pelo `Dragon's Fortune` | Alta após scry, mas execução maior | Fase posterior; normalmente Quadcasting e, portanto, um Sugar Lump. |
| `F + DH + 2BS + CF` | Mais forte | Intermediária; o guia cita cerca de 48% para o resultado desejado após scry de BS | Fallback quando o estimador mostrar que a variante reduzida não basta. |
| `F + DH + BS + CF + DF` | Mais forte | Menor e sensível à ordem | Fallback avançado; FtHoF deve ser lançado antes de DF e o natural deve ser clicado antes do cookie de CF. |
| Grail: `F + DH + BS + EF + CF + DF` | Máxima entre as rotas no-scum estudadas | Muito baixa; requer scry de EF e execução complexa | Último recurso, não primeira política automática. |
| Grail modificado planejado `F + DH + 3BS + EF + CF` | Muito alta e com margem estimada | Determinística no Quadcast `1222–1225`; difícil apenas na pilha natural | **Rota final deste save.** |

**Guia:** no Grail, mesmo após o raro scry de EF, o guia local apresenta aproximadamente 46% para uma rota forte com CF, mas apenas cerca de 3% para o resultado completo com DF+CF. Isso é inadequado como primeiro looper autônomo.

## 4. Dualcasting

### Mecânica validada

- **Runtime:** FtHoF tem `costMin = 10` e `costPercent = 0.6`.
- **Runtime:** `getSpellCost` usa a mana máxima e aplica redução de `Supreme Intellect` antes de arredondar para baixo.
- **Runtime:** a mana máxima usa quantidade e nível das Wizard Towers; `computeMagicM` também limita a mana atual ao novo máximo.
- **Guia:** depois do primeiro cast, vender torres reduz a mana máxima e o custo de FtHoF. A mana restante pode então cobrir o segundo cast sem recarga por lump.

No snapshot, havia 726 Wizard Towers nível 10, `116/116` de mana e FtHoF custava `71` com `Supreme Intellect` ativo. Esse valor confirma que aura, quantidade, nível e versão alteram o cálculo; a tabela abaixo não deve ser usada sem revalidação.

### Tabela local por nível de Wizard Tower

Notação: `antes → depois | tempo`. “Antes” é a quantidade de torres no primeiro cast; “depois”, a quantidade após a venda e antes do segundo cast; “tempo” é o **tempo de recarga reportado pelo guia**, em segundos. Não foi cronometrado neste estudo.

| Nível | Primeiro ponto conveniente | Ponto conveniente ótimo |
| ---: | ---: | ---: |
| 1 | `321 → 21 | 3015 s` | `537 → 37 | 2786 s` |
| 2 | `314 → 14 | 3015 s` | `530 → 30 | 2786 s` |
| 3 | `308 → 8 | 3015 s` | `524 → 24 | 2786 s` |
| 4 | `303 → 3 | 2997 s` | `408 → 8 | 2847 s` (`627 → 27 | 2801 s`*) |
| 5 | `401 → 1 | 3177 s` | `403 → 3 | 2847 s` (`622 → 22 | 2801 s`*) |
| 6 | `401 → 1 | 2864 s` | `503 → 3 | 2862 s` (`617 → 17 | 2801 s`*) |
| 7 | `401 → 1 | 3194 s` | `509 → 9 | 2893 s` (`610 → 10 | 2801 s`*) |
| 8 | `501 → 1 | 2862 s` | `501 → 1 | 2862 s` (`610 → 10 | 2801 s`*) |
| 9 | `501 → 1 | 3000 s` | `602 → 2 | 2907 s` (`2801 s`*) |
| 10 | `501 → 1 | 3032 s` (`3017 s`*) | `601 → 1 | 2907 s` (`2801 s`*) |

\* O guia chama a alternativa de **lookas regen**: manter o máximo de mana tão baixo quanto possível acima de 100 durante a regeneração. Nas linhas 9 e 10 da coluna ótima, o arquivo local fornece apenas o tempo alternativo, sem outro par de quantidades.

O índice atual da página de Grimoire do wiki.gg diverge em alguns pares e segundos, por exemplo níveis 2, 4, 5, 6 e 8. Isso pode refletir revisão do guia, aura ou versão. A política correta é: **calcular o plano no runtime, usar a tabela apenas como candidato e recusar a venda se o custo recalculado não provar o segundo cast**.

### Variáveis que precisam ser observadas antes de automatizar

1. versão do jogo e disponibilidade das APIs;
2. quantidade e nível reais das Wizard Towers;
3. mana atual `M.magic` e máxima `M.magicM`;
4. custo real de FtHoF por `M.getSpellCost(spell)` antes e depois da venda;
5. auras `Supreme Intellect` e `Reality Bending`, pois alteram custo e/ou backfire;
6. buffs `Magic adept` e `Magic inept` e a chance efetiva de backfire;
7. quantidade de Golden/Wrath Cookies já em tela, pois cada um aumenta o risco de backfire de FtHoF;
8. seed, total de spells, season, Dragonflight ativo e condições de prédios que preservam ou alteram o scry;
9. resultado esperado de cada cast e identificação do shimmer criado por ele;
10. tempo restante de Frenzy, Dragon Harvest e Building Special;
11. building associado ao BS ativo, especialmente se for Wizard Tower;
12. saldo para recomprar torres e política de recuperação.

### Riscos da venda e recompra

- Vender torres durante um BS de Wizard Tower reduz imediatamente a força desse BS.
- A venda pode ativar Godzamok antes da hora; vendas posteriores aumentam o multiplicador, mas não reiniciam a duração de `Devastation`.
- Recomprar muda o CpS, os Building Specials elegíveis e o custo/máximo de mana.
- A execução perde cookies na diferença entre compra e revenda e pode ficar sem saldo para restaurar o setup.
- A venda consome segundos de buffs curtos; qualquer UI lenta, lote incorreto ou confirmação atrasada pode perder CF/BS.
- O detector atual coleta Golden Cookies automaticamente por padrão; se continuar ativo, ele pode destruir os cookies que deveriam permanecer em tela.
- Um segundo cast inesperado pode produzir wrath, backfire ou alterar o contador de spells, invalidando planos subsequentes.

### Conveniente, ótimo e planejado

- **Dualcasting conveniente:** usa o primeiro par simples por nível; favorece poucos lotes de venda e menor risco operacional.
- **Dualcasting conveniente ótimo:** usa um par que reduz o tempo de recuperação, ainda tentando permitir vendas rápidas em grupos previsíveis. Não é sinônimo de maior ganho no combo atual.
- **Dualcasting planejado:** calcula quantidade inicial/final, aura, mana e resultados da seed para o save real. Pode usar scrying, season alignment, RA confirm, Flexible Magic Cap ou rotas GFD.
- **Variantes com savescumming/planner:** escolhem resultados futuros e podem chegar a casts maiores. Devem ser um modo separado, explicitamente habilitado, nunca um comportamento oculto do looper no-scum.

## 5. Pré-requisitos e cobertura atual do bot

### Inventário técnico da bridge, automações, UI e testes

- A bridge CDP serializa leituras por `RLock` e possui snapshots tipados de Ascensão, Garden e Stock Market.
- O Grimoire atual lista spells e possui uma ação que lança a spell selecionada quando a mana está cheia; não há snapshot autônomo de mana/custo/seed.
- Golden Cookie é lido apenas como o primeiro shimmer encontrado e a automação pode executar `pop()`; não há lista tipada com origem, força prevista e política de preservação.
- A automação de Garden já separa simulação e execução e possui leituras/ações de sementes, canteiro, solo e congelamento, mas seu objetivo atual é a coleção de sementes, não o layout de combo.
- O Stock Market lê ativos, brokers e lucro, mas não expõe estado/comandos de loans.
- Auto Ascensão lê saldo, prestígio e prédios, porém omite `Game.cookiesEarned`, achievement alvo e nível das Wizard Towers.
- A UI tem abas de Automações, Stock Market, Garden, Auto Ascensão, Atividade e Configurações; não há painel do combo.
- Os testes cobrem Grimoire, Garden, Stock Market e Auto Ascensão isoladamente; não há modelos, estado ou testes de combo.

### Matriz de requisitos

| Item | Prioridade | Papel no combo | Estado observado | Bot lê/controla hoje? | Extensão necessária |
| --- | --- | --- | --- | --- | --- |
| Achievement e `cookiesEarned` | **Obrigatório** | Medir progresso e conclusão real. | `1,1626e61`; achievement ausente. | Não em um snapshot público. | Adicionar ambos ao snapshot de combo e confirmar por duas leituras. |
| Buffs ativos | **Obrigatório** | Reconhecer F, DH, BS, CF, duração e potência. | Nenhum buff ativo. | Não estruturado. | Ler `Game.buffs` com frames/segundos, multiplicadores e building associado. |
| Golden/Wrath Cookies | **Obrigatório** | Atribuir naturais/FtHoF, clicar apenas o CF e preservar excedentes. | Nenhum em tela. | Lê um e pode coletá-lo; automação global vem habilitada por padrão. | Snapshot de todos os shimmers, origem/`force`, id e vida; exclusão mútua com coletor. |
| Grimoire e mana | **Obrigatório** | Scry, primeiro cast e Dualcast. | Disponível; `116/116`; FtHoF `71`. | Lista spells; cast mutável somente com mana cheia. | Snapshot somente leitura, custo/chance, ação por plano e confirmação de shimmer. |
| Wizard Towers | **Obrigatório** | Determinam máximo/custo; são vendidas no Dualcast. | 726, nível 10. | Quantidade aparece no snapshot de ascensão; nível e venda não. | Leitura conjunta de nível/quantidade/preço e venda/recompra transacional com limites. |
| Resultado esperado de FtHoF | **Obrigatório** para consistência | Garantir CF e detectar desvios. | Não havia cast/shimmer a observar. | Não há previsão; shimmer bruto pode ser lido após surgir. | Modelo explícito de scry e invariantes; não reproduzir RNG sem testes de versão. |
| Krumblor/Reaper of Fields | **Obrigatório** para DH | Habilitar Dragon Harvest ao clicar natural. | Auras atuais: Breath of Milk + Supreme Intellect. | Não. | Snapshot das duas auras e comando guardado de troca. |
| Dragon's Fortune | **Obrigatório** para monetizar cookies preservados | `+123% CpS` por cookie em tela, multiplicativo, conforme runtime. | Desbloqueada pelo dragão, não equipada. | Não. | Leitura/troca e confirmação de quantidade de shimmers preservados. |
| Radiant Appetite | **Recomendado** | Multiplicador final de produção. | Não equipada. | Não. | Mesma extensão de auras. |
| Supreme Intellect/Reality Bending | **Condicional** | Alteram custo, backfire e rotas de Grimoire. | Supreme Intellect equipada; Reality Bending não. | Não. | Incluir `auraMult` no snapshot e no simulador de mana. |
| Pantheon/Godzamok | **Obrigatório** para a rota otimizada | `Devastation` na venda antes dos cliques. | Três swaps; slots vazios. | Não. | Preparar Godzamok/Mokalsium/Muridal antes da espera e confirmar os slots. |
| Mokalsium | **Recomendado** | Produção final via leite. | Disponível, mas fora dos slots. | Não. | Preparar em Ruby e preservar Temple. |
| Holobore | **Opcional/recomendado** | Multiplicador final depois de todos os GCs necessários. | Não equipado. | Não. | Troca somente após confirmar que nenhum GC precisa ser clicado. |
| Vomitrax/Selebrak/Muridal | **Recomendado** no setup | Duração/frequência/produção enquanto espera. | Slots vazios. | Não. | A rota final usa Muridal em Jade; variantes de espera precisam recalcular swaps. |
| Garden de frequência | **Obrigatório** para empilhar dois BS naturais com praticidade | Golden Clovers + Nursetulips maduras em Clay aceleram naturais. | Farm nível 10; plantas-chave desbloqueadas; um lote ocupado; Fertilizer. | Lê e controla ações básicas. | Novo planejador de layout de combo, separado da Fazendeira de coleção. |
| Garden de produção | **Recomendado** | Replantar Whiskerblooms, Glovemorels ou Thumbcorns para a janela final. | Whiskerbloom e Thumbcorn desbloqueadas; Glovemorel não apareceu entre as sementes liberadas. | Ações básicas existem. | Simulação do ganho e guarda de tick/maturidade. |
| Golden Switch | **Recomendado** | Multiplicador após o último natural, sem impedir FtHoF. | Disponível e desligado. | Não. | Ler toggle/custo e acionar somente após confirmar último natural. |
| Sugar Frenzy | **Recomendado** na tentativa final | `3×` por uma hora, uma vez por ascensão. | Disponível e inativa; 1.205 lumps. | Só há colheita de lumps, não ativação. | Ativar apenas após todos os gates da tentativa final. |
| Loans | **Recomendado** no último combo da ascensão | `1,5×`, `2×` e `1,2×`, ou `3,6×` combinados. | Nenhum ativo; escritório nível 0, mas requisitos para o nível máximo atendidos. | Stock snapshot não os expõe. | Subir escritório antes; ativar os três na ordem de duração. |
| Prédios para BS/Godzamok | **Obrigatório** | Força do BS, vendas e recuperação. | Todos os 20 tipos presentes; 478–936 unidades. | Lê quantidade e compra lotes; não vende. | Identificar building do BS, orçamento e lista de venda; excluir Temple e alvos protegidos. |
| Clicker | **Obrigatório** para materializar CF | Gerador de cliques físicos já existe. | Disponível, estado não alterado neste estudo. | Sim. | Medir CPS de cliques, latência, foco e parada no limite de segurança. |

### Diagnóstico do save observado

O save possui todos os recursos estruturais, mas **não está pronto para executar agora**: o contador ainda está em `1014`, não há a pilha natural, o Garden não está no layout de frequência, as auras são Breath of Milk + Supreme Intellect e os slots do Pantheon estão vazios. Em compensação, há três swaps, 1.205 lumps e uma janela planejada forte. Isso reforça que o looper deve preparar e provar o estado, não simplesmente disparar FtHoF ao ver mana cheia.

## 6. Máquina de estados do futuro looper

Os timeouts abaixo são propostas iniciais. Buffs devem ser comparados em frames e convertidos pela taxa real do jogo; a máquina nunca deve assumir que um `sleep` preservará a janela.

| Estado | Entradas observáveis | Ações futuras | Timeout proposto | Sucesso | Falha | Custo e reversibilidade |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Preparação e diagnóstico | Versão, tela, `cookiesEarned`, achievement, automações concorrentes, mana, auras, Pantheon, Garden, Switch, loans, prédios. | Somente ler; gerar plano e estimativa; exigir autorização do modo real. | 5 s ou 3 snapshots consistentes. | Snapshot completo e plano viável. | Campo obrigatório ausente, versão não suportada, swaps/recursos insuficientes. | Sem custo; totalmente reversível. |
| 2. Espera por buffs naturais | Buffs, shimmers, próximo spawn, Garden e duração restante. | No modo real futuro, clicar apenas naturais permitidos; nunca FtHoF preservado. | 30 min por tentativa, renovável pelo usuário; também limitado pela vida dos buffs. | Frenzy longo e progresso rumo a DH/BS. | F expira, Garden perde frequência, GC inesperado ou coletor concorrente atua. | Cliques em GCs são irreversíveis; abortar e voltar a esperar. |
| 3. Validação de DH e BS | Nomes, `time`, `maxTime`, potência do BS e building associado. | Congelar decisão por um snapshot atômico. | 1 s e margem mínima configurável de buff. | F+DH+BS com tempo suficiente. | Ordem inadequada, BS fraco/protegido ou duração insuficiente. | Sem custo adicional; esperar nova base. |
| 4. Preparação de Garden/Pantheon/auras | Layout, solo, tick, slots, swaps, auras e season. | Colher/replantar layout final; trocar auras; inserir Godzamok conforme plano. | 5–10 s, sempre menor que a margem dos buffs. | Layout e slots confirmados. | Tick iminente, swap falha, planta/seed ausente. | Colheita e swaps têm custo/cooldown e são parcialmente irreversíveis. |
| 5. Primeiro FtHoF | Scry válido, mana atual/máxima, custo, chance de backfire, shimmers anteriores. | Cast único e registro do novo shimmer. | 1 s. | Mana caiu pelo custo esperado e exatamente um shimmer atribuível surgiu. | Cast recusado, backfire divergente, shimmer ambíguo. | Mana e contador de spells são irreversíveis; entrar em falha segura. |
| 6. Dual/Quadcasting | Torres atuais, alvo calculado, saldo, mana, contador `1222`, BS ativo e tempo. | Executar `601→1`, reler custo, recomprar, usar uma recarga autorizada e repetir. | 3–6 s, condicionado ao buff mínimo restante. | Quatro casts confirmados como EF/CF/F/BS. | Contador, quantidade, custo, mana, resultado ou building protegido diverge. | Vendas custam cookies; a recarga gasta um lump e inicia cooldown de 15 min. |
| 7. Validação de CF/BS e preservação | Todos os shimmers, origem, `force`, vida e scry; buffs após cada clique. | Identificar CF; clicar somente o cookie autorizado; marcar os demais como preservados. | 1 s por decisão, antes de qualquer shimmer expirar. | CF ativo e conjunto preservado conhecido. | CF ausente, cookie expirou, clique errado, DF ativo cedo demais. | Clique é irreversível; abortar otimizações e aproveitar fallback seguro. |
| 8. Preparação final de multiplicadores | Último natural já surgiu, CF ativo, shimmers restantes, saldo, swaps, loans, Switch e auras. | Golden Switch; `Dragon's Fortune + Radiant Appetite`; loans; Holobore/Mokalsium; Sugar Frenzy apenas se autorizada. | 3–8 s e margem mínima do menor buff. | Multiplicadores confirmados e clicker pronto. | Natural ainda pendente, custo do Switch inviável, swap/loan indisponível. | Switch/loans têm custo e cooldown; Sugar Frenzy gasta lump e é irreversível. |
| 9. Janela de clique | Buffs, CpS, contador de cliques, foco, `cookiesEarned` inicial e tempo mínimo restante. | Iniciar clicker; opcionalmente comprar upgrades autorizados; parar antes da expiração. | Até `min(buff.time) - margem`. | Ganho cresce e clicker para no limite. | Foco perdido, CpS/ganho não cresce, buff some ou parada solicitada. | Produção é positiva; compras são irreversíveis. |
| 10. Avaliação e achievement | `cookiesEarned`, saldo, delta, achievement e buffs remanescentes. | Duas leituras; registrar ganho e decisão. | 2 s ou 2 snapshots. | `cookiesEarned >= 1e72` e achievement confirmado. | Ganho abaixo do estimado ou confirmação ausente. | Somente leitura. Nunca ascender automaticamente neste estado. |
| 11. Recuperação e falha segura | Inventário vendido, auras/slots, automações concorrentes, erros. | Parar clicker/casts/vendas; oferecer recompra previamente orçada; restaurar apenas itens autorizados. | 5 s para estabilizar; depois intervenção. | Estado estável e relatório completo. | Runtime desconectado ou recuperação ambígua. | Recompra custa cookies; swaps/cooldowns podem não ser reversíveis. |
| 12. Nova tentativa | Mana, torres, Garden, swaps, cooldowns e decisão do usuário. | Recalcular do zero; aguardar regeneração ou encerrar. | Aproximadamente 2.786–3.194 s para os pontos tabelados, mas usar ETA do runtime. | Novo diagnóstico aprovado. | Recursos não se recuperam ou meta já atingida. | Espera é reversível; nenhuma repetição automática após erro ambíguo. |

## 7. Plano de implementação futura

### Incremento 1 — observabilidade somente leitura

- Criar `app/models/combo.py` com snapshots imutáveis de economia, buffs, shimmers, Grimoire, auras, Pantheon, Garden, loans, Switch e prédios.
- Adicionar `get_combo_snapshot()` à bridge em uma única avaliação JavaScript, sem qualquer chamada mutável.
- Incluir `Game.cookiesEarned`, `Game.cookiesReset`, achievement, versão e timestamp monotônico/frame.
- Expor todos os shimmers, não apenas o primeiro, preservando id, tipo, wrath, vida, origem observável e `force` quando disponível.
- Testar payload ausente, `NaN`, minigame não carregado, versões 2.053/2.058 e desconexão.

### Incremento 2 — estimador e simulador

- Criar `app/core/combo_estimator.py` para estimar ganho conservador usando CpS/click base, poder do BS real, quantidade de cookies em tela, auras, Garden, Godzamok, loans, Switch e taxa medida do clicker.
- Criar um simulador de Dualcast que avalie quantidades candidatas sem vender torres, chamando as mesmas fórmulas observadas ou uma função de runtime puramente calculadora.
- Calcular intervalos pessimista/esperado/otimista; liberar modo real somente se o cenário pessimista tiver margem configurável sobre `1e72` ou se o usuário autorizar uma tentativa de progresso.
- Incorporar primeiro um planner **somente leitura**, travado por versão e validado contra vetores conhecidos; qualquer execução continua sendo outro incremento.

### Incremento 3 — detector de janela sem ações

- Criar `app/core/combo_policy.py` para reconhecer F, DH, BS, scry válido, margem de tempo e interferências.
- Exibir na UI “aguardando”, “janela candidata”, “janela rejeitada” e o motivo.
- Desabilitar logicamente o coletor global de Golden Cookies no modo de combo simulado; inicialmente, apenas alertar se ele estiver ativo.
- Gravar um relatório reproduzível do plano, sem seed completa ou save em logs.

### Incremento 4 — assistência manual

- Adicionar uma aba “Combo” com checklist e próximos passos, ainda sem mutações.
- Permitir que o usuário confirme manualmente scry, season e origem dos shimmers.
- Cronometrar execução humana e calibrar timeouts antes de automatizar vendas/swaps.

### Incremento 5 — comandos mutáveis pequenos e guardados

Implementar um comando por vez, cada um com pré-condição e pós-condição no mesmo round-trip CDP:

1. cast de FtHoF com custo/mana/scry validados;
2. venda limitada de Wizard Towers, sem segundo cast automático;
3. Dualcast completo após testes do passo anterior;
4. troca de aura;
5. Pantheon;
6. Golden Switch e loans;
7. layout de Garden;
8. venda/recompra de Godzamok;
9. clicker na janela final.

Cada família deve nascer desligada, exigir confirmação explícita e possuir orçamento máximo de cookies/prédios/swaps/lumps.

### Incremento 6 — máquina de estados integrada

- Criar `app/core/combo_looper.py` com estados explícitos, cancelamento cooperativo e relatório de transição.
- Usar tokens de snapshot — versão, frame, ids de shimmers, contador de spells e quantidades — para impedir ações sobre estado obsoleto.
- Tornar Auto Ascensão, coletor de Golden Cookies, spam de Grimoire, Garden real e Stock Market mutuamente exclusivos com o looper.
- Nunca repetir automaticamente uma ação de resultado ambíguo.
- Nunca ascender, importar save, usar Sugar Lump ou ativar Sugar Frenzy sem autorização específica.

### Testes mínimos

- parsing e imutabilidade de cada snapshot;
- prova, por captura do JavaScript, de que simulação não contém `pop`, `castSpell`, `sell`, `buy`, `slotGod`, `SetDragonAura`, `takeLoan` ou toggle;
- custo de FtHoF com e sem Supreme Intellect/Reality Bending;
- candidatos de Dualcast para níveis 1–10 e rejeição quando runtime divergir da tabela;
- atribuição de shimmers naturais versus FtHoF e preservação por whitelist;
- BS de Wizard Tower, Temple protegido, saldo insuficiente e venda parcial;
- expiração de buffs entre precondição e comando;
- concorrência com coletor global e parada imediata;
- confirmação dupla de `cookiesEarned` e achievement;
- recuperação idempotente e erro seguro após desconexão.

## Decisões, riscos e pendências

1. A rota final é o Grail modificado `F + DH + 3BS + EF + CF`, com Quadcast sazonal `1222–1225` e um lump de recarga.
2. O Dualcast sem lump fica como baseline de teste; a janela rápida `1017–1019` é plano B.
3. A tabela local é documentação, não configuração executável; runtime sempre prevalece.
4. A estimativa conservadora da rota final é `5,05e72` antes de Godzamok/Mokalsium/Garden, mas a taxa real do clicker e a força real dos BS ainda devem ser medidas no gate final.
5. A versão observada é 2.053, enquanto o guia principal é 2.058. O planner deve recusar outra versão sem novos vetores de validação.
6. Pantheon tem três swaps e slots vazios; configurá-lo previamente não gasta lump. O Garden ainda precisa do layout de frequência.
7. O coletor automático de Golden Cookies e o auto-Grimoire são incompatíveis com a rota e precisam de exclusão mútua.
8. O acesso completo ao wiki.gg não foi possível; suas informações foram usadas apenas onde o índice corroborou os guias locais/runtime.
9. A previsão é frágil: qualquer cast adicional, mudança de seed/versão, season incompatível ou Dragonflight ativo invalida a sequência.
10. Quatro conquistas de Dungeons não são legitimamente obtíveis em 2.053; duas shadows exigem add-on/cheat e precisam de consentimento explícito.
11. Não houve validação prática de combo, cast ou venda; todas as observações do jogo foram somente leitura.

## Validações realizadas

- leitura integral dos seis guias locais e inspeção de suas tabelas/imagens relevantes;
- inspeção da bridge CDP, automações de Grimoire/Golden Cookie, Garden, Stock Market, Auto Ascensão, UI e testes;
- consulta externa integral do Google Docs por exportação pública em texto;
- tentativa de página e API do wiki.gg, com bloqueio registrado, seguida de consulta ao índice disponível;
- consulta CDP somente leitura ao runtime 2.053, incluindo achievement, economia, buffs, shimmers, mana, custo de FtHoF, auras, Pantheon, Garden, Golden Switch, Sugar Frenzy, loans e prédios;
- inspeção somente leitura de `computeMagicM`, `getSpellCost`, `getFailChance` e da condição nativa de achievements;
- enumeração das 21 conquistas ausentes e classificação em normais, shadows e Dungeons;
- previsão local dos casts `1014–21013`, com restauração do gerador global no mesmo turno síncrono, e validação específica das janelas `1017–1019` e `1222–1225`;
- cálculo conservador da rota final com o poder de clique, menor quantidade de prédios e ritmo nominal do clicker observados;
- nenhuma suíte de testes foi necessária: a única alteração é documental e nenhuma lógica de produção foi modificada.
