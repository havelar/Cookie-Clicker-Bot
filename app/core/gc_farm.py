"""Preparo do farm de dourados e medição pelo contador oficial da conquista."""
import math
import time
from collections import deque

from app.core.fazendeira import Fazendeira


class GCFarm:
    TARGET = 27_777

    def __init__(self, bridge, reserve_percent=80, clock=time.monotonic, should_stop=lambda: False,
                 manual_last_click=lambda: False):
        if (isinstance(reserve_percent, bool) or not isinstance(reserve_percent, (int, float))
                or not math.isfinite(reserve_percent) or not 0 <= reserve_percent <= 99):
            raise ValueError('Reserva deve ficar entre 0 e 99%.')
        self.bridge = bridge
        self.reserve_percent = reserve_percent
        self.clock = clock
        self.should_stop = should_stop
        self.manual_last_click = manual_last_click
        self.started = None
        self.initial = None
        self.seed = None
        self.samples = deque()
        self.next_garden = 0
        self.garden_tick = None
        self.garden_message = 'Aguardando a primeira leitura do Garden.'
        self.farmer = Fazendeira(bridge)

    def step(self):
        if self.should_stop():
            return dict(terminal=True, message='Farm desligado.')
        state = self.bridge.get_gc_farm_snapshot()
        count = state.get('count')
        if (not state.get('available') or isinstance(count, bool) or not isinstance(count, int) or count < 0
                or not state.get('seed')):
            return dict(terminal=True, message=state.get('message') or 'Dados da conquista inválidos.')
        now = self.clock()
        if self.started is None:
            self.started, self.initial, self.seed = now, count, state['seed']
        if state['seed'] != self.seed or (self.samples and count < self.samples[-1][1]):
            return dict(terminal=True, message='O save ou o contador mudou; inicie uma nova sessão.')
        self.samples.append((now, count))
        # Uma hora móvel; preserva a amostra anterior ao limite para evitar saltos.
        while len(self.samples) > 2 and self.samples[1][0] <= now - 3600:
            self.samples.popleft()
        elapsed = now - self.samples[0][0]
        gained = count - self.samples[0][1]
        rate = gained * 3600 / elapsed if elapsed > 0 else 0
        remaining = max(0, self.TARGET - count)
        completed = count >= self.TARGET or state.get('completed') is True
        report = dict(count=count, remaining=remaining, gained=count-self.initial, rate=rate,
                      waiting_manual=count == self.TARGET-1 and self.manual_last_click(),
                      elapsed=now-self.started, eta=remaining/rate*3600 if rate > 0 else None,
                      terminal=completed, completed=completed, garden=self.garden_message,
                      message='Conquista concluída!' if completed else 'Coletando dourados.')
        if completed or self.should_stop():
            return report
        if state.get('chain'):
            report['message'] = 'Corrente em andamento; priorizando a coleta.'
            return report
        setup = self.bridge.prepare_gc_farm(self.reserve_percent, self.seed)
        report['message'] = setup.get('message') or 'Mantendo a configuração de coleta.'
        if not setup.get('ok') and setup.get('changed'):
            report['message'] = 'O jogo não confirmou a ação: ' + report['message']
        if setup.get('chain') or setup.get('completed'):
            return report
        if not self.should_stop() and now >= self.next_garden:
            self.next_garden = now + 10
            self.garden_message = self._garden()
        report['garden'] = self.garden_message
        return report

    def _garden(self):
        garden = self.bridge.get_garden_snapshot()
        if not garden.status.available:
            return garden.status.message
        if garden.game_seed != self.seed:
            return 'Garden de outro save; nenhuma alteração enviada.'
        plan = self.farmer.build_plan(garden, strategy='golden_cookies')
        if self.should_stop():
            return 'Manutenção do Garden interrompida.'
        # Uma manutenção por tick, com todo o lote validado no próprio jogo.
        if garden.next_tick_at is not None and garden.next_tick_at == self.garden_tick:
            return plan.explanation
        for action in plan.actions:
            if action.kind == 'set_freeze':
                return self.bridge.set_garden_frozen(False).message
            if action.kind == 'change_soil':
                return self.bridge.change_garden_soil(action.soil_key).message
        layout = tuple(a for a in plan.actions if a.kind in ('plant', 'harvest'))
        if layout:
            balance = garden.cookies
            if balance is None or not math.isfinite(balance) or balance < 0:
                return 'Saldo indisponível; plantas preservadas.'
            results = self.bridge.execute_garden_layout(layout, cash_floor=balance*self.reserve_percent/100)
            if not results:
                return 'Plantio não confirmado; aguardando nova leitura.'
            if all(r.success for r in results):
                self.garden_tick = garden.next_tick_at
                return 'Canteiro de trevos e tulipas atualizado.'
            return next(r.message for r in results if not r.success)
        return plan.explanation
