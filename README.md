# Cookie Clicker Bot

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/PyQt5-5.15+-green.svg)](https://pypi.org/project/PyQt5/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Um bot automatizado para Cookie Clicker com interface gráfica moderna, desenvolvido em Python.

## ✨ Características

- **Automação Inteligente**: Clicador automático do cookie principal com controle preciso
- **Detecção de Cookies Especiais**: Identifica e coleta automaticamente Golden Cookies e Fortune Cookies
- **Interface Gráfica Moderna**: UI desenvolvida com PyQt5 para controle fácil e visual
- **Logging Centralizado**: Sistema de logs completo com saída para console, arquivo e interface
- **Configuração Flexível**: Sistema de configurações centralizado e customizável
- **Arquitetura Modular**: Código organizado em módulos desacoplados e reutilizáveis
- **Type Hints Completos**: Código Python moderno com anotações de tipo
- **Threading Seguro**: Automação executada em threads separadas para performance

## 🚀 Instalação

### Pré-requisitos

- Python 3.12 ou superior
- Windows 10/11 (suporte nativo para APIs Win32)
- Cookie Clicker rodando no navegador Chrome

### Instalação das Dependências

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/cookie-clicker-bot.git
cd cookie-clicker-bot

# Instale as dependências
pip install -r requirements.txt
```

## 🎮 Como Usar

1. **Inicie o Cookie Clicker** no navegador Chrome
2. **Execute o bot**:
   ```bash
   python main.py
   ```
3. **Configure as automações** na interface gráfica:
   - Ative o clicker do cookie principal
   - Habilite detecção de Golden Cookies
   - Habilite detecção de Fortune Cookies
4. **Controle via teclado**: Use SCROLL LOCK para ligar/desligar o clicker

## 🏗️ Arquitetura

```
app/
├── bridge/          # Comunicação com JavaScript do jogo
├── core/           # Lógica principal de automação
├── ui/             # Interface gráfica PyQt5
├── utils/          # Utilitários (logging, etc.)
├── config/         # Configurações centralizadas
└── models/         # Modelos de dados (futuro)
```

### Módulos Principais

- **`js_bridge.py`**: Bridge para comunicação com o runtime JavaScript do Cookie Clicker via Chrome DevTools Protocol
- **`run.py`**: Gerenciador principal das automações com threading
- **`input.py`**: Abstração de entrada (mouse/teclado) usando Win32 APIs
- **`main_window.py`**: Interface gráfica principal com PyQt5
- **`settings.py`**: Configurações centralizadas usando dataclasses

## ⚙️ Configuração

As configurações são centralizadas no arquivo `app/config/settings.py`:

```python
@dataclass
class AppConfig:
    # Intervalos de automação
    click_interval: float = 0.005  # 5ms entre cliques
    detect_interval: float = 0.2   # 200ms para detecção

    # Controles
    toggle_key: str = "SCROLLLOCK"

@dataclass
class AutomationConfig:
    # Automação do cookie principal
    enable_cookie_clicker: bool = True

    # Detecção de cookies especiais
    enable_golden_cookie: bool = True
    enable_fortune_cookie: bool = True
    enable_reindeer: bool = False  # Ainda não implementado
```

## 🔧 Desenvolvimento

### Estrutura de Pastas

O projeto segue uma arquitetura modular profissional:

- **`app/`**: Código fonte principal
  - **`bridge/`**: Comunicação com o jogo
  - **`core/`**: Lógica de negócio
  - **`ui/`**: Interface gráfica
  - **`utils/`**: Utilitários compartilhados
  - **`config/`**: Configurações
  - **`models/`**: Modelos de dados

### Padrões de Código

- **Type Hints**: Todos os métodos e funções têm anotações de tipo
- **Docstrings**: Documentação completa seguindo Google Style
- **Imports Absolutos**: Uso consistente de imports absolutos
- **Logging**: Sistema centralizado de logging
- **Threading**: Automação em threads separadas com controle de parada

### Executando Testes

```bash
# Testes unitários (futuro)
python -m pytest

# Testes de integração
python -c "from app.core.run import AutomationRunner; print('Import OK')"
```

## 📊 Logs

O sistema de logging registra todas as operações:

- **Console**: Logs em tempo real no terminal
- **Arquivo**: Logs persistentes em `logs/bot.log`
- **Interface**: Logs visíveis na UI em tempo real

Níveis de log:
- `INFO`: Operações normais
- `WARNING`: Avisos não críticos
- `ERROR`: Erros que não param a execução

## 🛡️ Segurança

- **Isolamento**: O bot não modifica arquivos do jogo
- **Permissões**: Apenas acesso de leitura ao processo do navegador
- **Threading Seguro**: Threads separadas com sincronização adequada
- **Tratamento de Erros**: Recuperação graceful de falhas

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📝 Licença

Este projeto está licenciado sob a MIT License - veja o arquivo [LICENSE](LICENSE) para detalhes.

## ⚠️ Aviso Legal

Este software é fornecido apenas para fins educacionais e de entretenimento. O uso de bots em jogos pode violar os termos de serviço. Use por sua própria conta e risco.

## 🙏 Agradecimentos

- Comunidade Cookie Clicker por criar um jogo tão viciante
- Desenvolvedores das bibliotecas pychrome, PyQt5 e pywin32
- Comunidade Python por ferramentas incríveis

---

**Desenvolvido com ❤️ para a comunidade Cookie Clicker**
- ✅ Clique em fortune: `Game.tickerL.click()`
- ✅ Toggle para clique no cookie principal (posição obtida do Game)
- ✅ **Threads separadas** para detecção e clique (performance otimizada)
- ✅ **Cache de posição** do cookie (calculada uma vez no início)
- ✅ Conexão automática no início
- ✅ Fallback seguro (não crasha se bridge falhar)
- ✅ Logs detalhados para debugging

## Expansão Futura

- Auto-buy upgrades
- Buff combos
- Ascension automation
- Estatísticas
- Scheduler

## Logs

Logs detalhados em console para debugging e monitoramento.