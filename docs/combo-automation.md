# Automação do combo endgame

A aba **Combo** prepara e tenta um Quadcast para a conquista **And a little extra**. O objetivo padrão é `1e72` cookies assados na ascensão atual. A execução real começa desabilitada e sempre pede confirmação.

## Como iniciar

1. Abra a aba **Combo** e clique em **Atualizar prévia**. A prévia apenas lê o runtime.
2. Confira o plano vivo, principalmente o cast inicial e os quatro resultados previstos.
3. Mantenha o Cookie Clicker e o bot abertos, marque **Habilitar execução real** e clique em **Iniciar e deixar rodando**.
4. Confirme o aviso. O bot cria um backup automático chamado `antes-do-combo`, pausa as demais automações e solicita ao Windows que não suspenda o computador enquanto o modo estiver ativo. A tela pode apagar normalmente.

O plano não é fixado no momento do clique. A seed, a season, o contador de spells, a mana, os buffs e os shimmers são relidos antes de cada ação; se o estado mudar, a janela é calculada novamente.

## Pausar para acompanhar a tentativa

Marque **Pausar quando faltarem 3 skips e aguardar Retomar** antes de iniciar.
Ao chegar a três skips ou menos, o modo fica **pausado — aguardando você**.
Não lança spells, gasta lumps, coleta cookies nem altera prédios ou Garden nessa
pausa. As demais automações continuam bloqueadas e o jogo segue normalmente:
a mana regenera, as plantas envelhecem e os buffs podem expirar.

Quando estiver pronto para acompanhar, clique em **Retomar combo**. O bot relê
o jogo, recalcula a janela, termina o alinhamento e volta a buscar os buffs
naturais necessários; retomar não dispara o Quadcast imediatamente. Essa pausa
acontece uma vez por execução. **Parar imediatamente** continua encerrando o
modo, inclusive enquanto está pausado. A opção é salva e vem desmarcada por
padrão.

## Estratégia executada

- Procura quatro FtHoF consecutivos contendo Elder Frenzy, Click Frenzy e pelo menos um Building Special.
- O padrão é **2 Building Specials distintos no total**: um natural e um de FtHoF. A janela já alinhada na season atual tem prioridade sobre gastar mais skips por um plano teoricamente maior.
- Alinha o contador com Haggler's Charm, a spell determinística segura de menor custo. Quando há Sugar Lump, orçamento e refill disponível, lança skips até a mana restante não pagar outra spell e só então recarrega. Sem refill disponível, espera a barra cheia antes de cada skip para favorecer a regeneração. Sempre para os skips ao chegar à janela planejada. A recarga respeita o cooldown de 15 minutos e o orçamento informado.
- Configura Valentine, Golden Switch desligado, Pantheon, auras de preparação, 601 Wizard Towers e o escritório necessário para os loans.
- Monta Golden Clover + Nursetulip. Usa Fertilizer para crescer e Clay quando pelo menos metade do canteiro e metade das Nursetulips estiverem maduras. O Garden é opcional para o disparo: assim que a pilha natural estiver pronta, não consulta nem altera o Garden antes do Quadcast.
- Coleta Golden/Wrath Cookies naturais enquanto procura Dragon Harvest + os BS necessários. Frenzy pode vir da própria sequência de FtHoF. Se o Frenzy natural tem margem suficiente, mantém o cookie redundante em tela para Dragon's Fortune; caso contrário, ativa o Frenzy da spell.
- Trata Cookie Storm como evento natural: drena somente os drops identificados pela engine e continua preparando o combo.
- Recompra pelo menos 601 Cursors depois dos sacrifícios necessários para liberar os loans, preservando essa venda no Godzamok.
- Revalida tudo em uma única chamada antes do Quadcast. Só então executa `601 → 1 → 601 → 1`, ativa os multiplicadores finais, vende os prédios seguros para Godzamok e inicia o clicker.

O clicker é armado **antes** dessa chamada para aproveitar os buffs curtos. A margem natural padrão é 12 s, o intervalo de verificação é 0,2 s e o limite de preparação/busca é 180 minutos. O limite encerra a busca sem forçar uma tentativa incompleta; não é uma garantia de sucesso. A pausa manual continua aguardando Retomar; o prazo decorrido é conferido ao retomar.

Depois dos casts, o bot ativa os BS e conta **prédios distintos**, antes de gastar Sugar Frenzy/loans. Uma duplicação encerra a tentativa parcial, informa o lump de refill já usado e preserva os boosts de uso único. Sugar Frenzy usa a ativação normal do jogo e só é confirmada com buff ativo e débito de um lump; loans em juros ou prestes a vencer bloqueiam antes dos casts. A janela de cliques considera os buffs necessários e a vida dos cookies preservados, desconta 1 s de margem e inclui a latência da chamada. Mesmo que a meta seja atingida antes, aproveita o restante da janela.

Os buffs exibidos no painel incluem seus segundos restantes. As durações verificadas, os cenários de espera e suas limitações estão em [Revalidação de 03/10/2026](revalidacao-combo-2026-10-03.md).

Ao reabrir o bot pela primeira vez nesta revisão, os antigos valores padrão `3 BS / 1 s / 15 s` são migrados para `2 BS / 0,2 s / 12 s`. Outros valores são preservados. Depois dessa migração, alterações manuais são respeitadas. Um processo já aberto precisa ser reiniciado para carregar o código novo.

Um Building Special de Wizard Towers não é aceito, pois deixaria de existir durante as vendas. Prédios associados a qualquer Building Special ativo também são preservados.

## Exclusividade e recuperação

Enquanto o modo está ativo, o detector comum, o spam do Grimoire, Stock Market, Garden normal, Auto Ascensão, coleta de lumps e atalhos manuais do clicker ficam pausados ou bloqueados. Ao terminar, os timers comuns voltam a funcionar; o clicker fica parado.

Se um buff expirar, aparecer um cookie ou a previsão mudar antes dos gastos, o bot desarma o clicker e revalida no próximo ciclo. Dragonflight e efeitos negativos incompatíveis também aguardam expirar. Inconsistências estruturais e falhas parciais entram em **erro seguro**. Numa falha parcial, o bot registra os lumps já gastos, não repete a tentativa automaticamente e tenta restaurar as Wizard Towers. Use **Parar imediatamente** para pedir uma parada cooperativa; uma operação atômica que já começou termina antes da thread encerrar.

## Limitações

- O bot não garante que a combinação aleatória natural aparecerá durante uma única noite.
- O jogo, o bot e a conexão CDP precisam permanecer abertos.
- Trocas do Pantheon usam worship swaps normais; não gastam Sugar Lumps.
- Sugar Frenzy e os loans são recursos de tentativa final e podem ter efeitos/penalidades posteriores no save.
- O backup automático é obrigatório para o início real, mas a restauração continua sendo uma decisão manual.
