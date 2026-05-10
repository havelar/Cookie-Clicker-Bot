# Arquitetura do Cookie Clicker Bot

## Visão Geral

O Cookie Clicker Bot é uma aplicação Python moderna que automatiza tarefas no jogo Cookie Clicker através de uma arquitetura modular e desacoplada. O sistema utiliza comunicação direta com o runtime JavaScript do jogo via Chrome DevTools Protocol, garantindo precisão e eficiência.

## Princípios Arquiteturais

### 1. Separação de Responsabilidades
Cada módulo tem uma responsabilidade clara e bem definida:
- **Bridge**: Comunicação com o jogo
- **Core**: Lógica de automação
- **UI**: Interface gráfica
- **Utils**: Utilitários compartilhados
- **Config**: Configurações centralizadas

### 2. Injeção de Dependências
As dependências são injetadas explicitamente, facilitando testes e manutenção:
```python
# Exemplo: AutomationRunner recebe suas dependências
runner = AutomationRunner(pid=pid, bridge=bridge)
```

### 3. Configuração Centralizada
Todas as configurações são centralizadas em dataclasses imutáveis:
```python
@dataclass(frozen=True)
class AppConfig:
    click_interval: float = 0.005
    detect_interval: float = 0.2
```

### 4. Logging Centralizado
Sistema de logging com múltiplos handlers (console, arquivo, UI):
```python
logger.info("Operação executada com sucesso")
```

## Diagrama de Componentes

```
┌─────────────────┐    ┌─────────────────┐
│   MainWindow    │    │  Automation-   │
│   (PyQt5 UI)    │◄──►│    Runner      │
│                 │    │                 │
└─────────────────┘    └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│   LogSignal-    │    │  InputHandler   │
│   Emitter       │    │  (Win32 API)    │
└─────────────────┘    └─────────────────┘
         ▲                       ▲
         │                       │
┌─────────────────┐    ┌─────────────────┐
│   BotLogger     │    │ CookieClicker- │
│  (Centralized)  │    │     Bridge     │
└─────────────────┘    └─────────────────┘
                         │
                         ▼
               ┌─────────────────┐
               │ Chrome DevTools │
               │    Protocol     │
               └─────────────────┘
```

## Fluxo de Dados

### Inicialização
1. `main.py` → `Application.initialize()`
2. Encontra janela do jogo → `find_cookie_window()`
3. Conecta bridge JS → `CookieClickerBridge.connect()`
4. Cria UI → `MainWindow()`
5. Conecta logging → `BotLogger.add_ui_handler()`
6. Cria runner → `AutomationRunner(pid, bridge)`

### Execução
1. UI mostra controles
2. Usuário clica "INICIAR CLICKER"
3. `AutomationRunner.start()` inicia threads
4. Thread detector busca cookies especiais
5. Thread clicker clica no cookie principal
6. Logs são enviados para console, arquivo e UI

## Threads e Concorrência

### Thread Principal (Qt Event Loop)
- Gerencia a interface gráfica
- Processa sinais e eventos da UI
- Recebe logs via sinais Qt

### Thread Detector
- Executa em loop contínuo
- Verifica presença de Golden Cookies e Fortunes
- Intervalo configurável (padrão: 200ms)
- Thread-safe com controle de parada

### Thread Clicker
- Executa em loop contínuo quando ativo
- Clica no cookie principal
- Intervalo configurável (padrão: 5ms)
- Controlado por toggle (SCROLL LOCK)

## Tratamento de Erros

### Estratégias
- **Recuperação Graceful**: Erros não críticos não param a execução
- **Logging Detalhado**: Todos os erros são logados com contexto
- **Fallbacks**: Métodos alternativos quando operações falham
- **Shutdown Seguro**: Cleanup adequado ao encerrar

### Exemplo de Tratamento
```python
try:
    result = self.bridge.get_cookie_position()
    if not result:
        logger.error("Fallback: usando posição cacheada")
        result = self.cached_position
except Exception as e:
    logger.error(f"Erro crítico: {e}")
    self.stop()
```

## Extensibilidade

### Adição de Novas Automações
1. Adicionar configuração em `AutomationConfig`
2. Implementar lógica no `AutomationRunner`
3. Adicionar controle na UI
4. Atualizar documentação

### Novos Tipos de Detecção
1. Criar método no `CookieClickerBridge`
2. Integrar na thread detector
3. Adicionar configuração
4. Testar isolamento

## Segurança e Performance

### Segurança
- **Isolamento**: Não modifica arquivos do jogo
- **Permissões Mínimas**: Apenas leitura do processo
- **Threading Seguro**: Sem condições de corrida
- **Validação**: Entradas validadas antes do processamento

### Performance
- **Threading Otimizado**: CPU não bloqueada
- **Cache Inteligente**: Posições cacheadas quando possível
- **Intervalos Configuráveis**: Ajustáveis por necessidade
- **Lazy Loading**: Componentes inicializados sob demanda

## Testabilidade

### Módulos Isolados
Cada módulo pode ser testado independentemente:
- `CookieClickerBridge` mocka conexão CDP
- `InputHandler` testa APIs Win32
- `AutomationRunner` testa lógica sem UI

### Integração
Testes end-to-end validam fluxo completo:
- Inicialização completa
- Automação funcionando
- UI responsiva
- Logging correto

## Manutenibilidade

### Padrões de Código
- **Type Hints**: Anotações completas em todos os métodos
- **Docstrings**: Documentação Google Style
- **Imports Absolutos**: Consistência em todo o projeto
- **Nomes Descritivos**: Variáveis e métodos autoexplicativos

### Refatoração Segura
- **Lógica Preservada**: Mudanças não alteram comportamento
- **Testes Frequentes**: Validação incremental
- **Versionamento**: Commits granulares
- **Documentação**: Atualizada com mudanças