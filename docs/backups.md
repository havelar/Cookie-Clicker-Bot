# Backups integrados ao jogo

Abra **Gerenciar Backups** no cabeçalho. Não é necessário exportar texto, copiar ou colar.

- **Salvar jogo agora** captura o jogo diretamente. O nome é opcional: sem nome, usa Backup com data e hora na lista. Enter no campo de nome também salva.
- **Carregar no jogo** restaura o backup selecionado e grava o resultado no save nativo. Duplo clique na lista faz o mesmo. Antes, cria automaticamente um backup do estado atual.
- **Desfazer carga** carrega esse estado anterior, também com proteção de backup.
- A lista mostra os mais recentes primeiro, mantém a seleção ao atualizar e permite buscar nome ou data.
- **Adicionar arquivo…** incorpora um arquivo de save existente à lista, sem usar clipboard e sem carregá-lo automaticamente.

Ao carregar, Garden, Banco e clicker são pausados; o detector aguarda a operação atual antes da exportação de segurança. Simple Farm, Combo, Auto Ascensão e uma sessão ativa de Save Scum precisam estar desligados. Após uma carga bem-sucedida ou rollback confirmado, as automações anteriormente ativas são retomadas.

Se a importação falhar, o estado anterior é restaurado e verificado. Se essa recuperação também falhar, as automações permanecem pausadas e o backup anterior fica acessível em Desfazer carga e na lista. Uma carga bem-sucedida libera a pausa. Também é possível usar a lista para resolver uma restauração pendente de Save Scum.

Backups com o formato antigo continuam aparecendo. Novos arquivos incluem microssegundos e nunca sobrescrevem um arquivo existente. Nomes são normalizados para impedir caminhos inválidos. O limite de retenção continua sendo respeitado, mas os backups usados na carga e na recuperação ficam protegidos durante a operação. As datas de novos backups usam o horário de São Paulo.
