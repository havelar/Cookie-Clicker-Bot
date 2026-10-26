"""Persistência e atalho do clicker, sem enviar cliques ao jogo."""
import copy
import os
import unittest
from unittest.mock import Mock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication
from app.config.settings import app_config,load_app_settings,save_app_settings
from app.core.run import AutomationRunner
from app.ui.main_window import MainWindow

class ClickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        previous=copy.deepcopy(app_config.__dict__)
        self.addCleanup(lambda:app_config.__dict__.update(previous))
        app_config.mouse_toggle_key='MOUSE4'
        app_config.mouse_click_interval=0.05
        app_config.toggle_key='SCROLLLOCK'
        app_config.click_interval=0.005
        app_config.clicker_mode=app_config.mouse_clicker_mode='toggle'
    def run_loop(self,keys,*,active=False,interval=0.005,on_wait=None):
        with patch('app.core.run.InputHandler'):
            runner=AutomationRunner(0,Mock())
        runner.is_running=active
        app_config.click_interval=interval
        times=[]
        class Event:
            index=0
            clock=0.0
            def is_set(self):return self.index>=len(keys)
            def wait(self,delay):
                self.clock+=delay
                self.index+=1
                if on_wait:on_wait(self.index)
        event=Event();runner.stop_event=event
        runner.input_handler.is_key_pressed.side_effect=lambda key:keys[event.index] if key==app_config.toggle_key else False
        runner.input_handler.click_cookie.side_effect=lambda:times.append(event.clock)
        def toggle():runner.is_running=not runner.is_running
        runner.toggle_clicker=Mock(side_effect=toggle)
        with patch('app.core.run.time.monotonic',side_effect=lambda:event.clock):
            runner.clicker_loop()
        return runner,times
    def test_holding_hotkey_only_toggles_once_per_press(self):
        runner,_=self.run_loop([True]*100+[False,True])
        self.assertEqual(runner.toggle_clicker.call_count,2)
    def test_hotkey_responds_between_slow_clicks(self):
        runner,times=self.run_loop([True,True,False,True],interval=1.0)
        self.assertEqual(runner.toggle_clicker.call_count,2)
        self.assertEqual(len(times),1)
    def test_changed_hotkey_held_does_not_toggle_until_new_press(self):
        def change(index):
            if index==1:app_config.toggle_key='F8'
        runner,_=self.run_loop([True,True,True,False,True],on_wait=change)
        self.assertEqual(runner.toggle_clicker.call_count,2)
        self.assertTrue(any(c.args==('F8',) for c in runner.input_handler.is_key_pressed.call_args_list))
    def test_click_speed_respects_interval_and_polls_hotkey(self):
        runner,times=self.run_loop([False]*102,active=True,interval=1.0)
        self.assertEqual(len(times),2)
        self.assertGreaterEqual(times[1]-times[0],1.0)
        self.assertEqual(runner.input_handler.is_key_pressed.call_count,204)
    def test_settings_persist_and_reject_invalid_hotkey(self):
        values={}
        class Settings:
            def __init__(self,*args):pass
            def beginGroup(self,*args):pass
            def endGroup(self):pass
            def sync(self):pass
            def setValue(self,k,v):values[k]=v
            def value(self,k,default=None,type=None):return values.get(k,default)
        with patch('app.config.settings.QSettings',Settings):
            app_config.toggle_key='F8';app_config.click_interval=1/40
            app_config.mouse_toggle_key='MOUSE5';app_config.mouse_click_interval=1/30
            app_config.clicker_mode='hold';app_config.mouse_clicker_mode='toggle'
            save_app_settings()
            app_config.toggle_key='SCROLLLOCK';app_config.click_interval=0.005
            app_config.mouse_toggle_key='MOUSE4';app_config.mouse_click_interval=0.05
            load_app_settings()
            self.assertEqual(app_config.toggle_key,'F8')
            self.assertEqual(app_config.click_interval,1/40)
            self.assertEqual(app_config.mouse_toggle_key,'MOUSE5')
            self.assertEqual(app_config.mouse_click_interval,1/30)
            self.assertEqual(app_config.clicker_mode,'hold')
            self.assertEqual(app_config.mouse_clicker_mode,'toggle')
            values['clicker_mode']='unknown'
            values['toggle_key']='unknown';values['click_interval']=0
            load_app_settings()
            self.assertEqual(app_config.toggle_key,'SCROLLLOCK')
            self.assertEqual(app_config.click_interval,0.001)
            self.assertEqual(app_config.clicker_mode,'toggle')
    def test_ui_controls_update_live_config_and_clicker_state(self):
        with patch('app.ui.main_window.save_app_settings') as save:
            window=MainWindow()
            try:
                self.assertTrue(window.clicker_group.isAncestorOf(window.clicker_button))
                self.assertFalse(window.clicker_button.isEnabled())
                window.clicker_hotkey_input.set_key('F8')
                window.clicker_hotkey_input.changed.emit('F8')
                window.clicker_speed_input.setValue(40)
                self.assertEqual(app_config.toggle_key,'F8')
                self.assertEqual(app_config.click_interval,1/40)
                self.assertEqual(save.call_count,2)
                window.set_clicker_state(True)
                self.assertEqual(window.clicker_button.text(),'Desligar')
                self.assertTrue(window.clicker_button.isChecked())
                self.assertEqual(window.clicker_run_status.text(),'Clicando')
                window.set_clicker_state(False)
                self.assertEqual(window.clicker_button.text(),'Ligar')
                self.assertFalse(window.clicker_button.isChecked())
            finally:window.close()

