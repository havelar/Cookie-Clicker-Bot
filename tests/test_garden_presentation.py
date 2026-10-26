"""Clareza do resumo e layout de mensagens longas no Garden."""
import os
import unittest
from dataclasses import replace
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication
from app.models.garden import GardenAction, GardenActionResult, GardenCycleResult, GardenGoal, GardenPlan, GardenPlant
from app.ui.garden_presentation import grouped_actions, pending_actions, current_state
from app.ui.main_window import MainWindow
from app.ui.theme import DARK_STYLESHEET
from tests.test_garden import snapshot


class GardenPresentationTests(unittest.TestCase):
    def goal(self):
        return GardenGoal('thumbcorn','Thumbcorn',('bakerWheat',),("2× Baker's wheat",),
                          'Buscar a próxima semente.',(), 'Colher madura.', 'mutacao_adjacente')

    def test_repeated_plantings_become_one_line_without_positions_or_reasons(self):
        actions = tuple(GardenAction('plant','Motivo repetido',x=x,y=1,seed_key='bakerWheat') for x in range(6))
        text = grouped_actions(actions)
        self.assertEqual(text, "• Plantar 6× Baker's wheat")
        self.assertNotIn('Motivo', text)
        self.assertNotIn('(0,', text)

    def test_confirmed_actions_leave_the_next_actions_but_failed_ones_remain(self):
        actions = (GardenAction('plant','',x=0,y=1,seed_key='bakerWheat'),
                   GardenAction('plant','',x=1,y=1,seed_key='bakerWheat'))
        results = (GardenActionResult(True,'plant','Feito',x=0,y=1,seed_key='bakerWheat'),
                   GardenActionResult(False,'plant','Aguardar',x=1,y=1,seed_key='bakerWheat'))
        self.assertEqual(pending_actions(GardenPlan(self.goal(),actions),results), (actions[1],))

    def test_waiting_for_planting_reports_time_instead_of_technical_layout(self):
        plan = GardenPlan(self.goal(), explanation='Layout técnico. Sincronizar os pais: aguardar para plantar Baker\'s wheat em ~12 min com o solo atual. Estimativa recalculada a cada leitura.')
        state, detail = current_state(snapshot({'bakerWheat'}), plan)
        self.assertEqual(state, 'Alinhando a maturação dos pais')
        self.assertIn('12 min', detail)
        self.assertNotIn('Layout técnico', detail)

    def test_mature_parents_must_be_adjacent_to_a_free_space(self):
        plants = (GardenPlant(0,0,0,'bakerWheat',"Baker's wheat",60,50,True),
                  GardenPlant(5,5,0,'bakerWheat',"Baker's wheat",60,50,True))
        current = snapshot({'bakerWheat'},plants,tiles=tuple((x,y) for y in range(6) for x in range(6)))
        state,_ = current_state(current,GardenPlan(self.goal()))
        self.assertNotEqual(state, 'Esperando a mutação aparecer')
        current = replace(current,plants=(plants[0],replace(plants[1],x=1,y=0)))
        self.assertEqual(current_state(current,GardenPlan(self.goal()))[0], 'Esperando a mutação aparecer')


class GardenPresentationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=MainWindow()
        self.window.setStyleSheet(DARK_STYLESHEET)
        self.window.tabs.setCurrentIndex(next(i for i in range(self.window.tabs.count()) if self.window.tabs.tabText(i)=='Garden'))
        self.addCleanup(self.window.close)

    def test_large_result_is_short_green_summary_with_complete_details(self):
        actions=tuple(GardenAction('plant','Explicação completa '*20,x=x,y=y,seed_key='bakerWheat')
                      for y in range(6) for x in range(6))
        results=tuple(GardenActionResult(True,'plant',f'Plantio confirmado em ({a.x}, {a.y}). '+a.reason,
                                        x=a.x,y=a.y,seed_key=a.seed_key) for a in actions)
        goal=GardenPresentationTests().goal()
        self.window._display_garden_result(GardenCycleResult(snapshot({'bakerWheat'}),GardenPlan(goal,actions),False,results))
        self.assertEqual(self.window.garden_feedback_label.text(), "Plantou 36× Baker's wheat")
        self.assertIn(results[-1].message,self.window.garden_details_text.toPlainText())
        self.assertNotIn('Plantar 36',self.window.garden_plan_text.toPlainText())
        self.assertTrue(self.window.garden_details_text.isHidden())
        for width,height in ((860,660),(600,520)):
            with self.subTest(width=width):
                self.window.resize(width,height);self.window.show();self.qt.processEvents()
                content=self.window.garden_scroll.widget()
                bottom=self.window.garden_feedback_label.mapTo(content,QPoint(0,self.window.garden_feedback_label.height())).y()
                top=self.window.garden_plan_group.mapTo(content,QPoint(0,0)).y()
                self.assertLessEqual(bottom,top)
        self.window.garden_details_toggle.setChecked(True);self.qt.processEvents()
        self.assertFalse(self.window.garden_details_text.isHidden())
        self.assertGreater(self.window.garden_scroll.verticalScrollBar().maximum(),0)

    def test_manual_long_feedback_is_bounded_and_full_message_is_accessible(self):
        message='Não foi possível concluir: '+('texto longo '*100)
        self.window._show_garden_feedback(False,message)
        self.assertLessEqual(len(self.window.garden_feedback_label.text()),150)
        self.assertEqual(self.window.garden_feedback_label.toolTip(),message)
        self.assertIn(message,self.window.garden_details_text.toPlainText())

    def test_unchanged_reports_keep_the_details_scroll_position(self):
        text='\n'.join(str(i) for i in range(300))
        self.window.garden_details_toggle.setChecked(True)
        self.window.show();self.qt.processEvents()
        self.window._set_garden_report_text(self.window.garden_details_text,text)
        self.window.garden_details_text.verticalScrollBar().setValue(100)
        self.window._set_garden_report_text(self.window.garden_details_text,text)
        self.assertEqual(self.window.garden_details_text.verticalScrollBar().value(),100)
