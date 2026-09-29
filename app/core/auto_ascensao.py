"""Máquina de estados segura para ciclos controlados de ascensão."""

from dataclasses import dataclass
import math
import threading
import time
from typing import Callable, Optional

from app.models.auto_ascensao import (
    Construcao,
    EstadoAutoAscensao,
    PlanoConstrucao,
    RelatorioAutoAscensao,
    ResultadoAcaoAscensao,
    SnapshotAscensao,
)
from app.utils.logger import logger


@dataclass(frozen=True)
class ConfiguracaoAutoAscensao:
    """Parâmetros validados de uma execução ou simulação."""

    ciclos_alvo: int
    ganho_minimo_prestigio: float
    intervalo_verificacao: float
    duracao_maxima_ciclo: float
    simulacao: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.ciclos_alvo, bool)
            or not isinstance(self.ciclos_alvo, int)
            or not 1 <= self.ciclos_alvo <= 10_000
        ):
            raise ValueError("A quantidade de ciclos deve ficar entre 1 e 10.000.")
        if (
            isinstance(self.ganho_minimo_prestigio, bool)
            or not isinstance(self.ganho_minimo_prestigio, (int, float))
            or not math.isfinite(self.ganho_minimo_prestigio)
            or self.ganho_minimo_prestigio < 0
        ):
            raise ValueError("O ganho mínimo de prestígio não pode ser negativo.")
        if (
            isinstance(self.intervalo_verificacao, bool)
            or not isinstance(self.intervalo_verificacao, (int, float))
            or not math.isfinite(self.intervalo_verificacao)
            or not 0.1 <= self.intervalo_verificacao <= 3600
        ):
            raise ValueError("O intervalo de verificação deve ficar entre 0,1 e 3.600 segundos.")
        if (
            isinstance(self.duracao_maxima_ciclo, bool)
            or not isinstance(self.duracao_maxima_ciclo, (int, float))
            or not math.isfinite(self.duracao_maxima_ciclo)
            or self.duracao_maxima_ciclo <= 0
        ):
            raise ValueError("O tempo máximo por ciclo deve ser positivo.")


def planejar_lote_construcoes(
    construcoes: tuple[Construcao, ...], lote: int = 100,
) -> tuple[PlanoConstrucao, ...]:
    """Planeja até ``lote`` unidades de todas as construções compráveis.

    O identificador crescente de ``Game.ObjectsById`` representa a progressão
    das construções no runtime 2.053. Todas as construções desbloqueadas entram
    no plano, ordenadas do maior identificador para o menor; assim as melhores
    recebem prioridade sem excluir as construções básicas.
    """
    if isinstance(lote, bool) or not isinstance(lote, int) or not 1 <= lote <= 1000:
        raise ValueError("O lote de construções deve ficar entre 1 e 1.000.")
    candidates = sorted((
        building for building in construcoes
        if building.desbloqueada and building.maximo_compravel > 0
    ), key=lambda building: building.id, reverse=True)
    return tuple(
        PlanoConstrucao(
            building.id,
            building.nome,
            min(lote, building.maximo_compravel),
            (
                "prioridade por nível decrescente; "
                f"até {min(lote, building.maximo_compravel)} unidade(s) neste lote"
            ),
        )
        for building in candidates
    )