class MouseClickerTests(unittest.TestCase):
    setUp = ClickerTests.setUp
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_two_clickers_send_both_actions_in_order(self):
        with patch('app.core.run.InputHandler'):
            runner=AutomationRunner(0,Mock())
        runner.is_running=runner.mouse_clicker_running=True
        runner.input_handler.is_key_pressed.return_value=False
        events=[]
        runner.input_handler.click_cookie.side_effect=lambda:events.append('cookie')
        runner.input_handler.click_at_cursor.side_effect=lambda:events.append('mouse') or True
        class Event:
            count=0
            clock=0
            def is_set(self):return self.count>=40
            def wait(self,delay):self.count+=1;self.clock+=delay
        event=Event();runner.stop_event=event
        with patch('app.core.run.time.monotonic',side_effect=lambda:event.clock):runner.clicker_loop()
        self.assertEqual(events[:2],['cookie','mouse'])
        self.assertGreater(events.count('cookie'),events.count('mouse'))
        self.assertGreater(runner.mouse_clicks,0)
    def test_pause_exclusive_and_capture_block_mouse(self):
        with patch('app.core.run.InputHandler'):
            runner=AutomationRunner(0,Mock())
        runner.toggle_mouse_clicker();self.assertTrue(runner.mouse_clicker_running)
        runner.set_paused(True)
        self.assertFalse(runner.mouse_clicker_running)
        self.assertFalse(runner.toggle_mouse_clicker())
        runner.set_paused(False);runner.acquire_exclusive('backup_restore')
        self.assertFalse(runner.toggle_mouse_clicker())
    def test_capture_suspends_all_clicks_and_toggles(self):
        with patch('app.core.run.InputHandler'):
            runner=AutomationRunner(0,Mock())
        runner.hotkey_capture_active.set()
        runner.is_running=runner.mouse_clicker_running=True
        runner.input_handler.is_key_pressed.return_value=True
        runner.toggle_clicker=Mock();runner.toggle_mouse_clicker=Mock()
        class Event:
            count=0
            def is_set(self):return self.count>=4
            def wait(self,delay):self.count+=1
        runner.stop_event=Event();runner.clicker_loop()
        runner.input_handler.click_cookie.assert_not_called()
        runner.input_handler.click_at_cursor.assert_not_called()
        runner.toggle_clicker.assert_not_called();runner.toggle_mouse_clicker.assert_not_called()
    def test_native_cursor_click_guard_and_coordinate_conversion(self):
        from app.automation.input import InputHandler
        handler=InputHandler.__new__(InputHandler);handler.hwnd=10;handler.click=Mock(return_value=True)
        with patch('app.automation.input.win32gui.IsWindow',return_value=True),             patch('app.automation.input.win32gui.IsIconic',return_value=False),             patch('app.automation.input.win32api.GetCursorPos',return_value=(150,200)),             patch('app.automation.input.win32gui.WindowFromPoint',return_value=11) as under,             patch('app.automation.input.win32gui.GetAncestor',side_effect=lambda hwnd,flag:10 if hwnd in (10,11) else 20),             patch('app.automation.input.win32gui.ScreenToClient',return_value=(50,80)),             patch('app.automation.input.win32gui.GetClientRect',return_value=(0,0,800,600)):
            self.assertTrue(handler.click_at_cursor())
            handler.click.assert_called_once_with(50,80)
            handler.click.reset_mock();under.return_value=20
            self.assertFalse(handler.click_at_cursor());handler.click.assert_not_called()
    def test_duplicate_hotkey_is_rejected_and_mouse_settings_save(self):
        with patch('app.ui.main_window.save_app_settings') as save:
            window=MainWindow()
            try:
                window.mouse_clicker_hotkey_input.set_key('SCROLLLOCK')
                window.mouse_clicker_hotkey_input.changed.emit('SCROLLLOCK')
                self.assertEqual(app_config.mouse_toggle_key,'MOUSE4')
                self.assertEqual(window.mouse_clicker_hotkey_input.key,'MOUSE4')
                save.assert_not_called()
                window.mouse_clicker_hotkey_input.set_key('MOUSE5')
                window.mouse_clicker_hotkey_input.changed.emit('MOUSE5')
                window.mouse_clicker_speed_input.setValue(30)
                self.assertEqual(app_config.mouse_toggle_key,'MOUSE5')
                self.assertAlmostEqual(app_config.mouse_click_interval,1/30)
            finally:window.close()

