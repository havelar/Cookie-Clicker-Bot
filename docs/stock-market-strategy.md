# Stock Market: limites por ativo e meta de lucro

Referência consultada em 26/09/2026: [código oficial do minigame](https://orteil.dashnet.org/cookieclicker/minigameMarket.js), especialmente `getRestingVal`, `tick`, `buyGood` e `sellGood`.

O jogo tem um preço de referência diferente por ativo: `10 × (id + 1) + nível do Banco − 1`. Há uma força de retorno à referência, mas também modos e movimentos aleatórios. A referência não é previsão, piso, teto nem garantia de recuperação em um prazo. **Gaseous assets exige $31.536.000** no contador nativo `M.profit`; Liquid assets exige $10.000.000. Compras descontam seu custo com overhead desse contador, e vendas somam a receita. Ações em carteira não contam como saldo até serem vendidas. Ascender reinicia esse saldo.

## Sugestão inicial implementada

- Comprar MAX com estoque zero e preço estritamente abaixo de 50% da referência, somente depois que a queda parar. Se a janela anterior ainda estiver em baixa, a reação precisa alcançar o percentual configurado para confirmar a recuperação.
- Ativar o acompanhamento do pico quando alcançar 100% da referência. Os limites podem ser personalizados em **Limites por ativo**, e são preservados entre execuções.
- Após ativado, vender MAX ao recuar 10% do maior preço observado. A saída por tendência anterior de alta seguida de queda percentual continua funcionando como saída antecipada acima do alvo.
- Há uma única estratégia de entrada. Os controles de ticks e percentual definem a janela analisada e a força mínima da recuperação, e também servem para a saída por tendência.
- Não comprar quando nem o alvo descontado do recuo de 10% cobre o custo atual estimado com taxas.

Exemplo com Banco nível 10 (o app usa o nível real):

| Ativo | Referência | Compra abaixo de | Ativa modo venda em |
| --- | ---: | ---: | ---: |
| Cereals, id 0 | $19 | $9,50 | $19 |
| Chocolate, id 1 | $29 | $14,50 | $29 |
| Cookies, id 13 | $149 | $74,50 | $149 |
| Publicists, id 16 | $179 | $89,50 | $179 |

Essas proporções são uma hipótese ajustável, não parâmetros comprovadamente ótimos. O histórico local analisado tinha cerca de dez horas contínuas e uma reinicialização do contador; isso não basta para estimar tempo até o achievement ou demonstrar a estratégia mais rápida. O limite universal de $20 não oferecia nenhuma entrada para vários ativos nessa amostra.

## Proteções e acompanhamento

O bot registra o custo unitário executado de suas novas compras, incluindo o overhead realmente pago. Contratar brokers depois não diminui retroativamente esse custo. A venda automática exige preço **estritamente superior** ao custo e revalida preço e referência de compra dentro da mesma execução JavaScript que envia a ordem. As compras também revalidam limite e estoque zero nesse instante.

Posições antigas não contêm a taxa histórica no save; para lotes únicos identificados pelo último preço pago, usa-se o teto conservador de 20% de overhead. Isso não reconstrói custo médio de compras manuais misturadas. Se um lote rastreado mudar de forma incompatível, a venda automática é bloqueada. Operações manuais continuam sob controle do usuário.

O histórico nativo tem prioridade nas decisões. Períodos separados por reinício de ticks recebem identificadores distintos, evitando preços antigos no lugar dos novos. Custos e picos ficam no JSON existente. O pico é zerado depois de uma liquidação confirmada.

**Meta** mostra o saldo nativo em relação a $31.536.000; **Lucro total** continua sendo a variação patrimonial da sessão, que é outra métrica. Se a venda das posições lucrativas já permite alcançar o achievement, o bot tenta liquidá-las sem esperar outra reversão. Compras automáticas param ao atingir a meta ou detectar o achievement. Tudo depende do toggle **Automação**; os ajustes menos frequentes ficam na aba **Configurações**.

Nenhuma regra assegura lucro futuro, execução em 100% dos casos ou prazo mínimo num mercado aleatório. As proteções limitam o preço aceito nas vendas automáticas; uma posição pode ficar imobilizada à espera de recuperação. Capacidade de estoque, caixa disponível, brokers e tempo de jogo aberto também limitam o ritmo; esta alteração não compra prédios, brokers nem executa ascensão.
