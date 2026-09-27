"""Configuração dos limites por ativo, sem alterar o mercado ou as preferências."""
from copy import deepcopy
from math import isfinite
from typing import Dict, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.models.stock_market import StockAsset, StockMarketSnapshot


class StockLimitsDialog(QDialog):
    """Edita uma cópia dos limites; os resultados são publicados ao aceitar."""

    def __init__(
        self,
        snapshot: StockMarketSnapshot,
        overrides: Dict[str, Dict[str, float]],
        use_reference_prices: bool,
        parent=None,
        *,
        buy_limit: float = 20.0,
        sell_limit: float = 80.0,
    ):
        super().__init__(parent)
        self.overrides = deepcopy(overrides)
        self.use_reference_prices = bool(use_reference_prices)
        self._draft_overrides = deepcopy(overrides)
        self._assets = {str(asset.asset_id): asset for asset in snapshot.assets}
        self._fallback_limits = (float(buy_limit), float(sell_limit))
        self._inputs: Dict[str, Tuple[QDoubleSpinBox, QDoubleSpinBox]] = {}

        self.setWindowTitle("Limites por ativo")
        self.resize(660, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.reference_checkbox = QCheckBox(
            "Limites pela referência (compra 50%, venda 100%)"
        )
        self.reference_checkbox.setChecked(self.use_reference_prices)
        self.reference_checkbox.setToolTip(
            "Sugestão inicial: comprar abaixo de metade da referência e iniciar "
            "o modo de venda na referência. Ela não garante recuperação do preço. "
            "Limites personalizados têm prioridade; sem referência, valem os limites gerais."
        )
        layout.addWidget(self.reference_checkbox)

        self.table = QTableWidget(len(snapshot.assets), 4)
        self.table.setHorizontalHeaderLabels(
            ["Ativo", "Referência", "Comprar < $", "Modo venda ≥ $"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        for row, asset in enumerate(snapshot.assets):
            key = str(asset.asset_id)
            label = f"{asset.name} ({asset.symbol})" if asset.symbol else asset.name
            self.table.setItem(row, 0, QTableWidgetItem(label))
            reference = self._reference(asset)
            reference_item = QTableWidgetItem(
                f"${reference:.2f}" if reference is not None else "—"
            )
            reference_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            reference_item.setToolTip(
                "Referência do jogo para este ativo; não é um preço garantido."
            )
            self.table.setItem(row, 1, reference_item)
            buy_input, sell_input = self._price_input(), self._price_input()
            self._inputs[key] = (buy_input, sell_input)
            self.table.setCellWidget(row, 2, buy_input)
            self.table.setCellWidget(row, 3, sell_input)
            buy_input.valueChanged.connect(
                lambda _value, asset_key=key: self._record_override(asset_key)
            )
            sell_input.valueChanged.connect(
                lambda _value, asset_key=key: self._record_override(asset_key)
            )
        layout.addWidget(self.table, 1)

        hint = QLabel("Edite os valores para personalizar cada ativo.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Salvar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        self.restore_button = QPushButton("Restaurar sugestões")
        buttons.addButton(self.restore_button, QDialogButtonBox.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.restore_button.clicked.connect(self._restore_suggestions)
        layout.addWidget(buttons)
        self.reference_checkbox.toggled.connect(self._refresh_inputs)
        self._refresh_inputs()

    @staticmethod
    def _price_input() -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setDecimals(2)
        control.setRange(0.0, 1_000_000_000.0)
        control.setButtonSymbols(QAbstractSpinBox.NoButtons)
        control.setMinimumWidth(105)
        control.setKeyboardTracking(False)
        return control

    @staticmethod
    def _reference(asset: StockAsset) -> Optional[float]:
        value = getattr(asset, "resting_value", None)
        if value is None or not isfinite(value) or value <= 0:
            return None
        return float(value)

    def _suggested_limits(self, key: str) -> Tuple[float, float]:
        reference = self._reference(self._assets[key])
        if self.reference_checkbox.isChecked() and reference is not None:
            return round(reference * 0.5, 2), round(reference, 2)
        return self._fallback_limits

    def _refresh_inputs(self, _checked=None):
        for key, (buy_input, sell_input) in self._inputs.items():
            defaults = self._suggested_limits(key)
            override = self._draft_overrides.get(key)
            values = (override["buy"], override["sell"]) if override else defaults
            for control, value in zip((buy_input, sell_input), values):
                control.blockSignals(True)
                control.setValue(value)
                control.blockSignals(False)
                control.setToolTip(
                    "Limite personalizado." if override else "Limite sugerido; pode ser editado."
                )

    def _record_override(self, key: str):
        buy_input, sell_input = self._inputs[key]
        values = (buy_input.value(), sell_input.value())
        if values == self._suggested_limits(key):
            self._draft_overrides.pop(key, None)
        else:
            self._draft_overrides[key] = {"buy": values[0], "sell": values[1]}

    def _restore_suggestions(self):
        self._draft_overrides.clear()
        self.reference_checkbox.setChecked(True)
        self._refresh_inputs()

    def accept(self):
        # Interpret pending text before validation, including keyboard submission.
        for key, (buy_input, sell_input) in self._inputs.items():
            buy_input.interpretText()
            sell_input.interpretText()
            buy, sell = buy_input.value(), sell_input.value()
            if not (isfinite(buy) and isfinite(sell) and 0 < buy < sell):
                QMessageBox.warning(
                    self,
                    "Limites inválidos",
                    f"{self._assets[key].name}: use preços positivos e um limite de "
                    "compra menor que o limite de venda.",
                )
                buy_input.setFocus()
                return
        self.overrides = deepcopy(self._draft_overrides)
        self.use_reference_prices = self.reference_checkbox.isChecked()
        super().accept()
