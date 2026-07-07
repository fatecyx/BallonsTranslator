from typing import List, Callable

from qtpy.QtWidgets import QComboBox, QWidget
from qtpy.QtCore import Signal, Qt
from qtpy.QtGui import QDoubleValidator, QValidator

from utils.shared import CONFIG_COMBOBOX_LONG, CONFIG_COMBOBOX_MIDEAN, CONFIG_COMBOBOX_SHORT, CONFIG_COMBOBOX_HEIGHT
from .push_button import NoBorderPushBtn


class ComboBox(QComboBox):

    # https://stackoverflow.com/questions/3241830/qt-how-to-disable-mouse-scrolling-of-qcombobox
    def __init__(self, parent: QWidget = None, scrollWidget: QWidget = None, options: List[str] = None) -> None:
        super().__init__(parent)
        self.scrollWidget = scrollWidget
        if options is not None:
            self.addItems(options)

    def setScrollWidget(self, scrollWidget: QWidget):
        self.scrollWidget = scrollWidget

    def wheelEvent(self, *args, **kwargs):
        if self.scrollWidget is None or self.hasFocus():
            return super().wheelEvent(*args, **kwargs)
        else:
            return self.scrollWidget.wheelEvent(*args, **kwargs)
        

class SmallComboBox(ComboBox):
    pass


class ConfigComboBox(ComboBox):

    def __init__(self, fix_size=True, scrollWidget: QWidget = None, *args, **kwargs) -> None:
        super().__init__(scrollWidget, *args, **kwargs)
        self.fix_size = fix_size
        self.adjustSize()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def addItems(self, texts: List[str]) -> None:
        super().addItems(texts)
        self.adjustSize()

    def adjustSize(self) -> None:
        super().adjustSize()
        width = self.minimumSizeHint().width()
        if width < CONFIG_COMBOBOX_SHORT:
            width = CONFIG_COMBOBOX_SHORT
        elif width < CONFIG_COMBOBOX_MIDEAN:
            width = CONFIG_COMBOBOX_MIDEAN
        else:
            width = CONFIG_COMBOBOX_LONG
        if self.fix_size:
            self.setFixedWidth(width)
        else:
            self.setMaximumWidth(width)


class ParamComboBox(ComboBox):
    paramwidget_edited = Signal(str, str)
    flushbtn_clicked = Signal()
    pathbtn_clicked = Signal()
    def __init__(self, param_key: str, options: List[str], size=CONFIG_COMBOBOX_SHORT, scrollWidget: QWidget = None, flush_btn: bool = False, path_selector: bool = False, *args, **kwargs) -> None:
        super().__init__(scrollWidget=scrollWidget, *args, **kwargs)
        self.param_key = param_key
        self.setFixedWidth(size)
        self.setFixedHeight(CONFIG_COMBOBOX_HEIGHT)
        options = [str(opt) for opt in options]
        self.addItems(options)
        self.currentTextChanged.connect(self.on_select_changed)
        
        if flush_btn:
            self.flush_btn = NoBorderPushBtn(self.tr('Flush'))
            self.flush_btn.clicked.connect(self.flushbtn_clicked)
        if path_selector:
            self.path_select_btn = NoBorderPushBtn(self.tr('Select Path'))
            self.path_select_btn.clicked.connect(self.pathbtn_clicked)

    def on_select_changed(self):
        self.paramwidget_edited.emit(self.param_key, self.currentText())


class RangeValidator(QValidator):
    def __init__(self, min_val: float, max_val: float, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val

    def validate(self, string: str, pos: int):
        if not string:
            return QValidator.State.Intermediate, string, pos
        if string == "." or string == "-":
            return QValidator.State.Intermediate, string, pos
        try:
            val = float(string)
            if val > self.max_val:
                return QValidator.State.Invalid, string, pos
            if val < self.min_val:
                return QValidator.State.Intermediate, string, pos
            return QValidator.State.Acceptable, string, pos
        except ValueError:
            return QValidator.State.Invalid, string, pos


class SizeComboBox(QComboBox):
    
    param_changed = Signal(str, float)
    def __init__(self, val_range: List = None, param_name: str = '', parent=None, init_value=None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.param_name = param_name
        self.editTextChanged.connect(self.on_text_changed)
        self.activated.connect(self.on_current_index_changed)
        self.setEditable(True)
        
        # Connect editingFinished signal of lineEdit for formatting when edit is done
        if self.lineEdit() is not None:
            self.lineEdit().editingFinished.connect(self.on_editing_finished)

        self.min_val = val_range[0]
        self.max_val = val_range[1]
        
        # Use custom RangeValidator to strictly intercept any input exceeding max_val
        validator = RangeValidator(self.min_val, self.max_val, self)
        self.setValidator(validator)
        self._value = 0
        if init_value is not None:
            self.setValue(init_value)

    def is_editing(self) -> bool:
        return self.hasFocus() or (self.lineEdit() is not None and self.lineEdit().hasFocus())

    def on_text_changed(self):
        if self.is_editing():
            txt = self.currentText()
            try:
                val = float(txt)
                val = min(self.max_val, max(self.min_val, val))
                self._value = val
                self.param_changed.emit(self.param_name, val)
            except ValueError:
                # Do not emit if the text is currently a transient invalid state like "." or ""
                pass

    def on_current_index_changed(self):
        if self.hasFocus() or self.view().isVisible():
            val = self.value()
            self.setValue(val, force_update_text=True)
            self.param_changed.emit(self.param_name, val)

    def on_editing_finished(self):
        self.setValue(self.value(), force_update_text=True)

    def value(self) -> float:
        txt = self.currentText()
        try:
            val = float(txt)
            self._value = val
            return val
        except:
            return self._value

    def setValue(self, value: float, force_update_text: bool = False):
        value = min(self.max_val, max(self.min_val, value))
        self._value = value
        if force_update_text or not self.is_editing():
            self.setCurrentText(str(round(value, 2)))

    def changeByDelta(self, delta: float, multiplier = 0.01):
        if isinstance(multiplier, Callable):
            multiplier = multiplier()
        self.setValue(self.value() + delta * multiplier, force_update_text=True)


class SmallSizeComboBox(SizeComboBox):
    pass