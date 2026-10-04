# Revalidação do combo — 03/10/2026

## Decisão

Priorizar `Frenzy + Dragon Harvest + 2 BS distintos + Elder Frenzy + Click Frenzy`, com Godzamok, auras finais, Golden Switch, Sugar Frenzy e loans configurados. O objetivo é aproveitar uma boa oportunidade em algumas horas; exigir um segundo BS natural reduz demais a chance de tentativa nesse horizonte. O terceiro BS aumenta o ganho por tentativa, mas o ganho por sessão pode ser zero se a oportunidade nunca chegar.

O bot procura a primeira pilha elegível, preserva multiplicadores extras que estiverem presentes e não abandona a sequência já alinhada por mais centenas de skips. Não implementa uma otimização global de ganho esperado: o prédio sorteado pelo BS de FtHoF, o Garden e o ritmo real de cliques continuam variáveis.

## Evidência do jogo, sem executar o combo

Leitura via CDP do Cookie Clicker **2.053**, em 03/10/2026, aproximadamente 17:49–17:59 (São Paulo). A sequência continuava no cast **1222**, com **108/108 mana**, 601 Wizard Towers de nível 10 e refill disponível:

`Elder Frenzy → Click Frenzy → Frenzy → Building Special`

O forecast com meta de 2 BS confirmou **zero skips e um BS natural necessário**. Na leitura, havia 1.173 lumps e Sugar Frenzy ainda não utilizada. Foram consultados o snapshot, o forecast e as funções carregadas de efeitos, buffs, vendas, loans e spawn; não foram lançadas spells nem consumidos recursos para testar o combo.

## Duração e ordem de execução

| Boost | Duração por ativação neste save | Consequência |
| --- | ---: | --- |
| Frenzy | 184 s | Pode acumular duração; natural é preferível para preservar o cookie extra. |
| Dragon Harvest | 143 s | Deve estar ativo com ao menos 12 s restantes. |
| Building Special | 72 s | Um natural com ao menos 12 s; spell ativada antes da troca de auras. |
| Click Frenzy | 30 s | Ativado depois das vendas. |
| Elder Frenzy | 14 s | Ativado por último; já sem Epoch Manipulator. |
| Godzamok / Devastation | 10 s | Principal limite da janela de produção. Vendas adicionais reforçam o multiplicador, mas não renovam um Devastation existente. |
| Sugar Frenzy | 1 h | ×3; a ativação e o gasto de um lump precisam ser confirmados. |
| Loan 1 | 120 min | Ativado apenas na tentativa final. |
| Loan 2 | 40,2 s | Ainda maior que a janela de Godzamok. |
| Loan 3 | 48 h | Ativado apenas na tentativa final; há juros posteriores. |

Os efeitos de cookies usam `ceil(duração_base × multiplicadores)`. O multiplicador verificado é 2,2666622, vezes 1,05 de Epoch durante a coleta. Os buffs já ativos conservam sua duração quando a aura muda. Por isso os 72 s do BS e os 14 s de EF pertencem a fases diferentes. CF/EF são ativados após a troca para Dragon's Fortune + Radiant Appetite.

Uma janela normal oferece cerca de **9 s programados de cliques**: 10 s de Godzamok menos 1 s de margem. O tempo efetivo também depende dos buffs restantes, da vida dos cookies preservados, da resposta CDP e da taxa real do clicker. O bot não assume que o ritmo nominal de 200 cliques/s seja efetivamente entregue, nem garante `1e72` com dois BS.

Se falta Frenzy natural, ativar o Frenzy da spell acrescenta ×7 à produção em vez de manter apenas o ×2,23 de um cookie extra para Dragon's Fortune. Com Frenzy natural suficiente, preserva o cookie redundante. Um terceiro BS natural já presente continua ativo e seu prédio é protegido.

## Espera: simulação de cenários, não previsão

Script reproduzível: `python docs/simulate_combo_wait.py`. São 10.000 sessões por cenário, seed local fixa, horizonte de três horas e nenhum acesso ao jogo.

O modelo usa o processo de spawn por frame `p=((t-min)/(max-min))^5`, a seleção condicional dos efeitos, a supressão de 80% da repetição do último efeito, duração acumulada, BS por prédio e 1% de cookies duplos. Não multiplica quatro probabilidades marginais. Os limites medidos foram 46,47–139,33 s; isso produz intervalo médio de **77,6 s**, incluindo 0,2 s para coleta.

| Cenário constante | Mediana da primeira oportunidade | Até 1 h | Até 2 h | Até 3 h |
| --- | ---: | ---: | ---: | ---: |
| Antigo: F + DH + 2 BS naturais, margem 15 s | Acima de 3 h | 0 observações | 0 observações | 0 observações |
| Novo: DH + 1 BS natural, margem 12 s; F pode vir da spell | 153 min | 22,7% | 41,7% | 55,8% |
| Novo com frequência dobrada, **hipótese** | 23 min | 85,8% | 98,1% | 99,8% |

Zero observações não significa impossibilidade. A simulação mede a **formação da pilha natural**, não o sucesso do combo ou a conquista: não inclui falhas de execução nem o BS de spell repetir o prédio do natural. Também não modela crescimento/morte das plantas, pausas, aceleração de cookie chains ou detalhes de storms. As probabilidades não são uma promessa para esta noite.

## Garden e limite de sessão

O Garden observado estava em Clay, com muitas Nursetulips jovens. Clay tem ticks de 15 min; Fertilizer, de 3 min. Crescer sempre em Clay prolonga muito a preparação. A nova política usa Fertilizer enquanto menos da metade das plantas ou Nursetulips estiverem maduras; depois volta para Clay. Fertilizer reduz temporariamente a força dos efeitos e acelera também o envelhecimento: a melhoria visa chegar antes a um canteiro produtivo, sem pressupor frequência constantemente dobrada.

O limite de espera padrão é **180 minutos**, configurável. Se não houver oportunidade válida, o bot encerra sem disparar uma pilha incompleta. A sequência permanece alinhada quando já estava alinhada; não há promessa de sucesso dentro do limite.

## Validações corrigidas

- Frenzy da spell substitui a exigência redundante de Frenzy natural.
- BS repetidos são detectados antes de Sugar Frenzy e loans; o lump de refill já gasto é informado, sem repetição automática.
- Corrigida a ativação de Sugar Frenzy em 2.053: o código anterior debitava um lump e chamava `buy(1)`, pulando o `clickFunction` que efetivamente ativa o buff. Agora chama a compra normal, suprime o prompt apenas durante a chamada síncrona autorizada, restaura a preferência e verifica buff, compra e débito de exatamente um lump. O retorno da compra não é suficiente: nessa versão pode ser zero mesmo após o callback completar a ativação.
- Loans em juros ou prestes a vencer bloqueiam antes do primeiro cast; a ativação de cada loan é confirmada.
- Um buff expirado ou shimmer novo antes da primeira spell faz revalidar, sem falha terminal e sem gasto final.
- Dragonflight, Cursed Finger, Clot e Building Debuff impedem a tentativa enquanto ativos.
- O clicker fica pronto antes dos buffs curtos; a janela inclui seus limitadores reais.
- Atingir a meta não desperdiça os segundos restantes de uma tentativa já em andamento.
- A interface mostra duração restante dos buffs e o limite de espera.

Os testes cobrem a máquina de estados e executam o JavaScript gerado contra um runtime isolado em Node.js. A validação no jogo real permaneceu somente leitura; a tentativa com gastos não foi usada como teste.
