# Farm de combos

A aba **Combo → Combo avançado** prepara e repete sequências de quatro magias. Não há meta de biscoitos nem parada por conquista: depois da janela de cliques, coleta os biscoitos restantes identificados, recompõe torres e prédios vendidos e prepara outra tentativa. Se faltar saldo livre para a recomposição, aguarda sem repetir o combo. O farm termina ao desligar, esgotar o orçamento de torrões ou detectar uma falha que exige revisão.

## Configuração principal

- **Gastar no máximo nesta sessão:** limite total de torrões desde o clique em Ligar. Inclui recargas de alinhamento, a recarga final e o frenesi de açúcar. O contador não reinicia entre combos. Zero impede gastos e encerra a execução. Cada tentativa usa pelo menos um torrão; com somente um restante, não ativa o frenesi de açúcar.
- **Manter reservado em biscoitos:** protege uma parte do saldo das compras de temporada, torres, construções, sementes e interruptor dourado. A reserva é calculada ao iniciar e atualizada ao concluir os ciclos, sem diminuir por causa das compras. Uma compra que não couber aguarda; o interruptor dourado opcional na finalização é ignorado se não couber. A reserva não impede vendas e sacrifícios de construções necessários ao combo.
- **Permitir preparar o Garden para o combo:** desmarcado não consulta nem altera plantas, solo ou congelamento. Marcado permite converter culturas desbloqueadas para o canteiro de coleta. Plantas fora do catálogo e descobertas bloqueadas são sempre preservadas.

As preferências são persistidas. **Opções avançadas** começa recolhida e guarda alcance de busca, bônus de construção desejados, intervalo de verificação, duração mínima de efeitos, renovação da busca, empréstimos, frenesi de açúcar, tratamento final das tulipas e pausa manual. O acompanhamento mostra os combos concluídos e os torrões gastos na sessão.

## Execução e espera

Ao ligar, o bot confirma os gastos, cria um backup chamado antes-do-combo, pausa as outras automações e impede a suspensão do computador. O backup não é restaurado automaticamente. A tela pode apagar normalmente.

A sequência contém frenesi de cliques, frenesi ancestral e pelo menos um bônus de construção. O padrão busca dois bônus de construções distintas no total. A previsão compara as duas famílias de temporadas com um gerador aleatório isolado e escolhe pelo ganho estimado em relação ao tempo de preparo e à exigência de efeitos naturais. A estimativa é comparativa, não uma garantia de ganho ou tempo. Não existe limite de produção que encerre o farm.

O plano é mantido enquanto suas condições forem válidas; mudanças de identificação do save, chance de falha ou contador ultrapassado exigem revalidação. Se o save mudar durante a execução, a automação interrompe. O Voo do dragão aguarda terminar antes de buscar uma sequência que precise do frenesi de cliques.

O preparo configura temporada, interruptor dourado desligado, Panteão, auras, 601 torres de magos de nível 10 e escritório dos empréstimos. O alinhamento usa Encanto do pechincheiro e reserva torrões para a tentativa final. Sem orçamento para recarregar durante o alinhamento, aguarda a regeneração natural. A execução exige mana cheia e recarga disponível. Os juros dos empréstimos aguardam terminar. O intervalo de renovação da busca não desliga o farm nem reinicia seu orçamento.

A sequência final usa 601 → 1 → 601 → 1 torres. Confirma bônus de construções distintas antes de gastar os multiplicadores finais, preserva os prédios desses bônus nas vendas e abre o frenesi ancestral por último. O clicker aproveita a janela útil, com margem para latência. O frenesi de açúcar só é usado quando ainda está disponível nesta ascensão e cabe no orçamento. Nos próximos ciclos, a automação continua sem ele.

## Garden autorizado