class AutoAscensao:
    """Coordena leitura, decisão e uma ação verificada por iteração."""

    TERMINAL_STATES = {
        EstadoAutoAscensao.CONCLUIDO,
        EstadoAutoAscensao.INTERROMPIDO,
        EstadoAutoAscensao.ERRO_SEGURO,
    }

    def __init__(
        self,
        bridge,
        configuracao: ConfiguracaoAutoAscensao,
        habilitar_producao: Optional[Callable[[], bool]] = None,
        desabilitar_producao: Optional[Callable[[], bool]] = None,
        relogio: Callable[[], float] = time.monotonic,
    ):
        self.bridge = bridge
        self.configuracao = configuracao
        self.habilitar_producao = habilitar_producao or (lambda: True)
        self.desabilitar_producao = desabilitar_producao or (lambda: True)
        self.relogio = relogio
        self.estado = EstadoAutoAscensao.PREVIA
        self.ciclos_concluidos = 0
        self.ultima_acao = "Nenhuma ação executada."
        self.proximo_passo = "Gerar uma prévia do estado atual."
        self.motivo_parada = ""
        self.ultimo_snapshot: Optional[SnapshotAscensao] = None
        self._historico: list[str] = []
        self._stop_event = threading.Event()
        self._inicio_ciclo: Optional[float] = None
        self._ascensao_solicitada = False
        self._producao_preparada = False
        self._controle_producao_assumido = False

    @property
    def terminou(self) -> bool:
        return self.estado in self.TERMINAL_STATES

    def relatorio(self) -> RelatorioAutoAscensao:
        current = min(
            self.ciclos_concluidos + (1 if self._inicio_ciclo is not None else 0),
            self.configuracao.ciclos_alvo,
        )
        if self.estado == EstadoAutoAscensao.CONCLUIDO:
            current = self.configuracao.ciclos_alvo
        return RelatorioAutoAscensao(
            self.estado,
            current,
            self.configuracao.ciclos_alvo,
            self.ultima_acao,
            self.proximo_passo,
            self.motivo_parada,
            self.configuracao.simulacao,
            self.ultimo_snapshot,
            tuple(self._historico[-100:]),
        )

    def gerar_previa(self) -> RelatorioAutoAscensao:
        """Lê e planeja o próximo passo sem chamar nenhuma operação mutável."""
        snapshot = self.bridge.get_ascension_snapshot()
        self.ultimo_snapshot = snapshot
        self.estado = EstadoAutoAscensao.PREVIA
        self.ultima_acao = "Snapshot lido; nenhuma alteração foi feita."
        if not snapshot.disponivel:
            self.proximo_passo = snapshot.mensagem
            self.motivo_parada = "Prévia indisponível; bridge ou runtime inválido."
            return self.relatorio()
        self.proximo_passo = self._descrever_plano(snapshot)
        self.motivo_parada = ""
        self._registrar(f"Prévia: {self.proximo_passo}")
        return self.relatorio()

    def iniciar(self) -> RelatorioAutoAscensao:
        """Valida a condição inicial sem executar uma ação mutável."""
        if self.configuracao.simulacao:
            return self.gerar_previa()
        if self.estado == EstadoAutoAscensao.CONCLUIDO:
            return self.relatorio()
        if self.ciclos_concluidos >= self.configuracao.ciclos_alvo:
            return self._concluir()
        if self.estado != EstadoAutoAscensao.PREVIA:
            return self.relatorio()
        if self._stop_event.is_set():
            return self._interromper("Interrupção solicitada antes do início.")
        snapshot = self.bridge.get_ascension_snapshot()
        self.ultimo_snapshot = snapshot
        if not snapshot.disponivel:
            return self._falhar(snapshot.mensagem)
        if snapshot.tela != "ascensao":
            return self._falhar(
                "A execução real deve começar na tela de ascensão; nenhuma ação foi feita."
            )
        self._controle_producao_assumido = True
        if not self._parar_producao():
            return self._falhar("Não foi possível desabilitar o clicker na tela de ascensão.")
        self.estado = EstadoAutoAscensao.COMPRA_CELESTIAL
        self._inicio_ciclo = self.relogio()
        self.ultima_acao = "Condição inicial validada na tela de ascensão."
        self.proximo_passo = "Comprar Heavenly Upgrades simples, elegíveis e acessíveis."
        self._registrar(self.ultima_acao)
        return self.relatorio()

    def executar_passo(self) -> RelatorioAutoAscensao:
        """Executa no máximo uma operação mutável, sempre após novo snapshot."""
        if self.configuracao.simulacao:
            return self.gerar_previa()
        if self.terminou:
            return self.relatorio()
        if self.estado == EstadoAutoAscensao.PREVIA:
            return self.iniciar()
        if self._stop_event.is_set():
            return self._interromper("Interrupção manual solicitada.")
        if self._tempo_esgotado():
            return self._interromper(
                "Tempo máximo do ciclo excedido; ascensão forçada não foi executada."
            )

        snapshot = self.bridge.get_ascension_snapshot()
        self.ultimo_snapshot = snapshot
        if not snapshot.disponivel:
            return self._falhar(snapshot.mensagem)

        if self.estado == EstadoAutoAscensao.COMPRA_CELESTIAL:
            return self._passo_compra_celestial(snapshot)
        if self.estado == EstadoAutoAscensao.REENCARNACAO:
            return self._passo_reencarnacao(snapshot)
        if self.estado == EstadoAutoAscensao.PREPARACAO:
            return self._passo_preparacao(snapshot)
        if self.estado in {
            EstadoAutoAscensao.PRODUCAO_COMPRAS,
            EstadoAutoAscensao.AGUARDANDO_PRESTIGIO,
        }:
            return self._passo_producao(snapshot)
        if self.estado == EstadoAutoAscensao.ASCENSAO:
            return self._passo_ascensao(snapshot)
        return self._falhar(f"Estado interno inesperado: {self.estado.value}.")

    def executar(
        self, ao_atualizar: Optional[Callable[[RelatorioAutoAscensao], None]] = None,
    ) -> RelatorioAutoAscensao:
        """Faz polling conservador até conclusão, parada ou erro seguro."""
        report = self.iniciar()
        if ao_atualizar:
            ao_atualizar(report)
        if self.configuracao.simulacao or self.terminou:
            return report
        while not self.terminou:
            if self._stop_event.wait(self.configuracao.intervalo_verificacao):
                report = self._interromper("Interrupção manual solicitada.")
            else:
                report = self.executar_passo()
            if ao_atualizar:
                ao_atualizar(report)
        return report

    def parar(self) -> None:
        """Impede novas operações mutáveis e acorda o polling imediatamente."""
        self._stop_event.set()

    def _passo_compra_celestial(self, snapshot: SnapshotAscensao) -> RelatorioAutoAscensao:
        if snapshot.tela == "transicao":
            return self._aguardar("Aguardar o término da transição para a tela de ascensão.")
        if snapshot.tela != "ascensao":
            return self._falhar("Tela inesperada durante a compra de Heavenly Upgrades.")
        eligible = [upgrade for upgrade in snapshot.heavenly_upgrades if upgrade.elegivel]
        if not eligible:
            self.estado = EstadoAutoAscensao.REENCARNACAO
            self.ultima_acao = "Nenhum Heavenly Upgrade seguro e elegível ficou disponível."
            self.proximo_passo = "Reencarnar após nova validação da tela."
            return self.relatorio()
        chosen = min(eligible, key=lambda upgrade: (upgrade.preco, upgrade.id))
        return self._executar_acao(
            lambda: self.bridge.buy_heavenly_upgrade(chosen.id),
            f"Comprar Heavenly Upgrade “{chosen.nome}” ({chosen.id}).",
            "Continuar avaliando a árvore celestial após observar a compra.",
        )

    def _passo_reencarnacao(self, snapshot: SnapshotAscensao) -> RelatorioAutoAscensao:
        if snapshot.tela == "transicao":
            return self._aguardar("Aguardar a transição de reencarnação.")
        if snapshot.tela != "ascensao":
            return self._falhar("Tela inesperada antes da reencarnação.")
        report = self._executar_acao(
            self.bridge.reincarnate,
            "Reencarnar.",
            "Aguardar o jogo normal e preparar a produção.",
        )
        if not self.terminou:
            self.estado = EstadoAutoAscensao.PREPARACAO
            return self.relatorio()
        return report

    def _passo_preparacao(self, snapshot: SnapshotAscensao) -> RelatorioAutoAscensao:
        if snapshot.tela == "transicao":
            return self._aguardar("Aguardar a reencarnação terminar.")
        if snapshot.tela != "jogo":
            return self._falhar("Tela inesperada durante a preparação da produção.")
        if self._stop_event.is_set():
            return self._interromper("Interrupção manual solicitada antes de preparar a produção.")
        if not self._producao_preparada:
            try:
                enabled = self.habilitar_producao()
            except Exception as error:
                return self._falhar(f"Falha ao habilitar a produção: {error}")
            if enabled is not True:
                return self._falhar("Não foi possível habilitar o clicker para produzir cookies.")
            self._producao_preparada = True
        self.estado = EstadoAutoAscensao.PRODUCAO_COMPRAS
        self.ultima_acao = "Produção habilitada."
        self.proximo_passo = "Comprar upgrades seguros e a melhor construção disponível."
        self._registrar(self.ultima_acao)
        return self.relatorio()

    def _passo_producao(self, snapshot: SnapshotAscensao) -> RelatorioAutoAscensao:
        if snapshot.tela == "transicao":
            return self._aguardar("Aguardar a transição do jogo terminar.")
        if snapshot.tela != "jogo":
            return self._falhar("Tela inesperada durante a produção.")
        if snapshot.ganho_prestigio >= self.configuracao.ganho_minimo_prestigio:
            self.estado = EstadoAutoAscensao.ASCENSAO
            self.ultima_acao = (
                f"Meta atingida: ganho previsto de {snapshot.ganho_prestigio:,.0f} prestígio."
            )
            self.proximo_passo = "Revalidar atomicamente a meta e iniciar a ascensão."
            return self.relatorio()

        upgrades = [upgrade for upgrade in snapshot.upgrades_normais if upgrade.elegivel]
        if upgrades:
            self.estado = EstadoAutoAscensao.PRODUCAO_COMPRAS
            return self._executar_acao(
                self.bridge.buy_all_normal_upgrades,
                f"Usar “Comprar todos os upgrades” para {len(upgrades)} opção(ões) acessível(is).",
                "Atualizar o snapshot antes de decidir outra compra.",
            )

        building_plan = planejar_lote_construcoes(snapshot.construcoes)
        if building_plan:
            self.estado = EstadoAutoAscensao.PRODUCAO_COMPRAS
            return self._executar_acao(
                lambda: self.bridge.buy_buildings_batch(
                    [building.id for building in building_plan], 100
                ),
                (
                    "Comprar até 100 unidade(s) de cada uma das "
                    f"{len(building_plan)} construção(ões), das melhores para as básicas."
                ),
                "Atualizar o snapshot e repetir o lote enquanto houver compras possíveis.",
            )

        self.estado = EstadoAutoAscensao.AGUARDANDO_PRESTIGIO
        self.ultima_acao = "Nenhuma compra segura disponível neste snapshot."
        self.proximo_passo = (
            f"Aguardar ganho de prestígio: {snapshot.ganho_prestigio:,.0f} de "
            f"{self.configuracao.ganho_minimo_prestigio:,.0f}."
        )
        return self.relatorio()

    def _passo_ascensao(self, snapshot: SnapshotAscensao) -> RelatorioAutoAscensao:
        if self.ciclos_concluidos >= self.configuracao.ciclos_alvo:
            return self._concluir()
        if self._ascensao_solicitada:
            if snapshot.tela == "ascensao":
                self.ciclos_concluidos += 1
                self._ascensao_solicitada = False
                if self.ciclos_concluidos >= self.configuracao.ciclos_alvo:
                    return self._concluir()
                self.estado = EstadoAutoAscensao.COMPRA_CELESTIAL
                self._inicio_ciclo = self.relogio()
                self._producao_preparada = False
                self.ultima_acao = f"Ciclo {self.ciclos_concluidos} concluído na tela de ascensão."
                self.proximo_passo = "Iniciar o próximo ciclo pela árvore celestial."
                return self.relatorio()
            if snapshot.tela == "transicao":
                return self._aguardar("Aguardar a tela de ascensão confirmar o fim do ciclo.")
            return self._falhar("A ascensão foi solicitada, mas o jogo voltou a uma tela inesperada.")

        if snapshot.tela != "jogo":
            return self._falhar("Tela inesperada antes de iniciar a ascensão.")
        if snapshot.ganho_prestigio < self.configuracao.ganho_minimo_prestigio:
            self.estado = EstadoAutoAscensao.AGUARDANDO_PRESTIGIO
            self.ultima_acao = "A meta de prestígio deixou de estar satisfeita; ascensão cancelada."
            self.proximo_passo = "Retomar produção e compras sem ascender."
            return self.relatorio()
        if not self._parar_producao():
            return self._falhar("Não foi possível desabilitar o clicker antes da ascensão.")
        report = self._executar_acao(
            lambda: self.bridge.start_ascension(self.configuracao.ganho_minimo_prestigio),
            "Iniciar ascensão.",
            "Aguardar a tela de ascensão para confirmar o ciclo.",
        )
        if not self.terminou:
            self._ascensao_solicitada = True
        return report

    def _executar_acao(
        self,
        operation: Callable[[], ResultadoAcaoAscensao],
        description: str,
        next_step: str,
    ) -> RelatorioAutoAscensao:
        if self._stop_event.is_set():
            return self._interromper("Interrupção manual solicitada antes da ação mutável.")
        result = operation()
        if not isinstance(result, ResultadoAcaoAscensao):
            return self._falhar(f"Resposta inválida ao tentar: {description}")
        if not result.sucesso:
            return self._falhar(f"{description} {result.mensagem}")
        self.ultima_acao = f"{description} {result.mensagem}"
        self.proximo_passo = next_step
        self._registrar(self.ultima_acao)
        return self.relatorio()

    def _descrever_plano(self, snapshot: SnapshotAscensao) -> str:
        if snapshot.tela == "transicao":
            return "Aguardaria a transição atual terminar antes de qualquer ação."
        if snapshot.tela == "ascensao":
            upgrades = [item for item in snapshot.heavenly_upgrades if item.elegivel]
            if upgrades:
                chosen = min(upgrades, key=lambda item: (item.preco, item.id))
                return f"Compraria primeiro o Heavenly Upgrade “{chosen.nome}” e reavaliaria a árvore."
            return "Reencarnaria; não há Heavenly Upgrade simples, elegível e acessível."
        if snapshot.ganho_prestigio >= self.configuracao.ganho_minimo_prestigio:
            return "A meta está atingida; revalidaria o ganho e iniciaria a ascensão."
        upgrades = [item for item in snapshot.upgrades_normais if item.elegivel]
        if upgrades:
            return (
                "Usaria o botão nativo “Comprar todos os upgrades” para tentar "
                f"{len(upgrades)} opção(ões) acessível(is) em uma única ação."
            )
        building_plan = planejar_lote_construcoes(snapshot.construcoes)
        if building_plan:
            return (
                f"Compraria até 100 unidade(s) de {len(building_plan)} construção(ões), "
                f"começando por “{building_plan[0].nome}” e seguindo até as básicas."
            )
        return "Aguardaria produção até surgir uma compra segura ou a meta de prestígio ser atingida."

    def _tempo_esgotado(self) -> bool:
        return (
            self._inicio_ciclo is not None
            and self.relogio() - self._inicio_ciclo > self.configuracao.duracao_maxima_ciclo
        )

    def _aguardar(self, next_step: str) -> RelatorioAutoAscensao:
        self.ultima_acao = "Nenhuma ação mutável durante este polling."
        self.proximo_passo = next_step
        return self.relatorio()

    def _registrar(self, message: str) -> None:
        self._historico.append(message)
        logger.info(f"Auto Ascensão: {message}")

    def _parar_producao(self) -> bool:
        if not self._controle_producao_assumido:
            return True
        try:
            stopped = self.desabilitar_producao()
        except Exception as error:
            logger.error(f"Auto Ascensão: falha ao desabilitar o clicker: {error}")
            return False
        if stopped is True:
            self._producao_preparada = False
            return True
        return False

    def _falhar(self, reason: str) -> RelatorioAutoAscensao:
        self._parar_producao()
        self.estado = EstadoAutoAscensao.ERRO_SEGURO
        self.motivo_parada = reason
        self.proximo_passo = "Automação parada; revise o diagnóstico antes de tentar novamente."
        logger.error(f"Auto Ascensão interrompida com segurança: {reason}")
        return self.relatorio()

    def _interromper(self, reason: str) -> RelatorioAutoAscensao:
        self._parar_producao()
        self.estado = EstadoAutoAscensao.INTERROMPIDO
        self.motivo_parada = reason
        self.proximo_passo = "Nenhuma nova ação mutável será iniciada."
        logger.warning(f"Auto Ascensão interrompida: {reason}")
        return self.relatorio()

    def _concluir(self) -> RelatorioAutoAscensao:
        self._parar_producao()
        self.estado = EstadoAutoAscensao.CONCLUIDO
        self.ultima_acao = f"{self.ciclos_concluidos} ciclo(s) concluído(s)."
        self.proximo_passo = "Automação finalizada na tela de ascensão."
        self.motivo_parada = "Limite configurado de ciclos atingido."
        self._registrar(self.ultima_acao)
        return self.relatorio()
