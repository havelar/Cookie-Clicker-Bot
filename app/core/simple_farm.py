"""Looper econômico de Golden Cookies com FtHoF único sem Sugar Lumps."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from app.models.simple_farm import (
    ConfiguracaoSimpleFarm,
    EstadoSimpleFarm,
    PlanoSimpleFarm,
    RelatorioSimpleFarm,
)
from app.utils.logger import logger


class SimpleFarmAutomation:
    """Coleta naturais e usa um FtHoF único oportunista sem tocar nos minigames."""

    SKIP_SPELL_ID = 4  # Haggler's Charm: menor custo no save suportado.
    COOKIE_STORM_DROP = "cookie storm drop"
    REINVEST_INTERVAL_SECONDS = 15.0
    DIRECT_CLICK_BUFFS = {
        "click frenzy", "dragonflight", "blood frenzy", "devastation", "cursed finger",
    }
    PRODUCTION_CLICK_BUFFS = {"frenzy", "dragon harvest", "building buff"}

    def __init__(
        self,
        bridge,
        configuracao: ConfiguracaoSimpleFarm,
        *,
        habilitar_clicker: Optional[Callable[[], bool]] = None,
        desabilitar_clicker: Optional[Callable[[], bool]] = None,
        dormir: Callable[[float], None] = time.sleep,
        relogio: Callable[[], float] = time.monotonic,
    ):
        self.bridge = bridge
        self.configuracao = configuracao
        self.habilitar_clicker = habilitar_clicker or (lambda: True)
        self.desabilitar_clicker = desabilitar_clicker or (lambda: True)
        self.dormir = dormir
        self.relogio = relogio
        self._stop = threading.Event()
        self._golden_cookies = 0
        self._magias = 0
        self._upgrades = 0
        self._buildings = 0
        self._cash_floor = 0.0
        self._last_reinvest_at = float("-inf")
        self._clicker_ativo = False
        self._investment_status = ""
        self._live_reserve = 0.0

    def parar(self) -> None:
        self._stop.set()

    def gerar_previa(self) -> RelatorioSimpleFarm:
        snapshot = self.bridge.get_combo_snapshot(require_minigames=False)
        if not snapshot.get("available"):
            return self._error(snapshot.get("message", "Runtime indisponível"), stop_clicker=False)
        self._cash_floor = max(
            self._cash_floor,
            float(snapshot.get("cookies", 0)) * self.configuracao.reserva_caixa,
        )
        plano = self._planejar(snapshot)
        return self._report(
            EstadoSimpleFarm.PREVIA,
            "Previsão somente leitura; nenhum recurso foi usado.",
            "Garden e Banco continuam ativos; cliques extras somente nas janelas fortes.",
            snapshot,
            plano,
        )

    def executar(self, atualizar: Optional[Callable[[RelatorioSimpleFarm], None]] = None):
        atualizar = atualizar or (lambda _report: None)
        try:
            while not self._stop.is_set():
                report = self.executar_passo()
                atualizar(report)
                if report.terminal:
                    return report
                self.dormir(self.configuracao.intervalo_verificacao)
            return self._interrompido("Simple Farm interrompido pelo usuário.")
        except Exception as error:
            logger.exception("Falha inesperada no Simple Farm")
            return self._error(f"Falha inesperada: {error}")
        finally:
            self._set_clicker(False)

    def executar_passo(self) -> RelatorioSimpleFarm:
        if self._stop.is_set():
            return self._interrompido("Simple Farm interrompido pelo usuário.")

        snapshot = self.bridge.get_combo_snapshot(require_minigames=False)
        if not snapshot.get("available"):
            return self._error(snapshot.get("message", "Runtime indisponível"))
        if snapshot.get("screen") != "game":
            return self._error("O Cookie Clicker não está na tela normal do jogo.")
        self._cash_floor = max(
            self._cash_floor,
            float(snapshot.get("cookies", 0)) * self.configuracao.reserva_caixa,
        )
        if not self._sincronizar_clicker(snapshot):
            return self._error("Não foi possível ativar o autoclicker na janela útil.")

        plano = self._planejar(snapshot)

        forced = [item for item in snapshot.get("shimmers", ()) if item.get("force")]
        unexpected = [item for item in forced if item.get("force") != self.COOKIE_STORM_DROP]
        if unexpected:
            return self._error(
                "Há um Golden Cookie de spell inesperado em tela; o modo parou para não clicar no resultado errado."
            )
        if forced:
            result = self.bridge.pop_combo_cookie_storm_drops()
            count = int(result.get("count", 0))
            self._golden_cookies += count
            return self._report(
                EstadoSimpleFarm.COLETANDO,
                f"Cookie Storm em andamento: {count} drop(s) coletado(s).",
                "A tempestade continua sendo drenada sem interromper o Simple Farm.",
                snapshot,
                plano,
            )

        natural = next((item for item in snapshot.get("shimmers", ()) if not item.get("force")), None)
        if natural is not None:
            result = self.bridge.pop_combo_natural_shimmer(int(natural["id"]))
            if result.get("ok"):
                self._golden_cookies += 1
                return self._report(
                    EstadoSimpleFarm.COLETANDO,
                    "Golden Cookie natural coletado.",
                    "Reavaliando o buff obtido e o FtHoF único no próximo ciclo.",
                    snapshot,
                    plano,
                )
            if result.get("gone"):
                return self._report(
                    EstadoSimpleFarm.COLETANDO,
                    "O Golden Cookie expirou durante a leitura.",
                    "Continuando a busca sem alterar outros sistemas.",
                    snapshot,
                    plano,
                )
            return self._error(result.get("message", "Falha ao coletar Golden Cookie natural"))

        # Compras independem da existência de um combo ou de mana disponível.
        investment = self._talvez_reinvestir(snapshot, plano)
        if investment is not None:
            return investment
        if plano is None:
            return self._report(
                EstadoSimpleFarm.COLETANDO,
                "Farm ativo; nenhuma magia útil disponível no alcance.",
                "Coletando naturais e acumulando caixa para compras econômicas.", snapshot, None,
            )
        if self._buff(snapshot, "dragonflight") is not None:
            return self._report(
                EstadoSimpleFarm.AGUARDANDO_BUFF, "Aproveitando Dragonflight sem usar magia.",
                "Aguardando o buff terminar para reavaliar a previsão.", snapshot, plano,
            )

        cast_atual = int(snapshot.get("spellsCastTotal", 0))
        if cast_atual < plano.cast_inicial:
            return self._alinhar(snapshot, plano)
        if cast_atual > plano.cast_inicial:
            return self._report(
                EstadoSimpleFarm.ALINHANDO,
                "O contador de spells mudou; o plano foi descartado.",
                "Recalculando a seed no próximo ciclo.",
                snapshot,
                plano,
            )

        magic = float(snapshot.get("magic", 0))
        maximum = float(snapshot.get("magicM", 0))
        cost = float(snapshot.get("fthofCost") or 0)
        if maximum <= 0 or magic + 1e-7 < maximum or magic < cost:
            return self._report(
                EstadoSimpleFarm.AGUARDANDO_BUFF,
                "Click Frenzy alinhado; aguardando mana cheia e suficiente para a magia.",
                "Golden Cookies e autoclick continuam ativos durante a regeneração.",
                snapshot,
                plano,
            )

        trigger = self._melhor_buff_natural(snapshot)
        if trigger is None:
            return self._report(
                EstadoSimpleFarm.AGUARDANDO_BUFF,
                "Mana e Click Frenzy prontos; aguardando um multiplicador natural.",
                "O próximo multiplicador natural dispara a tentativa automaticamente.",
                snapshot,
                plano,
            )

        # O clique precisa começar antes da avaliação atômica que cria e abre
        # o Click Frenzy; assim nenhum frame útil do FtHoF único é perdido.
        if not self._set_clicker(True):
            return self._error("O FtHoF único estava pronto, mas o autoclicker não pôde ser ativado.")
        result = self.bridge.execute_simple_farm_spell(
            expected_cast=plano.cast_inicial,
            minimum_buff_seconds=self.configuracao.duracao_minima_buff,
        )
        if not result.get("ok"):
            if result.get("waiting"):
                self._sincronizar_clicker(snapshot)
                return self._report(
                    EstadoSimpleFarm.AGUARDANDO_BUFF,
                    result.get("message", "Aguardando recursos para o FtHoF único."),
                    "Nada foi vendido; o modo tentará novamente.",
                    snapshot,
                    plano,
                )
            return self._error(result.get("message", "FtHoF único não confirmado"))
        self._magias += 1
        return self._report(
            EstadoSimpleFarm.EXECUTANDO,
            f"FtHoF único concluído sobre {trigger}; sem venda de torres; clicker ativo.",
            "Regenerando mana para a próxima oportunidade, sem usar Sugar Lumps.",
            snapshot,
            plano,
        )

    def _talvez_reinvestir(
        self, snapshot: dict, plano: Optional[PlanoSimpleFarm],
    ) -> Optional[RelatorioSimpleFarm]:
        """Investe uma parcela do excedente, no máximo uma vez por cooldown."""
        now = self.relogio()
        if now - self._last_reinvest_at < self.REINVEST_INTERVAL_SECONDS:
            return None
        # Buffs multiplicativos são curtos; durante eles o clicker e o FtHoF único
        # têm precedência total sobre compras de loja.
        if self._janela_ativa(snapshot):
            return None
        self._last_reinvest_at = now
        result = self.bridge.reinvest_simple_farm(
            cash_floor=self._cash_floor,
            max_spend_fraction=self.configuracao.investimento_por_ciclo,
            reserve_fraction=self.configuracao.reserva_caixa,
        )
        self._cash_floor = max(
            self._cash_floor,
            float(result.get("before", 0)) * self.configuracao.reserva_caixa,
        )
        self._live_reserve = float(result.get("reserve", self._cash_floor))
        self._investment_status = result.get("message", "")
        if not result.get("ok"):
            if result.get("waiting"):
                return None
            return self._error(result.get("message", "Reinvestimento não confirmado"))
        self._upgrades += max(0, int(result.get("upgrades", 0)))
        self._buildings += max(0, int(result.get("buildings", 0)))
        # Exibe o saldo após as compras, não o snapshot anterior.
        snapshot = dict(snapshot, cookies=result.get("after", snapshot.get("cookies", 0)))
        return self._report(
            EstadoSimpleFarm.COLETANDO,
            result.get("message", "Excedente reinvestido com segurança."),
            f"Foram gastos {float(result.get('spent', 0)):.3g}; caixa protegido mantido.",
            snapshot,
            plano,
        )

    def _planejar(self, snapshot: dict) -> Optional[PlanoSimpleFarm]:
        raw = self.bridge.forecast_simple_farm_spell(self.configuracao.busca_maxima_spells)
        if not isinstance(raw, dict) or not raw.get("ok"):
            return None
        outcomes = tuple(str(value) for value in raw.get("results", ()))
        if outcomes != ("click frenzy",):
            return None
        return PlanoSimpleFarm(
            seed=str(raw.get("seed", snapshot.get("seed", ""))),
            versao=str(raw.get("version", snapshot.get("version", ""))),
            cast_atual=int(raw.get("currentCast", snapshot.get("spellsCastTotal", 0))),
            cast_inicial=int(raw["startCast"]),
            resultados=outcomes,
            spells_a_pular=int(raw.get("skipCount", 0)),
            qualidade=str(raw.get("quality", "Click Frenzy")),
        )

    def _alinhar(self, snapshot: dict, plano: PlanoSimpleFarm) -> RelatorioSimpleFarm:
        if self._janela_ativa(snapshot):
            return self._report(
                EstadoSimpleFarm.ALINHANDO,
                "Um multiplicador natural está ativo, mas a magia ainda não está alinhada.",
                "O bot aproveitará os cliques e só fará o skip depois que o buff terminar.",
                snapshot,
                plano,
            )
        magic = float(snapshot.get("magic", 0))
        maximum = float(snapshot.get("magicM", 0))
        cost = float(snapshot.get("skipSpellCost", float("inf")))
        if maximum > 0 and magic + 1e-7 >= maximum and magic + 1e-7 >= cost:
            result = self.bridge.cast_combo_skip(
                expected_cast=int(snapshot.get("spellsCastTotal", 0)),
                spell_id=self.SKIP_SPELL_ID,
            )
            if not result.get("ok"):
                return self._error(result.get("message", "O skip de baixo custo não foi confirmado"))
            return self._report(
                EstadoSimpleFarm.ALINHANDO,
                "Haggler's Charm usada uma vez com mana máxima.",
                "Aguardando a barra encher novamente; nenhum Sugar Lump será usado.",
                snapshot,
                plano,
            )
        return self._report(
            EstadoSimpleFarm.ALINHANDO,
            f"Faltam {plano.spells_a_pular} skip(s); aguardando mana máxima.",
            "A regeneração é preservada: a spell barata só é usada com a barra cheia.",
            snapshot,
            plano,
        )

    def _janela_ativa(self, snapshot: dict) -> bool:
        return any(
            str(buff.get("type")) in self.DIRECT_CLICK_BUFFS | self.PRODUCTION_CLICK_BUFFS
            and float(buff.get("timeSeconds", 0)) > 0
            for buff in snapshot.get("buffs", ())
        )

    def _melhor_buff_natural(self, snapshot: dict) -> Optional[str]:
        minimum = self.configuracao.duracao_minima_buff
        if self._buff(snapshot, "click frenzy") or self._buff(snapshot, "dragonflight"):
            return None
        allowed = {
            "frenzy", "dragon harvest", "building buff", "blood frenzy",
        }
        candidates = [
            buff for buff in snapshot.get("buffs", ())
            if str(buff.get("type")) in allowed
            and float(buff.get("timeSeconds", 0)) >= minimum
        ]
        if not candidates:
            return None
        return str(max(candidates, key=lambda buff: float(buff.get("multCpS", 1))).get("name") or "buff")

    @staticmethod
    def _buff(snapshot: dict, buff_type: str):
        return next(
            (buff for buff in snapshot.get("buffs", ()) if str(buff.get("type")) == buff_type),
            None,
        )

    def _sincronizar_clicker(self, snapshot: dict) -> bool:
        """Liga somente em janelas fortes de clique e desliga ao terminarem."""
        buffs = [
            buff for buff in snapshot.get("buffs", ())
            if float(buff.get("timeSeconds", 0)) > 0.25
        ]
        types = {str(buff.get("type")) for buff in buffs}
        direct = bool(types & self.DIRECT_CLICK_BUFFS) or any(
            float(buff.get("multClick", 1) or 1) >= 10 for buff in buffs
        )
        production_stack = len(types & self.PRODUCTION_CLICK_BUFFS) >= 2
        return self._set_clicker(direct or production_stack)

    def _set_clicker(self, enabled: bool) -> bool:
        if enabled == self._clicker_ativo:
            return True
        operation = self.habilitar_clicker if enabled else self.desabilitar_clicker
        if not operation():
            return False
        self._clicker_ativo = enabled
        return True

    def _report(self, state, message, next_step, snapshot, plano):
        return RelatorioSimpleFarm(
            estado=state,
            mensagem=message,
            proximo_passo=next_step + (f" Compras: {self._investment_status}" if self._investment_status else ""),
            plano=plano,
            cast_atual=int(snapshot.get("spellsCastTotal", 0)),
            mana=float(snapshot.get("magic", 0)),
            mana_maxima=float(snapshot.get("magicM", 0)),
            cookies_assados=float(snapshot.get("cookiesEarned", 0)),
            cookies_no_banco=float(snapshot.get("cookies", 0)),
            buffs_ativos=tuple(
                str(buff.get("name") or buff.get("type")) for buff in snapshot.get("buffs", ())
            ),
            golden_cookies_coletados=self._golden_cookies,
            magias_executadas=self._magias,
            upgrades_comprados=self._upgrades,
            construcoes_compradas=self._buildings,
            caixa_reservado=max(self._cash_floor, self._live_reserve),
            pantheon_slots=tuple(int(value) for value in snapshot.get("pantheonSlots", ())),
        )

    def _error(self, message: str, *, stop_clicker: bool = True):
        if stop_clicker:
            self._set_clicker(False)
        return RelatorioSimpleFarm(
            EstadoSimpleFarm.ERRO_SEGURO,
            "Simple Farm bloqueado em estado seguro.",
            "Corrija o diagnóstico e inicie novamente.",
            golden_cookies_coletados=self._golden_cookies,
            magias_executadas=self._magias,
            upgrades_comprados=self._upgrades,
            construcoes_compradas=self._buildings,
            caixa_reservado=self._cash_floor,
            erro=message,
        )

    def _interrompido(self, message: str):
        self._set_clicker(False)
        return RelatorioSimpleFarm(
            EstadoSimpleFarm.INTERROMPIDO,
            message,
            "Nenhuma nova ação será iniciada.",
            golden_cookies_coletados=self._golden_cookies,
            magias_executadas=self._magias,
            upgrades_comprados=self._upgrades,
            construcoes_compradas=self._buildings,
            caixa_reservado=self._cash_floor,
        )
