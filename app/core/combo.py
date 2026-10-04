"""Máquina de estados do combo endgame, com replanejamento contínuo."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from app.models.combo import ConfiguracaoCombo, EstadoCombo, PlanoCombo, RelatorioCombo
from app.utils.logger import logger


class ComboAutomation:
    """Prepara e executa um combo somente após validar cada precondição."""

    PANTHEON = (2, 8, 6)  # Godzamok, Mokalsium, Muridal
    AURAS_PREPARACAO = (4, 13)  # Reaper of Fields, Epoch Manipulator
    WIZARD_TOWERS_PRIMEIRO_CAST = 601
    CURSORS_GODZAMOK = 601
    SKIP_SPELL_ID = 4  # Haggler's Charm
    COOKIE_STORM_DROP = "cookie storm drop"

    def __init__(
        self,
        bridge,
        configuracao: ConfiguracaoCombo,
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
        self._pause_released = threading.Event()
        self._pause_plan: Optional[PlanoCombo] = None
        self._lumps_gastos = 0
        self._click_deadline: Optional[float] = None
        self._inicio_espera: Optional[float] = None
        self._wizard_towers_originais: Optional[int] = None
        self._latest_snapshot: Optional[dict] = None
        self._garden_maduras = 0
        self._garden_total = 0
        self._last_report = RelatorioCombo(EstadoCombo.OCIOSO, "Combo não iniciado.")

    def parar(self) -> None:
        """Solicita parada cooperativa; nenhuma nova mutação começa depois disso."""
        self._stop.set()

    def retomar(self) -> None:
        """Libera uma única pausa de acompanhamento nesta execução."""
        if self._pause_plan is not None:
            self._pause_released.set()

    def _report_pausa(self, snapshot: dict) -> RelatorioCombo:
        plano = self._pause_plan
        remaining = max(0, plano.cast_inicial - int(snapshot.get("spellsCastTotal", 0)))
        return self._report(
            EstadoCombo.PAUSADO,
            f"Pausa de acompanhamento: faltavam até 3 skips; agora faltam {remaining} para o plano guardado.",
            "Clique em Retomar combo quando estiver pronto. Nenhuma ação no jogo será executada até lá.",
            snapshot,
            plano,
        )

    def gerar_previa(self) -> RelatorioCombo:
        """Lê e planeja sem alterar o jogo."""
        snapshot = self.bridge.get_combo_snapshot()
        if not snapshot.get("available"):
            return self._error(snapshot.get("message", "Runtime indisponível"))
        plano = self._planejar(snapshot)
        if plano is None:
            return self._error("Nenhuma janela EF + CF + BS foi encontrada no alcance configurado.")
        return self._report(
            EstadoCombo.PREVIA,
            f"Janela calculada on-the-go: {plano.resumo}.",
            "Inicie o modo real para pausar as demais automações e preparar o save.",
            snapshot,
            plano,
        )

    def executar(self, atualizar: Optional[Callable[[RelatorioCombo], None]] = None) -> RelatorioCombo:
        """Executa até conclusão, parada manual ou erro seguro."""
        atualizar = atualizar or (lambda _report: None)
        try:
            while not self._stop.is_set():
                report = self.executar_passo()
                self._last_report = report
                atualizar(report)
                if report.terminal:
                    return report
                self.dormir(self.configuracao.intervalo_verificacao)
            return self._interrompido("Parada solicitada pelo usuário.")
        except Exception as error:  # barreira final da thread autônoma
            logger.exception("Falha inesperada no modo Combo")
            return self._error(f"Falha inesperada: {error}")
        finally:
            self.desabilitar_clicker()

    def executar_passo(self) -> RelatorioCombo:
        if self._stop.is_set():
            return self._interrompido("Parada solicitada pelo usuário.")

        snapshot = self.bridge.get_combo_snapshot()
        if not snapshot.get("available"):
            return self._error(snapshot.get("message", "Runtime indisponível"))
        self._latest_snapshot = snapshot
        if snapshot.get("screen") != "game":
            return self._error("O Cookie Clicker não está na tela normal do jogo.")

        if self._wizard_towers_originais is None:
            self._wizard_towers_originais = int(snapshot.get("wizardTowers", 0))

        if self._pause_plan is not None:
            if not self._pause_released.is_set():
                return self._report_pausa(snapshot)
            self._pause_plan = None

        if self._click_deadline is None and (
            snapshot.get("achievementWon") or float(snapshot.get("cookiesEarned", 0)) >= self.configuracao.alvo_cookies
        ):
            self.desabilitar_clicker()
            self._restore_wizard_towers(snapshot)
            return self._report(
                EstadoCombo.CONCLUIDO,
                "Meta confirmada: And a little extra foi obtida.",
                "Combo encerrado; as automações pausadas podem ser retomadas.",
                snapshot,
                None,
            )

        if self._click_deadline is not None:
            return self._monitorar_cliques(snapshot)

        if self._inicio_espera is None:
            self._inicio_espera = self.relogio()
        if self.relogio() - self._inicio_espera >= self.configuracao.tempo_maximo_espera:
            return self._interrompido(
                "Limite de espera atingido sem uma pilha válida; nenhuma tentativa final foi disparada."
            )

        plano = self._planejar(snapshot)
        if plano is None:
            return self._error("Nenhuma janela EF + CF + BS foi encontrada no alcance configurado.")

        if (
            self.configuracao.pausar_antes_ultimos_skips
            and not self._pause_released.is_set()
            and plano.cast_inicial - int(snapshot.get("spellsCastTotal", 0)) <= 3
        ):
            self.desabilitar_clicker()
            self._pause_plan = plano
            return self._report_pausa(snapshot)

        # Golden Cookies naturais são coletados apenas pelo dono exclusivo do modo Combo.
        natural = next(
            (item for item in snapshot.get("shimmers", ()) if not item.get("force")),
            None,
        )
        if natural is not None:
            result = self.bridge.pop_combo_natural_shimmer(int(natural["id"]))
            if not result.get("ok"):
                if result.get("gone"):
                    return self._report(
                        EstadoCombo.PREPARANDO,
                        "Golden Cookie expirou antes da coleta.",
                        "Recalculando o runtime sem considerar o shimmer antigo.",
                        snapshot,
                        plano,
                    )
                return self._error(result.get("message", "Falha ao coletar Golden Cookie natural"))
            return self._report(
                EstadoCombo.PREPARANDO,
                "Golden Cookie natural coletado pelo modo Combo.",
                "Recalculando buffs e plano no próximo snapshot.",
                snapshot,
                plano,
            )

        forced = [item for item in snapshot.get("shimmers", ()) if item.get("force")]
        unexpected = [item for item in forced if item.get("force") != self.COOKIE_STORM_DROP]
        if unexpected:
            return self._error(
                "Há um shimmer de spell inesperado em tela; execução bloqueada para não clicar no cookie errado."
            )
        if forced:
            result = self.bridge.pop_combo_cookie_storm_drops()
            count = int(result.get("count", 0))
            return self._report(
                EstadoCombo.PREPARANDO,
                f"Cookie Storm em andamento: {count} drop(s) coletado(s) com segurança.",
                "A tempestade não interrompe o modo; novos drops serão drenados no próximo ciclo.",
                snapshot,
                plano,
            )

        preparation = self._preparar_estado_estatico(snapshot, plano)
        if preparation is not None:
            return preparation

        cast_atual = int(snapshot.get("spellsCastTotal", 0))
        ready, reason = self._buffs_prontos(snapshot, plano)
        # O Garden apenas acelera a coleta. Uma pilha natural pronta sempre
        # tem prioridade, inclusive sobre leitura, plantio e maturidade.
        if not ready:
            try:
                garden_report, _ = self._preparar_garden(snapshot, plano)
            except Exception as error:
                logger.warning("Combo: manutenção opcional do Garden falhou: %s", error)
                garden_report = None
            if self._stop.is_set():
                return self._interrompido("Parada solicitada durante a preparação opcional do Garden.")
            if garden_report is not None and garden_report.estado == EstadoCombo.PREPARANDO:
                return garden_report
        if cast_atual < plano.cast_inicial:
            return self._alinhar_spells(snapshot, plano)
        if cast_atual > plano.cast_inicial:
            # Outro ator lançou uma spell entre snapshots; não reutilize o plano obsoleto.
            novo = self._planejar(snapshot)
            if novo is None or novo.cast_inicial < cast_atual:
                return self._error("O contador de spells ultrapassou a janela e não foi possível replanejar.")
            plano = novo
            ready, reason = self._buffs_prontos(snapshot, plano)

        if float(snapshot.get("magic", 0)) + 1e-7 < float(snapshot.get("magicM", 0)):
            return self._report(
                EstadoCombo.ALINHANDO,
                "Janela alinhada; aguardando a mana ficar completamente cheia.",
                "Golden Cookies naturais continuam sendo coletados durante a recarga.",
                snapshot,
                plano,
            )
        if not snapshot.get("canRefillLump"):
            remaining = max(0.0, float(snapshot.get("lumpRefillRemaining", 0)))
            return self._report(
                EstadoCombo.ALINHANDO,
                f"Janela alinhada; recarga por Sugar Lump em cooldown ({remaining:.0f} s).",
                "O Quadcast só será armado quando a recarga estiver novamente disponível.",
                snapshot,
                plano,
            )
        required_lumps = 1 + int(
            self.configuracao.usar_sugar_frenzy and not snapshot.get("sugarFrenzyUsed")
        )
        if int(snapshot.get("lumps", 0)) < required_lumps:
            return self._error(
                f"São necessários {required_lumps} Sugar Lumps para o Quadcast final configurado."
            )

        if not ready:
            return self._report(
                EstadoCombo.AGUARDANDO_BUFFS,
                reason,
                "Aguardando DH + BS; Frenzy pode vir do Quadcast. "
                f"Restam {max(0, self.configuracao.tempo_maximo_espera - (self.relogio() - self._inicio_espera)) / 60:.0f} min de busca.",
                snapshot,
                plano,
            )

        # Inicia o clicker antes dos buffs curtos para não perder a latência
        # da resposta CDP e da ativação da thread dentro dos 10 s de Godzamok.
        if not self.habilitar_clicker():
            return self._error("O clicker não pôde ser iniciado; Quadcast não foi lançado.")
        started = self.relogio()
        result = self.bridge.execute_combo_quadcast(
            expected_cast=plano.cast_inicial,
            expected_results=list(plano.resultados),
            minimum_buff_seconds=self.configuracao.duracao_minima_buff,
            required_natural_bs=plano.building_specials_naturais,
            use_sugar_frenzy=self.configuracao.usar_sugar_frenzy,
            use_loans=self.configuracao.usar_loans,
        )
        if not result.get("ok"):
            self.desabilitar_clicker()
            self._lumps_gastos += int(result.get("lumpsSpent", 0))
            if result.get("retryable") and not result.get("mutated"):
                return self._report(
                    EstadoCombo.AGUARDANDO_BUFFS,
                    result.get("message", "A pilha mudou antes do disparo."),
                    "Revalidando sem consumir spells ou lumps.", snapshot, plano,
                )
            self._recover_after_quadcast_failure()
            return self._error(result.get("message", "Quadcast não foi confirmado"))
        self._lumps_gastos += int(result.get("lumpsSpent", 0))
        click_seconds = max(1.0, float(result.get("clickSeconds", 8.0)))
        self._click_deadline = started + click_seconds
        return self._report(
            EstadoCombo.CLICANDO,
            "Quadcast confirmado; clicker executando na janela final.",
            f"Janela segura estimada em {click_seconds:.1f} s.",
            snapshot,
            plano,
        )

    def _planejar(self, snapshot: dict) -> Optional[PlanoCombo]:
        raw = self.bridge.forecast_combo_window(
            self.configuracao.busca_maxima_spells,
            self.configuracao.building_specials_totais,
        )
        if not isinstance(raw, dict) or not raw.get("ok"):
            return None
        outcomes = tuple(str(value) for value in raw.get("results", ()))
        if len(outcomes) != 4:
            return None
        return PlanoCombo(
            seed=str(raw.get("seed", snapshot.get("seed", ""))),
            versao=str(raw.get("version", snapshot.get("version", ""))),
            cast_atual=int(raw.get("currentCast", snapshot.get("spellsCastTotal", 0))),
            cast_inicial=int(raw["startCast"]),
            season=str(raw.get("season", snapshot.get("season", ""))),
            resultados=outcomes,
            spells_a_pular=int(raw.get("skipCount", 0)),
            building_specials_spell=int(raw.get("spellBuildingSpecials", 0)),
            building_specials_naturais=int(raw.get("naturalBuildingSpecials", 0)),
            score=float(raw.get("score", 0)),
        )

    def _preparar_estado_estatico(self, snapshot: dict, plano: PlanoCombo) -> Optional[RelatorioCombo]:
        if snapshot.get("season") != plano.season:
            result = self.bridge.set_combo_season(plano.season)
            return self._action_report(result, "Season ajustada para o forecast.", snapshot, plano)
        if snapshot.get("goldenSwitchOn"):
            result = self.bridge.set_combo_golden_switch(False)
            return self._action_report(result, "Golden Switch desligado durante a busca natural.", snapshot, plano)
        if int(snapshot.get("officeLevel", 0)) < 5 and self.configuracao.usar_loans:
            result = self.bridge.upgrade_combo_office_once()
            return self._action_report(result, "Escritório do Stock Market avançado.", snapshot, plano)
        cursor_amount = next(
            (
                int(building.get("amount", 0))
                for building in snapshot.get("buildings", ())
                if int(building.get("id", -1)) == 0
            ),
            0,
        )
        if cursor_amount < self.CURSORS_GODZAMOK:
            result = self.bridge.ensure_combo_building_minimum(0, self.CURSORS_GODZAMOK)
            return self._action_report(
                result,
                "Cursors recompostos para a venda final de Godzamok.",
                snapshot,
                plano,
            )
        if tuple(snapshot.get("pantheonSlots", ())) != self.PANTHEON:
            swaps = int(snapshot.get("pantheonSwaps", 0))
            if swaps < 1:
                return self._report(
                    EstadoCombo.PREPARANDO,
                    "Pantheon aguarda regeneração de worship swap.",
                    "Nenhum Sugar Lump será usado para o Pantheon.",
                    snapshot,
                    plano,
                )
            result = self.bridge.configure_combo_pantheon(list(self.PANTHEON))
            return self._action_report(result, "Pantheon preparado para o combo.", snapshot, plano)
        if tuple(snapshot.get("auras", ())) != self.AURAS_PREPARACAO:
            result = self.bridge.set_combo_auras(*self.AURAS_PREPARACAO)
            return self._action_report(result, "Auras de coleta configuradas.", snapshot, plano)
        if int(snapshot.get("wizardTowers", 0)) != self.WIZARD_TOWERS_PRIMEIRO_CAST:
            result = self.bridge.set_combo_wizard_towers(self.WIZARD_TOWERS_PRIMEIRO_CAST)
            return self._action_report(result, "Wizard Towers ajustadas para o primeiro cast.", snapshot, plano)
        return None

    def _alinhar_spells(self, snapshot: dict, plano: PlanoCombo) -> RelatorioCombo:
        remaining = plano.cast_inicial - int(snapshot.get("spellsCastTotal", 0))
        magic = float(snapshot.get("magic", 0))
        maximum = float(snapshot.get("magicM", 0))
        cost = float(snapshot.get("skipSpellCost", float("inf")))
        mana_cheia = maximum > 0 and magic + 1e-7 >= maximum
        refill_disponivel = bool(
            snapshot.get("canRefillLump")
            and self._lumps_gastos < self.configuracao.maximo_lumps_alinhamento
            and int(snapshot.get("lumps", 0)) > 0
        )
        # Com refill autorizado e disponivel, consome a barra em skips antes
        # de gastar o lump. Cada cast ainda passa por um novo snapshot/plano.
        if mana_cheia or (refill_disponivel and magic >= cost):
            if magic + 1e-7 < cost:
                return self._error(
                    "Mesmo com a mana cheia, Haggler's Charm não cabe na barra atual."
                )
            result = self.bridge.cast_combo_skip(
                expected_cast=int(snapshot.get("spellsCastTotal", 0)),
                spell_id=self.SKIP_SPELL_ID,
            )
            return self._action_report(
                result,
                f"Spell de alinhamento lançada; faltavam {remaining} skips.",
                snapshot,
                plano,
                EstadoCombo.ALINHANDO,
            )
        if (
            remaining > 0
            and refill_disponivel
            and magic < cost
        ):
            result = self.bridge.refill_combo_magic(int(snapshot.get("spellsCastTotal", 0)))
            if result.get("ok"):
                self._lumps_gastos += int(result.get("lumpsSpent", 1))
            return self._action_report(
                result,
                "Mana recarregada para continuar o alinhamento.",
                snapshot,
                plano,
                EstadoCombo.ALINHANDO,
            )
        return self._report(
            EstadoCombo.ALINHANDO,
            f"Aguardando mana máxima; faltam {remaining} spells até a janela recalculada.",
            "Sem refill disponível, Haggler's Charm aguarda a barra cheia; com refill disponível, consome a mana antes da recarga.",
            snapshot,
            plano,
        )

    def _preparar_garden(self, snapshot: dict, plano: PlanoCombo):
        def optional_problem(message: str):
            return self._report(
                EstadoCombo.AGUARDANDO_GARDEN,
                "Garden opcional: " + message,
                "O alinhamento e a busca de buffs continuam; o Garden não bloqueia o Quadcast.",
                snapshot,
                plano,
            ), False

        try:
            garden = self.bridge.get_garden_snapshot()
        except Exception as error:
            return optional_problem(str(error))
        if not garden.status.available:
            return optional_problem(garden.status.message)
        required = {"goldenClover", "nursetulip"}
        if not required.issubset(garden.unlocked_seed_keys):
            return optional_problem("Golden Clover ou Nursetulip não está desbloqueada.")
        plants = {(plant.x, plant.y): plant for plant in garden.plants}
        desired = {
            tile: ("nursetulip" if tile[0] % 3 == 1 else "goldenClover")
            for tile in garden.unlocked_tiles
        }
        total = len(desired)
        if not total:
            return optional_problem("O Garden não possui espaços desbloqueados.")
        mature_plants = [
            plants[position] for position, key in desired.items()
            if position in plants and plants[position].key == key and plants[position].mature
        ]
        mature = len(mature_plants)
        self._garden_maduras = mature
        self._garden_total = total
        if garden.frozen:
            result = self.bridge.set_garden_frozen(False)
            if not result.success:
                return optional_problem(result.message)
            return self._garden_action_report(result, snapshot, plano), False
        # Clay prolonga a coleta, mas seus ticks de 15 min tornam a formação
        # das Nursetulips muito lenta. Fertilizer cresce em ticks de 3 min;
        # troca para Clay quando já há uma maioria útil, sem exigir perfeição.
        tulips_total = sum(key == "nursetulip" for key in desired.values())
        tulips_mature = sum(plant.key == "nursetulip" for plant in mature_plants)
        harvest_ready = mature * 2 >= total and tulips_mature * 2 >= tulips_total
        desired_soil = "clay" if harvest_ready else "fertilizer"
        if garden.soil_key != desired_soil:
            result = self.bridge.change_garden_soil(desired_soil)
            if result.success:
                return self._garden_action_report(result, snapshot, plano), False
            # Cooldown de solo é uma espera legítima, não um erro fatal.
            return self._report(
                EstadoCombo.AGUARDANDO_GARDEN,
                result.message,
                f"A troca para {desired_soil} será tentada novamente sem bloquear os buffs.",
                snapshot,
                plano,
            ), False

        for position, key in desired.items():
            plant = plants.get(position)
            if plant is not None and plant.key != key:
                result = self.bridge.harvest_garden_tile(
                    position[0], position[1], expected_key=plant.key, require_mature=False
                )
                if not result.success:
                    return optional_problem(result.message)
                return self._garden_action_report(result, snapshot, plano), False

        missing = [
            (position, key) for position, key in desired.items()
            if plants.get(position) is None
        ]
        if missing:
            planted = 0
            for position, key in missing:
                if self._stop.is_set():
                    return self._interrompido("Parada solicitada durante o plantio do Garden."), False
                result = self.bridge.plant_garden_seed(key, position[0], position[1])
                if not result.success:
                    return optional_problem(result.message)
                planted += 1
            return self._report(
                EstadoCombo.PREPARANDO,
                f"Garden preenchido rapidamente: {planted} semente(s) plantada(s) neste ciclo.",
                "Revalidando todo o canteiro antes de aguardar a maturidade.",
                snapshot,
                plano,
            ), False

        return None, True

    def _buffs_prontos(self, snapshot: dict, plano: PlanoCombo):
        minimum = self.configuracao.duracao_minima_buff
        buffs = list(snapshot.get("buffs", ()))
        by_type = {str(buff.get("type")): buff for buff in buffs}
        frenzy = by_type.get("frenzy")
        harvest = by_type.get("dragon harvest")
        building = [
            buff for buff in buffs
            if buff.get("type") == "building buff"
            and float(buff.get("timeSeconds", 0)) >= minimum
            and int(buff.get("buildingId", -1)) != 7
        ]
        missing = []
        if any(buff.get("type") in {"dragonflight", "cursed finger", "clot", "building debuff"}
               for buff in buffs):
            return False, "Aguardando expirar Dragonflight ou um efeito negativo incompatível."
        if (not frenzy or float(frenzy.get("timeSeconds", 0)) < minimum) and "frenzy" not in plano.resultados:
            missing.append("Frenzy")
        if not harvest or float(harvest.get("timeSeconds", 0)) < minimum:
            missing.append("Dragon Harvest")
        if len(building) < plano.building_specials_naturais:
            missing.append(
                f"{plano.building_specials_naturais - len(building)} Building Special(s)"
            )
        if missing:
            return False, "Ainda faltam: " + ", ".join(missing) + "."
        return True, "Pilha natural confirmada com margem de duração."

    def _monitorar_cliques(self, snapshot: dict) -> RelatorioCombo:
        achieved = snapshot.get("achievementWon") or float(snapshot.get("cookiesEarned", 0)) >= self.configuracao.alvo_cookies
        active = {str(buff.get("type")) for buff in snapshot.get("buffs", ())}
        if self.relogio() >= (self._click_deadline or 0) or not {"blood frenzy", "click frenzy"}.issubset(active):
            self.desabilitar_clicker()
            self._restore_wizard_towers(snapshot)
            if achieved:
                return self._report(
                    EstadoCombo.CONCLUIDO,
                    "Meta confirmada; janela de cliques aproveitada até o fim.",
                    "Combo encerrado.", snapshot, None,
                )
            return self._error(
                "A janela final terminou antes de confirmar 1e72; o bot parou sem repetir gastos."
            )
        remaining = max(0.0, (self._click_deadline or 0) - self.relogio())
        return self._report(
            EstadoCombo.CLICANDO,
            ("Meta atingida; " if achieved else "Clicker ativo; ") + f"{remaining:.1f} s de margem planejada.",
            "Monitorando cookiesEarned e buffs a cada snapshot.",
            snapshot,
            None,
        )

    def _restore_wizard_towers(self, snapshot: dict) -> None:
        if self._wizard_towers_originais is None:
            return
        current = int(snapshot.get("wizardTowers", 0))
        if current < self._wizard_towers_originais:
            result = self.bridge.set_combo_wizard_towers(self._wizard_towers_originais)
            if not result.get("ok"):
                logger.warning("Combo: não foi possível restaurar Wizard Towers: %s", result.get("message"))

    def _recover_after_quadcast_failure(self) -> None:
        """Tenta somente a restauração idempotente das torres após falha parcial."""
        try:
            snapshot = self.bridge.get_combo_snapshot()
            if isinstance(snapshot, dict) and snapshot.get("available"):
                self._latest_snapshot = snapshot
                self._restore_wizard_towers(snapshot)
        except Exception as error:
            logger.warning("Combo: falha ao consultar estado para recuperar Wizard Towers: %s", error)

    def _action_report(
        self, result: dict, success_message: str, snapshot: dict, plano: PlanoCombo,
        state: EstadoCombo = EstadoCombo.PREPARANDO,
    ) -> RelatorioCombo:
        if not result.get("ok"):
            if result.get("waiting"):
                return self._report(
                    state,
                    result.get("message", "Aguardando a precondição da ação."),
                    "O estado será revalidado no próximo ciclo.",
                    snapshot,
                    plano,
                )
            return self._error(result.get("message", "Ação não confirmada"))
        return self._report(
            state,
            result.get("message") or success_message,
            "Revalidando o runtime antes da próxima ação.",
            snapshot,
            plano,
        )

    def _garden_action_report(self, result, snapshot: dict, plano: PlanoCombo) -> RelatorioCombo:
        if not result.success:
            return self._error(result.message)
        return self._report(
            EstadoCombo.PREPARANDO,
            result.message,
            "Revalidando o Garden antes da próxima ação.",
            snapshot,
            plano,
        )

    def _report(
        self,
        state: EstadoCombo,
        message: str,
        next_step: str,
        snapshot: dict,
        plano: Optional[PlanoCombo],
        *,
        garden_maduras: Optional[int] = None,
        garden_total: Optional[int] = None,
    ) -> RelatorioCombo:
        buffs = tuple(
            f"{buff.get('name') or buff.get('type')} ({float(buff.get('timeSeconds', 0)):.1f} s)"
            for buff in snapshot.get("buffs", ())
        )
        return RelatorioCombo(
            estado=state,
            mensagem=message,
            proximo_passo=next_step,
            plano=plano,
            cast_atual=int(snapshot.get("spellsCastTotal", 0)),
            mana=float(snapshot.get("magic", 0)),
            mana_maxima=float(snapshot.get("magicM", 0)),
            lumps=int(snapshot.get("lumps", 0)),
            lumps_gastos=self._lumps_gastos,
            cookies_assados=float(snapshot.get("cookiesEarned", 0)),
            buffs_ativos=buffs,
            building_specials_ativos=sum(
                buff.get("type") == "building buff" for buff in snapshot.get("buffs", ())
            ),
            garden_maduras=self._garden_maduras if garden_maduras is None else garden_maduras,
            garden_total=self._garden_total if garden_total is None else garden_total,
        )

    def _error(self, message: str) -> RelatorioCombo:
        self.desabilitar_clicker()
        return RelatorioCombo(
            EstadoCombo.ERRO_SEGURO,
            "Execução bloqueada em estado seguro.",
            "Corrija o diagnóstico e inicie novamente; gastos ambíguos não serão repetidos.",
            lumps_gastos=self._lumps_gastos,
            erro=message,
        )

    def _interrompido(self, message: str) -> RelatorioCombo:
        self.desabilitar_clicker()
        return RelatorioCombo(
            EstadoCombo.INTERROMPIDO,
            message,
            "Nenhuma nova ação será iniciada.",
            lumps_gastos=self._lumps_gastos,
        )
