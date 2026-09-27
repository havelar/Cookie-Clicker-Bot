"""Valida edição isolada e prioridades dos limites por ativo."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialog

from app.models.stock_market import StockAsset, StockMarketSnapshot, StockMarketStatus
from app.ui.stock_limits_dialog import StockLimitsDialog


class StockLimitsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        cereals = StockAsset(0, "Cereals", "CRL", 12.0, 0, 100)
        chocolate = StockAsset(1, "Chocolate", "CHC", 25.0, 0, 100)
        # The UI also accepts older snapshots where reference data is unavailable.
        object.__setattr__(cereals, "resting_value", 10.0)
        object.__setattr__(chocolate, "resting_value", 20.0)
        unknown = StockAsset(2, "Unknown", None, 10.0, 0, 100)
        self.snapshot = StockMarketSnapshot(
            StockMarketStatus(True, True, "disponível"),
            assets=(cereals, chocolate, unknown),
        )
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        self.app.processEvents()

    def dialog(self, overrides=None, use_reference=True, **kwargs):
        dialog = StockLimitsDialog(
            self.snapshot, overrides or {}, use_reference, **kwargs
        )
        self.dialogs.append(dialog)
        return dialog

    @staticmethod
    def limits(dialog, row):
        return tuple(dialog.table.cellWidget(row, column).value() for column in (2, 3))

    def test_suggestions_use_reference_and_fallback_without_freezing_defaults(self):
        dialog = self.dialog(buy_limit=18.0, sell_limit=75.0)

        self.assertFalse(hasattr(dialog, "discount_checkbox"))
        self.assertEqual(self.limits(dialog, 0), (5.0, 10.0))
        self.assertEqual(self.limits(dialog, 1), (10.0, 20.0))
        self.assertEqual(self.limits(dialog, 2), (18.0, 75.0))
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.overrides, {})

    def test_cancel_does_not_modify_original_or_published_results(self):
        source = {"0": {"buy": 3.0, "sell": 15.0}}
        dialog = self.dialog(source)
        dialog.table.cellWidget(0, 2).setValue(4.0)
        dialog.reject()

        self.assertEqual(source, {"0": {"buy": 3.0, "sell": 15.0}})
        self.assertEqual(dialog.overrides, source)

    def test_edit_only_overrides_edited_asset_and_preserves_unlisted_assets(self):
        source = {"9": {"buy": 40.0, "sell": 120.0}}
        dialog = self.dialog(source)
        dialog.table.cellWidget(1, 2).setValue(8.0)
        dialog.accept()

        self.assertEqual(dialog.overrides, {
            "1": {"buy": 8.0, "sell": 20.0},
            "9": {"buy": 40.0, "sell": 120.0},
        })
        self.assertEqual(source, {"9": {"buy": 40.0, "sell": 120.0}})

    def test_switching_reference_preserves_explicit_limits(self):
        dialog = self.dialog({"0": {"buy": 4.0, "sell": 16.0}})
        dialog.reference_checkbox.setChecked(False)

        self.assertEqual(self.limits(dialog, 0), (4.0, 16.0))
        self.assertEqual(self.limits(dialog, 1), (20.0, 80.0))
        dialog.accept()
        self.assertFalse(dialog.use_reference_prices)
        self.assertEqual(dialog.overrides, {"0": {"buy": 4.0, "sell": 16.0}})

    def test_restore_suggestions_clears_overrides_and_enables_reference(self):
        dialog = self.dialog(
            {"0": {"buy": 4.0, "sell": 16.0}, "9": {"buy": 40.0, "sell": 120.0}},
            use_reference=False,
        )
        dialog.restore_button.click()
        self.assertEqual(self.limits(dialog, 0), (5.0, 10.0))
        self.assertEqual(self.limits(dialog, 2), (20.0, 80.0))
        dialog.accept()

        self.assertTrue(dialog.use_reference_prices)
        self.assertEqual(dialog.overrides, {})

    def test_reverting_an_edit_to_suggestions_removes_override(self):
        dialog = self.dialog({"0": {"buy": 4.0, "sell": 16.0}})
        dialog.table.cellWidget(0, 2).setValue(5.0)
        dialog.table.cellWidget(0, 3).setValue(10.0)
        dialog.accept()
        self.assertEqual(dialog.overrides, {})

    def test_invalid_limits_do_not_publish_edits(self):
        for buy, sell in ((0.0, 10.0), (10.0, 10.0), (11.0, 10.0)):
            with self.subTest(buy=buy, sell=sell):
                dialog = self.dialog()
                dialog.table.cellWidget(0, 2).setValue(buy)
                dialog.table.cellWidget(0, 3).setValue(sell)
                with patch("app.ui.stock_limits_dialog.QMessageBox.warning") as warning:
                    dialog.accept()
                warning.assert_called_once()
                self.assertEqual(dialog.result(), QDialog.Rejected)
                self.assertEqual(dialog.overrides, {})


if __name__ == "__main__":
    unittest.main()
