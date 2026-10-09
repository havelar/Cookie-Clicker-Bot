# JavaScript do Cookie Clicker — referência local

Cópia integral dos 69 arquivos JavaScript presentes na instalação Steam, versão 2.053 (build 17243728), obtida em 07/10/2026. Os arquivos foram copiados sem alterações, mantendo a estrutura original de `resources/app`.

## Onde consultar

- `src/main.js`: lógica principal, upgrades, buildings, buffs, Golden Cookies, Sugar Lumps e Krumblor.
- `src/minigameGarden.js`: plantas, crescimento, mutações, solos e recarga com Sugar Lump.
- `src/minigameMarket.js`: Stock Market.
- `src/minigameGrimoire.js`: magias e mana.
- `src/minigamePantheon.js`: deuses e slots do Pantheon.
- `src/loc/`: traduções, incluindo `PT-BR.js`.
- `start.js`, `preload.js`, `steam/` e `greenworks/`: integração da aplicação Steam.
- `node_modules/`: JavaScript das dependências distribuídas com o jogo.
- `mods/local/`: mods de exemplo distribuídos com o jogo.

`src/index.html` registra a versão e o carregamento dos scripts. Os manifests de pacotes e arquivos de licença encontrados também foram preservados. `manifest.json` registra origem, versão, tamanho e SHA-256 de cada arquivo, para verificar a integridade da cópia.

Esta pasta serve para consulta e não é carregada pelo bot. Não inclui saves, imagens, sons, binários ou uma instalação executável do jogo. Quando o jogo atualizar, a referência precisará ser atualizada a partir da instalação Steam.

O código mantém os direitos e avisos dos autores originais; a licença do bot não se aplica automaticamente a estes arquivos.
