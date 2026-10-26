"""Campos numéricos que deixam a roda do mouse rolar a página."""

from PyQt5.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class ScrollSafeComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class ScrollSafeSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class ScrollSafeDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()