class HoldClickerTests(unittest.TestCase):
    setUp = ClickerTests.setUp
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def simulate(self, frames, *, cookie_mode='hold', mouse_mode='hold', automatic=False, on_frame=None):
        app_config.clicker_mode=cookie_mode;app_config.mouse_clicker_mode=mouse_mode
        with patch('app.core.run.InputHandler'):
            runner=AutomationRunner(0,Mock())
        runner.cookie_position=(10,10)
        runner.bridge.get_cookie_position.return_value={"x":10,"y":10}
        runner.is_running=automatic
        actions=[]
        class Event:
            index=0
            clock=0.0
            def is_set(self):return self.index>=len(frames)
            def wait(self,delay):
                self.index+=1;self.clock+=delay
                if on_frame:on_frame(runner,self.index)
        event=Event();runner.stop_event=event
        runner.input_handler.is_key_pressed.side_effect=lambda key:frames[event.index][0 if key==app_config.toggle_key else 1]
        runner.input_handler.click_cookie.side_effect=lambda:actions.append(('cookie',event.index))
        runner.input_handler.click_at_cursor.side_effect=lambda:actions.append(('mouse',event.index)) or True
        with patch('app.core.run.time.monotonic',side_effect=lambda:event.clock):runner.clicker_loop()
        return runner,actions

    def test_both_hold_click_only_while_pressed_and_stop_on_release(self):
        runner,actions=self.simulate([(True,True)]*15+[(False,False)]*15)
        self.assertEqual({name for name,index in actions},{'cookie','mouse'})
        self.assertTrue(all(index<15 for name,index in actions))
        self.assertFalse(runner.cookie_hold_active or runner.mouse_hold_active)
        self.assertFalse(runner.is_running or runner.mouse_clicker_running)

    def test_toggle_cookie_and_hold_mouse_work_independently(self):
        runner,actions=self.simulate([(True,True)]+[(False,True)]*15+[(False,False)]*15,cookie_mode='toggle')
        self.assertTrue(runner.is_running)
        self.assertTrue(any(name=='cookie' and index>=16 for name,index in actions))
        self.assertFalse(any(name=='mouse' and index>=16 for name,index in actions))

    def test_release_does_not_stop_automation_cookie_clicks(self):
        runner,actions=self.simulate([(True,False)]*10+[(False,False)]*10,automatic=True)
        self.assertTrue(runner.is_running)
        self.assertTrue(any(index>=10 for name,index in actions))

    def test_pause_capture_and_exclusive_require_a_new_press(self):
        for blocker in ('pause','capture','exclusive'):
            def change(runner,index):
                if blocker=='pause' and index in (2,4):runner.set_paused(index==2)
                if blocker=='capture':
                    if index==2:runner.hotkey_capture_active.set()
                    if index==4:runner.hotkey_capture_active.clear()
                if blocker=='exclusive':
                    if index==2:runner.acquire_exclusive('backup_restore')
                    if index==4:runner.release_exclusive('backup_restore')
            with self.subTest(blocker=blocker):
                _,actions=self.simulate([(True,True)]*8+[(False,False),(True,True)],on_frame=change)
                self.assertFalse(any(2<=index<9 for name,index in actions))
                self.assertTrue(any(index==9 for name,index in actions))

    def test_switch_mode_while_pressed_waits_until_release(self):
        def change(runner,index):
            if index==2:
                app_config.clicker_mode='hold'
                runner.reset_manual_clicker()
        _,actions=self.simulate([(True,False)]*8+[(False,False),(True,False)],cookie_mode='toggle',on_frame=change)
        self.assertFalse(any(2<=index<9 for name,index in actions))
        self.assertTrue(any(index==9 for name,index in actions))

    def test_hold_ui_and_mode_change_preserve_simple_farm(self):
        with patch('app.ui.main_window.save_app_settings') as save,patch('app.core.run.InputHandler'):
            runner=AutomationRunner(0,Mock());runner.cookie_position=(10,10)
            runner.bridge.get_cookie_position.return_value={"x":10,"y":10}
            runner.acquire_simple_farm();runner.set_simple_farm_clicker(True)
            window=MainWindow();window.runner=runner;window._bot_enabled=True
            try:
                window.clicker_mode_input.setCurrentIndex(1)
                window.mouse_clicker_mode_input.setCurrentIndex(1)
                self.assertTrue(runner.is_running)
                self.assertFalse(runner._simple_farm_manual_clicker)
                self.assertEqual(window.clicker_button.text(),'Segure o atalho')
                self.assertFalse(window.clicker_button.isEnabled())
                self.assertEqual(window.mouse_clicker_run_status.text(),'Aguardando atalho')
                runner.mouse_hold_active=True;runner.mouse_clicker_over_game=True
                window.refresh_clicker_states()
                self.assertEqual(window.mouse_clicker_run_status.text(),'Clicando')
                window.clicker_mode_input.setCurrentIndex(0)
                self.assertTrue(window.clicker_button.isEnabled())
                self.assertEqual(save.call_count,3)
            finally:window.runner=None;window.close()

class HotkeyCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_side_button_detected_and_waits_for_release(self):
        from app.ui.hotkey_capture import HotkeyCapture
        widget=HotkeyCapture('F8');changed=Mock();widget.changed.connect(changed)
        with patch.object(widget,'pressed_keys',return_value=set()) as keys:
            widget.toggle_capture()
            keys.return_value={'MOUSE5'};widget.poll()
            changed.assert_called_once_with('MOUSE5')
            self.assertEqual(widget.value_label.text(),'Lateral 2')
            self.assertTrue(widget.is_capturing)
            widget.wait_release();self.assertTrue(widget.is_capturing)
            keys.return_value=set();widget.wait_release()
            self.assertFalse(widget.is_capturing)
        widget.close()
    def test_held_key_is_ignored_and_escape_cancels(self):
        from app.ui.hotkey_capture import HotkeyCapture
        widget=HotkeyCapture('F8');changed=Mock();widget.changed.connect(changed)
        with patch.object(widget,'pressed_keys',return_value={'MOUSE4'}) as keys:
            widget.toggle_capture();widget.poll();changed.assert_not_called()
            keys.return_value=set();widget.poll()
            keys.return_value={'ESC'};widget.poll()
            self.assertFalse(widget.is_capturing);self.assertEqual(widget.key,'F8')
            changed.assert_not_called()
        widget.close()
