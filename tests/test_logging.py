"""Logs úteis sem esconder novas falhas, ações ou resultados finais."""
import logging
import os
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from app.utils.logger import RepeatedProblemFilter, ActivitySummary, logger, add_ui_handler
from app.ui.main_window import MainWindow
from app.core.save_scum import SaveScumReport

class LogPolicyTests(unittest.TestCase):
    def record(self, message, level=logging.WARNING, line=10):
        return logging.LogRecord('test', level, 'poll.py', line, message, (), None)

    def test_repeated_problem_is_summarized_and_new_problem_immediate(self):
        now = [0.0]
        filt = RepeatedProblemFilter(clock=lambda: now[0])
        self.assertTrue(filt.filter(self.record('Bridge desconectada')))
        self.assertFalse(filt.filter(self.record('Bridge desconectada')))
        self.assertTrue(filt.filter(self.record('Garden sem conexão')))
        self.assertFalse(filt.filter(self.record('Bridge desconectada')))
        now[0] = 30.0
        repeated = self.record('Bridge desconectada')
        self.assertTrue(filt.filter(repeated))
        self.assertIn('mais 2 ocorrência(s)', repeated.getMessage())
        for _ in range(3):
            self.assertTrue(filt.filter(self.record('Comprou 10 prédios', logging.INFO)))

    def test_repeated_problem_memory_is_bounded(self):
        filt = RepeatedProblemFilter(capacity=3)
        for i in range(20):
            self.assertTrue(filt.filter(self.record(str(i))))
        self.assertEqual(len(filt.entries), 3)

    def test_collection_summary_keeps_counts_and_flushes_on_pause(self):
        now = [0.0]; output = Mock()
        summary = ActivitySummary(output, clock=lambda: now[0])
        summary.record('Golden Cookies'); summary.record('Golden Cookies')
        output.info.assert_not_called()
        now[0] = 60
        summary.record('Renas')
        self.assertEqual(output.info.call_args.args[1], '2 Golden Cookies, 1 Renas')
        summary.record('Wrinklers'); summary.flush()
        self.assertEqual(output.info.call_args.args[1], '1 Wrinklers')
        summary.flush()
        self.assertEqual(output.info.call_count, 2)

    def test_window_detection_is_only_diagnostic(self):
        from app.core.window_finder import find_cookie_window
        with patch('app.core.window_finder.win32gui.EnumWindows'), patch('app.core.window_finder.logger') as log:
            self.assertIsNone(find_cookie_window())
            log.info.assert_not_called(); log.warning.assert_not_called()

class LogUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.close)

    def test_ui_handler_is_replaced_instead_of_duplicated(self):
        original = list(logger.handlers)
        try:
            add_ui_handler(self.window.log_emitter)
            add_ui_handler(self.window.log_emitter)
            self.assertEqual(sum(hasattr(h, 'emitter') for h in logger.handlers), 1)
        finally:
            for h in list(logger.handlers):
                if h not in original:
                    logger.removeHandler(h); h.close()
            for h in original:
                if h not in logger.handlers: logger.addHandler(h)

    def test_log_text_is_literal_and_does_not_force_scroll_to_bottom(self):
        self.window.show(); self.window.tabs.setCurrentIndex(next(i for i in range(self.window.tabs.count()) if self.window.tabs.tabText(i) == 'Atividade'))
        for i in range(80): self.window.add_log(f'12:00:00 - INFO - Linha {i}')
        self.app.processEvents()
        scrollbar = self.window.log_text.verticalScrollBar()
        scrollbar.setValue(0)
        self.window.add_log('12:00:00 - WARNING - Saldo < mínimo; <b>texto literal</b>')
        self.assertEqual(scrollbar.value(), 0)
        self.assertIn('<b>texto literal</b>', self.window.log_text.toPlainText())

    def test_save_scum_throttles_attempts_but_logs_final_result_once(self):
        tab = self.window.save_scum_tab
        with patch('app.ui.save_scum_tab.time.monotonic', side_effect=[10, 11, 15, 16, 17]), patch('app.ui.save_scum_tab.logger') as log:
            tab.display(SaveScumReport('rodando', 'Iniciando', 0))
            tab.display(SaveScumReport('rodando', 'Tentativa 1', 1))
            self.assertIn('Tentativas: 1', tab.status.text())
            self.assertEqual(log.info.call_count, 1)
            tab.display(SaveScumReport('rodando', 'Tentativa 20', 20))
            final = SaveScumReport('alvo encontrado', 'Dourado encontrado', 21)
            tab.display(final); tab.display(final)
            self.assertEqual(log.info.call_count, 3)
            self.assertEqual(tab.logs.document().blockCount(), 3)
