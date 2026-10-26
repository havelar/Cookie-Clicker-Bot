# Save Scum de Sugar Lumps

A aba Save Scum exporta o save, colhe o lump e restaura um checkpoint com as funções nativas. Não modifica a seed, o tipo ou o horário de início. O novo instante de colheita varia o sorteio do próximo lump.

## Como testar

1. Desligue **Coletar Sugar Lumps ao maturar** na aba Automações antes de importar o save de teste. A coleta comum pode consumir um lump maduro antes de você ligar Save Scum.
2. Desligue Simple Farm, Combo e Auto Ascensão. Garden, Banco e clicker são pausados durante as tentativas e retomados ao terminar.
3. Importe um save com lump maduro. Prefira a fase garantida e deixe margem antes da colheita automática. Um timestamp antigo pode disparar a colheita automática na importação; nesse caso, a rotina aguarda a maturação do próximo lump.
4. Na nova aba, marque Dourado e/ou Caramelizado, configure limite e intervalo e use **Consultar estado**. Consultar não colhe nem restaura.
5. Use **Ligar**. O backup inicial é gravado em disco antes da primeira colheita. Resultados rejeitados voltam ao mesmo checkpoint.
6. Ao encontrar o alvo, o bot cria outro backup, grava o resultado no save nativo e desliga. O lump novo ainda precisa crescer. A preservação do tipo escolhido é ligada nas Configurações para aguardar sua colheita garantida.

O save anexado não é importado automaticamente. A sessão usa o estado atualmente aberto no jogo.

## Encerramento e recuperação

- Desligar ou atingir o limite restaura o início antes de liberar as outras automações.
- Uma falha de comunicação pode acontecer depois de uma colheita efetiva; o bot restaura mesmo quando a resposta da ação não chegou.
- Se a restauração falhar, as outras automações continuam pausadas. Use **Restaurar início** para tentar recuperar. O acompanhamento mostra o caminho do backup em disco.
- A sessão exige 30 segundos de margem antes da colheita automática. Checkpoints expirados são rejeitados antes de importar, evitando uma colheita automática durante o rollback.
- Alvos, limite e intervalo persistem; Save Scum sempre inicia desligado.
- Não faça ações manuais durante as tentativas: a restauração desfaz o progresso posterior ao checkpoint.

## Coleta comum corrigida

Game.lumps é o saldo numérico. O lump em crescimento usa Game.lumpT, Game.lumpCurrentType e os tempos de maturidade. Antes, o bot procurava uma lista no saldo e não encontrava nenhum lump.

A coleta comum usa Game.clickLump() e confirma a mudança do início do próximo lump. Tipos não preservados são colhidos ao maturar, com 50% de chance de saldo zero; mesmo a colheita de saldo zero gera o próximo lump. Tipos preservados aguardam Game.lumpRipeAge. Preservar significa aguardar a fase garantida, não deixar de colher. A proteção é verificada novamente na própria ação.

A exclusividade espera todo o ciclo do detector e as operações de Garden/Banco antes de exportar o checkpoint.
