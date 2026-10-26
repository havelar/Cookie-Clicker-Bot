"""Máquina de estados do combo endgame, com replanejamento contínuo."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from app.models.combo import ConfiguracaoCombo, EstadoCombo, PlanoCombo, RelatorioCombo
from app.utils.logger import logger
from app.core.garden_catalog import GARDEN_CATALOG
from app.core.garden_golden import golden_layout, golden_soil
from app.core.combo_planning import choose, estimate
from app.models.garden import GardenAction
from dataclasses import replace


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
        self._plan_key = None
        self._selected_candidate = None
        self._garden_check_at = 0.0
        self._garden_tick = None
        self._busca_armada = False
        self._ciclos_concluidos = 0
        self._residuos_combo = ()
        self._session_seed = None
        self._cash_floor = 0.0
        self._rebuild = {}
        self._last_report = RelatorioCombo(EstadoCombo.OCIOSO, "Combo não iniciado.")

    def parar(self) -> None:
        """Solicita parada cooperativa; nenhuma nova mutação começa depois disso."""
        self._stop.set()

    def retomar(self) -> None:
        """Libera uma única pausa de acompanhamento nesta execução."""
        if self._pause_plan is not None:
            self._plan_key = None
            self._pause_released.set()

    def _report_pausa(self, snapshot: dict) -> RelatorioCombo:
        plano = self._pause_plan
        remaining = max(0, plano.cast_inicial - int(snapshot.get("spellsCastTotal", 0)))
        return self._report(
            EstadoCombo.PAUSADO,
            f"Combo pausado. Magias de preparação restantes: {remaining} para o plano guardado.",
            "Clique em Retomar combo quando estiver pronto. Nenhuma ação no jogo será executada até lá.",
            snapshot,
            plano,
        )

    def gerar_previa(self) -> RelatorioCombo:
        """Lê e planeja sem alterar o jogo."""
        snapshot = self.bridge.get_combo_snapshot()
        if not snapshot.get("available"):
            return self._error(snapshot.get("message", "Não foi possível ler o jogo. Verifique a conexão."))
        plano = self._planejar(snapshot)
        if plano is None:
            if any(b.get('type') == 'dragonflight' for b in snapshot.get('buffs', ())):
                return self._report(EstadoCombo.AGUARDANDO_BUFFS, 'Aguardando terminar o Voo do dragão.',
                                    'A previsão será refeita quando o frenesi de cliques voltar a ser possível.', snapshot, None)
            return self._error("Nenhuma janela EF + CF + BS foi encontrada no alcance configurado.")
        return self._report(
            EstadoCombo.PREVIA,
            f"Oportunidade planejada: {plano.resumo}.",
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
            if hasattr(self.bridge, "set_combo_cash_floor"):
                self.bridge.set_combo_cash_floor(0)

    def executar_passo(self) -> RelatorioCombo:
        if self._stop.is_set():
            return self._interrompido("Parada solicitada pelo usuário.")

        snapshot = self.bridge.get_combo_snapshot()
        if not snapshot.get("available"):
            return self._error(snapshot.get("message", "Não foi possível ler o jogo. Verifique a conexão."))
        self._latest_snapshot = snapshot
        if snapshot.get("screen") != "game":
            return self._error("O Cookie Clicker não está na tela normal do jogo.")

        if self._wizard_towers_originais is None:
            self._wizard_towers_originais = int(snapshot.get("wizardTowers", 0))

        if self._pause_plan is not None:
            if not self._pause_released.is_set():
                return self._report_pausa(snapshot)
            self._pause_plan = None

        if self._session_seed is None:
            self._session_seed = snapshot.get('seed')
        elif snapshot.get('seed') != self._session_seed:
            return self._error('O save mudou durante o farm; inicie novamente para revalidar os gastos.')
        if self._click_deadline is None:
            if self._lumps_gastos >= self.configuracao.maximo_lumps_total:
                return self._interrompido('Limite de torrões desta sessão atingido. Nenhum novo combo será preparado.')
            if not self._cash_floor:
                self._cash_floor = float(snapshot.get('cookies', 0)) * self.configuracao.reserva_caixa_percentual / 100
        if hasattr(self.bridge, 'set_combo_cash_floor'):
            self.bridge.set_combo_cash_floor(self._cash_floor)

        if self._click_deadline is not None:
            return self._monitorar_cliques(snapshot)

        if self._inicio_espera is None:
            self._inicio_espera = self.relogio()
        if self.relogio() - self._inicio_espera >= self.configuracao.tempo_maximo_espera:
            self._inicio_espera = self.relogio()
            return self._report(EstadoCombo.AGUARDANDO_BUFFS, 'Nenhuma oportunidade nesta janela; a busca continua.',
                                'A sequência e o orçamento da sessão são preservados.', snapshot, None)

        if any(b.get('type') == 'dragonflight' for b in snapshot.get('buffs', ())):
            return self._report(EstadoCombo.AGUARDANDO_BUFFS, 'Aguardando terminar o Voo do dragão.',
                                'A previsão será refeita quando o frenesi de cliques voltar a ser possível.', snapshot, None)

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
                        "Buscando outra oportunidade de Golden Cookie.",
                        snapshot,
                        plano,
                    )
                return self._error(result.get("message", "Falha ao coletar Golden Cookie natural"))
            return self._report(
                EstadoCombo.PREPARANDO,
                "Golden Cookie natural coletado pelo modo Combo.",
                "Atualizando os bônus e a próxima oportunidade.",
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
                return self._error("A oportunidade de combo passou e não foi possível encontrar outra.")
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
        usar_acucar = self._usar_sugar_frenzy(snapshot)
        required_lumps = 1 + int(usar_acucar)
        if int(snapshot.get('lumps', 0)) < required_lumps:
            return self._interrompido('Faltam torrões para a próxima tentativa. Nenhum novo gasto foi feito.')

        if self.configuracao.usar_loans and any(
                'loan' in str(b.get('name', '')).lower() + str(b.get('type', '')).lower()
                and 'interest' in str(b.get('name', '')).lower() + str(b.get('type', '')).lower()
                for b in snapshot.get('buffs', ())):
            return self._report(EstadoCombo.PREPARANDO, 'Aguardando terminar os juros dos empréstimos.',
                                'A espera armada começa quando os recursos finais estiverem disponíveis.', snapshot, plano)

        if not self._busca_armada:
            self._busca_armada = True
            self._inicio_espera = self.relogio()

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
            use_sugar_frenzy=usar_acucar,
            use_loans=self.configuracao.usar_loans,
            optimize_garden=self.configuracao.permitir_converter_garden and self.configuracao.otimizar_garden_final,
        )
        if not result.get("ok"):
            self.desabilitar_clicker()
            self._lumps_gastos += int(result.get("lumpsSpent", 0))
            if result.get("retryable") and not result.get("mutated"):
                return self._report(
                    EstadoCombo.AGUARDANDO_BUFFS,
                    result.get("message", "A pilha mudou antes do disparo."),
                    "Conferindo a oportunidade sem gastar mana ou Sugar Lumps.", snapshot, plano,
                )
            self._recover_after_quadcast_failure()
            return self._error(result.get("message", "Quadcast não foi confirmado"))
        self._lumps_gastos += int(result.get("lumpsSpent", 0))
        click_seconds = max(1.0, float(result.get("clickSeconds", 8.0)))
        self._click_deadline = started + click_seconds
        self._residuos_combo = tuple(result.get("preserved", ()))
        sold_ids = {int(item[0]) for item in result.get("sold", ())}
        self._rebuild = {int(b["id"]):int(b["amount"]) for b in snapshot.get("buildings", ())
                         if int(b.get("id", -1)) in sold_ids}
        return self._report(
            EstadoCombo.CLICANDO,
            "Quadcast confirmado; clicker executando na janela final.",
            f"Janela segura estimada em {click_seconds:.1f} s.",
            snapshot,
            plano,
        )

    def _usar_sugar_frenzy(self, snapshot):
        return (self.configuracao.usar_sugar_frenzy and not snapshot.get('sugarFrenzyUsed')
                and self.configuracao.maximo_lumps_total-self._lumps_gastos >= 2
                and int(snapshot.get('lumps', 0)) >= 2)

    def _planejar(self, snapshot: dict) -> Optional[PlanoCombo]:
        config = replace(self.configuracao, maximo_lumps_total=max(0, self.configuracao.maximo_lumps_total-self._lumps_gastos))
        current = int(snapshot.get('spellsCastTotal', 0))
        key = (snapshot.get('seed'), snapshot.get('version'), snapshot.get('fthofFailBase'),
               tuple(snapshot.get('auras', ())), snapshot.get('seasonSwitchAvailable'),
               sum(int(b.get('amount', 0)) for b in snapshot.get('buildings', ())) >= 10,
               tuple(sorted(b.get('type', '') for b in snapshot.get('buffs', ())
                            if b.get('type') in {'dragonflight', 'magic adept', 'magic inept'})))
        selected = self._selected_candidate
        if self._plan_key != key or not selected or current > selected['startCast']:
            if hasattr(self.bridge, 'forecast_combo_candidates'):
                raw = self.bridge.forecast_combo_candidates(self.configuracao.busca_maxima_spells,
                                                            self.configuracao.building_specials_totais)
                selected = choose(raw.get('candidates', ()), snapshot, config) if raw.get('ok') else None
            else:
                # Compatibilidade com bridges antigos; a implementação atual usa alternativas isoladas.
                raw = self.bridge.forecast_combo_window(self.configuracao.busca_maxima_spells,
                                                        self.configuracao.building_specials_totais)
                selected = raw if isinstance(raw, dict) and raw.get('ok') else None
            self._selected_candidate, self._plan_key = selected, key
        if not selected or len(selected.get('results', ())) != 4:
            return None
        raw = estimate(selected, snapshot, config)
        return PlanoCombo(
            seed=str(raw.get('seed', snapshot.get('seed', ''))),
            versao=str(raw.get('version', snapshot.get('version', ''))),
            cast_atual=current, cast_inicial=int(raw['startCast']), season=str(raw.get('season', snapshot.get('season', ''))),
            resultados=tuple(raw['results']), spells_a_pular=max(0, int(raw['startCast'])-current),
            building_specials_spell=int(raw['spellBuildingSpecials']), building_specials_naturais=int(raw['naturalBuildingSpecials']),
            score=float(raw['score']), ganho_estimado=raw['estimatedGain'], preparo_estimado=raw['preparationSeconds'])

    def _preparar_estado_estatico(self, snapshot: dict, plano: PlanoCombo) -> Optional[RelatorioCombo]:
        if snapshot.get("season") != plano.season:
            result = self.bridge.set_combo_season(plano.season)
            return self._action_report(result, "Temporada ajustada para preparar o combo.", snapshot, plano)
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
            and self._lumps_gastos + 1 + int(self._usar_sugar_frenzy(snapshot)) < self.configuracao.maximo_lumps_total
            and int(snapshot.get("lumps", 0)) > 1 + int(self._usar_sugar_frenzy(snapshot))
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
                f"Spell de alinhamento lançada; faltavam {remaining} magias de preparação.",
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
            f"Aguardando mana máxima; faltam {remaining} magias até a próxima oportunidade.",
            "Sem refill disponível, Haggler's Charm aguarda a barra cheia; com refill disponível, consome a mana antes da recarga.",
            snapshot,
            plano,
        )

    def _preparar_garden(self, snapshot: dict, plano: PlanoCombo):
        # A consulta e a manutenção ficam fora da janela final; o solo não precisa ser lido a cada 0,2 s.
        if not self.configuracao.permitir_converter_garden:
            return None, False
        now = self.relogio()
        if now < self._garden_check_at:
            return None, True
        self._garden_check_at = now + 10
        garden = self.bridge.get_garden_snapshot()
        if not garden.status.available or not {'goldenClover', 'nursetulip'}.issubset(garden.unlocked_seed_keys):
            return None, False
        if garden.frozen:
            # Congelar desativa os efeitos. Preserve uma escolha manual; não descongele sem autorização.
            return None, False
        blocked = tuple((p.x, p.y) for p in garden.plants if
                        p.key not in GARDEN_CATALOG or p.key not in garden.unlocked_seed_keys or
                        (not self.configuracao.permitir_converter_garden and p.key not in {'goldenClover', 'nursetulip'}))
        desired = dict(golden_layout(garden.unlocked_tiles, blocked))
        # Plantas saudáveis deste cultivo não são arrancadas só para redesenhar as faixas.
        desired.update(((p.x, p.y), p.key) for p in garden.plants
                       if (p.x, p.y) not in blocked and p.key in {'goldenClover', 'nursetulip'})
        self._garden_total = len(desired)
        self._garden_maduras = sum(p.mature and desired.get((p.x, p.y)) == p.key for p in garden.plants)
        if not desired:
            return None, False
        soil, effect, peak = golden_soil(garden, desired)
        if garden.soil_key != soil:
            result = self.bridge.change_garden_soil(soil)
            if result.success:
                return self._garden_action_report(result, snapshot, plano), False
            return None, False
        tick = garden.next_tick_at
        if tick is not None and tick == self._garden_tick:
            return None, True
        actions = []
        plants = {(p.x, p.y): p for p in garden.plants}
        for (x, y), seed in desired.items():
            plant = plants.get((x, y))
            if plant and plant.key == seed:
                continue
            if plant:
                actions.append(GardenAction('harvest', 'Conversão do canteiro autorizada.', x=x, y=y,
                                            seed_key=plant.key, require_mature=False))
            actions.append(GardenAction('plant', 'Reposição dos espaços disponíveis para coleta.', x=x, y=y, seed_key=seed))
        if actions:
            # O bridge revalida todas as plantas, sementes e o saldo do lote antes da primeira remoção.
            results = self.bridge.execute_garden_layout(tuple(actions))
            if not results or not all(r.success for r in results):
                return None, False
            self._garden_tick = tick
            planted = sum(a.kind == 'plant' for a in actions)
            return self._report(EstadoCombo.PREPARANDO, f'Garden: {planted} semente(s) plantada(s) em lote.',
                                'Mantendo as plantas produtivas e repondo os espaços disponíveis.', snapshot, plano), False
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
        if self.configuracao.usar_loans:
            if any('interest' in str(buff.get('name', '')).lower() or 'interest' in str(buff.get('type', '')).lower()
                   for buff in buffs if 'loan' in str(buff.get('name', '')).lower() or 'loan' in str(buff.get('type', '')).lower()):
                return False, 'Aguardando terminar os juros dos empréstimos antes da tentativa.'
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
        active = {str(buff.get('type')) for buff in snapshot.get('buffs', ())}
        if self.relogio() >= (self._click_deadline or 0) or not {'blood frenzy', 'click frenzy'}.issubset(active):
            self.desabilitar_clicker()
            if self._residuos_combo:
                result = self.bridge.collect_combo_leftovers(self._residuos_combo)
                if not result.get('ok'):
                    return self._error(result.get('message', 'Não foi possível conferir os biscoitos restantes.'))
                self._residuos_combo = ()
            if self._wizard_towers_originais is not None and int(snapshot.get('wizardTowers', 0)) < self._wizard_towers_originais:
                restored = self.bridge.set_combo_wizard_towers(self._wizard_towers_originais)
                if not restored.get('ok'):
                    if restored.get('waiting'):
                        return self._report(EstadoCombo.PREPARANDO, 'Aguardando saldo livre para recompor as torres.',
                                            'A reserva é preservada; o combo não será repetido antes da recomposição.', snapshot, None)
                    return self._error('Não foi possível restaurar as torres respeitando a reserva de biscoitos.')
            for building_id, amount in tuple(self._rebuild.items()):
                restored = self.bridge.ensure_combo_building_minimum(building_id, amount)
                if not restored.get('ok'):
                    if restored.get('waiting'):
                        return self._report(EstadoCombo.PREPARANDO, 'Aguardando saldo livre para recompor os prédios vendidos.',
                                            'A reserva é preservada; aguardando antes do próximo combo.', snapshot, None)
                    return self._error('Não foi possível confirmar a recomposição dos prédios vendidos.')
                self._rebuild.pop(building_id)
            self._ciclos_concluidos += 1
            self._click_deadline = None
            self._selected_candidate = self._plan_key = self._pause_plan = None
            self._pause_released.clear()
            self._inicio_espera = self.relogio()
            self._busca_armada = False
            self._garden_tick = None
            self._garden_check_at = 0.0
            self._cash_floor = max(self._cash_floor, float(snapshot.get('cookies', 0))*self.configuracao.reserva_caixa_percentual/100)
            return self._report(EstadoCombo.PREPARANDO,
                                f'Combo {self._ciclos_concluidos} concluído. Preparando a próxima tentativa.',
                                'Aguardando mana, recarga e empréstimos disponíveis. O limite de gastos não é reiniciado.', snapshot, None)
        remaining = max(0.0, (self._click_deadline or 0) - self.relogio())
        return self._report(EstadoCombo.CLICANDO, f'Clicker ativo; {remaining:.1f} s de janela útil.',
                            'Aproveitando os bônus antes de preparar outro combo.', snapshot, None)

    def _restore_wizard_towers(self, snapshot: dict) -> None:
        if self._wizard_towers_originais is None:
            return True
        current = int(snapshot.get("wizardTowers", 0))
        if current < self._wizard_towers_originais:
            result = self.bridge.set_combo_wizard_towers(self._wizard_towers_originais)
            if not result.get("ok"):
                logger.warning("Combo: não foi possível restaurar Wizard Towers: %s", result.get("message"))
                return False
        return True

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
            "Conferindo os recursos antes da próxima ação.",
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
            cookies_assados=float(snapshot.get("cookies", 0)),
            ciclos_concluidos=self._ciclos_concluidos,
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
            ciclos_concluidos=self._ciclos_concluidos,
            erro=message,
        )

    def _interrompido(self, message: str) -> RelatorioCombo:
        self.desabilitar_clicker()
        return RelatorioCombo(
            EstadoCombo.INTERROMPIDO,
            message,
            "Nenhuma nova ação será iniciada.",
            lumps_gastos=self._lumps_gastos,
            ciclos_concluidos=self._ciclos_concluidos,
        )
