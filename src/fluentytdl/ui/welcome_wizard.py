from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import MessageBoxBase, PrimaryPushButton

from .help_window import WelcomeGuideWidget
from ..core.config_manager import config_manager

class WelcomeWizardDialog(MessageBoxBase):
    """
    A standalone, modal dialog for the First-Run Experience (FRE).
    Wraps the WelcomeGuideWidget in a clean, frameless container.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Hide standard buttons provided by MessageBoxBase
        self.yesButton.hide()
        self.cancelButton.hide()
        self.buttonGroup.hide()

        # Content
        self.guide = WelcomeGuideWidget(self)
        # Re-wire guide's finish signal to accept/close dialog
        self.guide.finished.connect(self._on_finished)
        
        try:
            self.guide.skip_btn.clicked.disconnect()
        except Exception:
            pass
        self.guide.skip_btn.clicked.connect(self._on_finished)
        
        # Add to layout
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.addWidget(self.guide)
        
        self._set_window_size()

    def _set_window_size(self):
        # MessageBoxBase uses self.widget to control size
        self.widget.setFixedSize(700, 500)
        
    def _on_finished(self):
        # Mark as shown in config, record version
        from fluentytdl import __version__
        config_manager.set("welcome_guide_shown_for_version", __version__)
        config_manager.set("has_shown_welcome_guide", True)
        self.accept()

