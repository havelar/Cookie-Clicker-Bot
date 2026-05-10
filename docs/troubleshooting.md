# Troubleshooting - Cookie Clicker Bot

## Problemas Comuns e Soluções

### 1. "Nenhuma janela do Cookie Clicker encontrada"

**Sintomas:**
- Erro: "Nenhuma janela do Cookie Clicker encontrada!"
- Aplicação não consegue localizar o processo do jogo

**Causas Possíveis:**
- Cookie Clicker não está executando
- Jogo rodando em modo incompatível
- Problemas de permissões

**Soluções:**
1. Certifique-se que o Cookie Clicker está aberto
2. Verifique se está rodando no Chrome (não Steam CEF)
3. Execute o bot como administrador
4. Reinicie o jogo e tente novamente

### 2. "Falha ao conectar ao bridge JavaScript"

**Sintomas:**
- Erro: "Falha ao conectar ao bridge JS. Saindo."
- Status do bridge mostra "Desconectado"

**Causas Possíveis:**
- Remote debugging não habilitado
- Porta 9222 ocupada
- Firewall bloqueando conexão

**Soluções:**
1. **Para Chrome:**
   - Execute Chrome com: `chrome.exe --remote-debugging-port=9222`
   - Ou use launch options no Steam: `--remote-debugging-port=9222`

2. **Verificar porta:**
   ```bash
   netstat -ano | findstr :9222
   ```

3. **Firewall:**
   - Permita conexões na porta 9222
   - Desative temporariamente para teste

### 3. Bot não clica no cookie

**Sintomas:**
- Clicker ativo mas sem cliques
- Logs mostram "Macro INICIADO" mas sem ação

**Causas Possíveis:**
- Posição do cookie não encontrada
- Janela do jogo minimizada
- Problemas de foco da janela

**Soluções:**
1. Certifique-se que a janela do jogo está visível
2. Não minimize a janela durante uso
3. Verifique logs para mensagens de erro de posição
4. Reinicie o bot com o jogo em foco

### 4. Golden Cookies não são detectados

**Sintomas:**
- Logs não mostram detecção de golden cookies
- Cookies aparecem mas não são coletados

**Causas Possíveis:**
- Problemas na comunicação JS
- Timing incorreto
- Estado do jogo incompatível

**Soluções:**
1. Verifique se o bridge está conectado
2. Aguarde alguns segundos após iniciar o jogo
3. Verifique logs detalhados
4. Teste com fortune cookies (mais simples)

### 5. Interface gráfica não responde

**Sintomas:**
- UI congela ou não responde a cliques
- Aplicação parece travada

**Causas Possíveis:**
- Thread principal bloqueada
- Problemas com PyQt5
- Erro não tratado em thread

**Soluções:**
1. Verifique logs no console para erros
2. Reinicie a aplicação
3. Execute sem UI para testar: `python app/core/run.py`
4. Verifique instalação do PyQt5

### 6. Erro de importação de módulos

**Sintomas:**
- `ModuleNotFoundError` ao executar
- Dependências não encontradas

**Causas Possíveis:**
- Dependências não instaladas
- Ambiente virtual incorreto
- Versão Python incompatível

**Soluções:**
1. Instale dependências:
   ```bash
   pip install -r requirements.txt
   ```

2. Verifique versão Python:
   ```bash
   python --version  # Deve ser 3.12+
   ```

3. Ative ambiente virtual se usado

### 7. Logs não aparecem na interface

**Sintomas:**
- Logs no console mas não na UI
- Área de logs vazia

**Causas Possíveis:**
- Handler da UI não conectado
- Sinais Qt não funcionando

**Soluções:**
1. Verifique inicialização da UI
2. Confirme que `logger.add_ui_handler()` foi chamado
3. Teste logs manuais na UI

### 8. Performance degradada

**Sintomas:**
- Cliques lentos ou irregulares
- Alto uso de CPU

**Causas Possíveis:**
- Intervalos muito curtos
- Muitas threads competindo
- Problemas de sistema

**Soluções:**
1. Ajuste intervalos em `settings.py`:
   ```python
   click_interval: float = 0.010  # Aumente para 10ms
   detect_interval: float = 0.5   # Aumente para 500ms
   ```

2. Feche outras aplicações
3. Monitore uso de recursos

## Diagnóstico Avançado

### Verificar Conexão CDP

```python
# Execute no Python para testar conexão
from app.bridge.js_bridge import CookieClickerBridge
bridge = CookieClickerBridge()
print("Conectando...")
if bridge.connect():
    print("✅ Conexão OK")
    result = bridge.execute_js("return Game.version")
    print(f"Versão do jogo: {result}")
else:
    print("❌ Falha na conexão")
```

### Testar APIs Win32

```python
# Teste de input handling
from app.automation.input import InputHandler
handler = InputHandler(pid=12345, restore_game=False)
print("Handler criado com sucesso")
```

### Verificar Threads

```python
# Monitore threads ativas
import threading
import time

def monitor_threads():
    while True:
        print(f"Threads ativas: {threading.active_count()}")
        for t in threading.enumerate():
            print(f"  - {t.name}: {t.is_alive()}")
        time.sleep(5)

monitor_threads()
```

## Logs de Debug

Para debug avançado, habilite logs detalhados:

```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

Ou modifique `app/utils/logger.py`:

```python
ui_handler.setLevel(logging.DEBUG)
file_handler.setLevel(logging.DEBUG)
```

## Suporte

Se os problemas persistirem:

1. Colete informações do sistema:
   - Versão Python
   - Sistema operacional
   - Logs completos
   - Configuração do jogo

2. Abra uma issue no repositório com:
   - Descrição detalhada do problema
   - Logs relevantes
   - Passos para reproduzir
   - Ambiente (OS, Python version, etc.)

3. Para questões urgentes, verifique:
   - [Documentação oficial do Chrome DevTools](https://chromedevtools.github.io/devtools-protocol/)
   - [Documentação PyQt5](https://pypi.org/project/PyQt5/)
   - [Documentação pywin32](https://pypi.org/project/pywin32/)