O canteiro livre de 6×6 usa faixas alternadas de 18 trevos dourados e 18 tulipas nutridoras. Plantas saudáveis do cultivo de coleta são preservadas, e espaços disponíveis são repostos em lote com validação de saldo e layout antes da primeira remoção. Fertilizante cresce até 60% do efeito potencial em Argila; depois mantém Argila até cair abaixo de 40%, evitando alternância por uma reposição isolada. Um congelamento manual é preservado; congelar desativa os benefícios do Garden.

Com a otimização final habilitada, após confirmar os bônus de construções distintas pode remover tulipas para retirar a penalidade de produção. Isso só ocorre se todo o canteiro contiver trevos e tulipas desbloqueados. Outras culturas, descobertas, dados desconhecidos ou congelamento fazem essa etapa ser ignorada. Os efeitos são recalculados, e não há replantio durante a janela de cliques. A próxima preparação recompõe o cultivo conforme o orçamento.

## Planejador para combos manuais

Abra **Combo → Planejador** para consultar as próximas 50, 100, 250 ou 500 magias de Forçar a Mão do Destino. **Magias antes: 0** corresponde ao próximo lançamento; o valor 5 significa avançar o contador em cinco magias antes de lançar aquele Forçar a Mão do Destino. A coluna **Contador** mostra o valor absoluto usado na previsão. Magias de preparação, como Encanto do pechincheiro, também avançam esse contador quando lançadas normalmente.

As colunas **0 biscoitos** a **3 biscoitos** mostram os resultados conforme a quantidade de biscoitos dourados em tela antes do lançamento, incluindo biscoitos da ira. A coluna correspondente à quantidade atual fica destacada. Cada biscoito em tela acrescenta 15 pontos percentuais à chance de falha. **[falha]** indica que a magia cria um biscoito da ira, podendo inclusive resultar em Frenesi ancestral. Passe o mouse no resultado para ver a chance de falha e o tipo do biscoito.

O seletor **Previsão** compara a temporada atual, as temporadas comuns ou Páscoa/Dia dos Namorados. Ele apenas muda a comparação: não troca a temporada no jogo. O Planejador considera os efeitos atuais que alteram a chance de falha, Voo do dragão e a quantidade de construções. Frenesi de cliques, Frenesi ancestral, Bônus de construção e Torrões de açúcar aparecem em destaque. O prédio de um bônus de construção só é definido ao abrir o biscoito.

**Acompanhar magias automaticamente** consulta a cada dois segundos enquanto o painel está visível. Conforme você usa magias, as quantidades de magias restantes são recalculadas a partir do contador novo. Desmarque para consultar somente pelo botão **Atualizar**. A consulta funciona com o bot pausado, não lança magias, não consome mana ou Torrões de açúcar e usa um gerador aleatório isolado. Ela aguarda durante restaurações e recuperação da conexão. Para executar o combo manualmente, desligue as automações que lançam magias ou coletam biscoitos dourados; o Planejador não altera essas preferências por conta própria.

As previsões mantêm as condições atuais para cada linha. Efeitos que expirem, novas construções ou mudanças de temporada podem alterar a sequência. O acompanhamento automático atualiza essas condições, mas não garante que uma previsão continuará válida após mudanças no jogo.

## Pausa manual e falhas

A opção avançada de pausa aguarda **Retomar combo** antes das últimas três magias de preparação de cada ciclo. Enquanto aguarda, o bot não lança magias, coleta biscoitos nem altera o Garden ou prédios; o jogo segue normalmente. Ao retomar, relê o jogo e revalida a sequência.

Falhas parciais ou resultados divergentes interrompem o farm, sem repetir automaticamente os gastos. Uma duplicação de construção nos bônus de magia encerra a tentativa parcial antes dos multiplicadores finais. Restaurações de prédios usam limites idempotentes e precisam ser confirmadas antes do próximo combo. Cookies expirados entre ciclos não são recriados; apenas os resíduos identificados na execução anterior são coletados.

O jogo e a conexão precisam permanecer abertos. O orçamento é por sessão: desligar e ligar novamente inicia uma nova contagem. As proteções de descobertas do Garden permanecem ativas em todos os ciclos.
