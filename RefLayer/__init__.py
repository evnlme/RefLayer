"""
TODO: Case where user deletes or changes the RefLayer node.
TODO: Case where multiple instances, windows, or documents are used.
Later:
>>> img = QImage('W:\\Media\\Images\\genshinCharacter\\Furina_Profile.webp')
>>> QApplication.instance().clipboard().setImage(img)
"""
import random
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Callable, List, Optional

import krita as K

@dataclass
class TransformParams:
    x0: float
    y0: float
    dx: float
    dy: float
    s: float

    def xml(self) -> str:
        transform = f"""\
        <!DOCTYPE transform_params>
        <transform_params>
        <main id="tooltransformparams"/>
        <data mode="0">
        <free_transform>
            <transformedCenter type="pointf" x="{self.dx}" y="{self.dy}"/>
            <originalCenter type="pointf" x="{self.x0}" y="{self.y0}"/>
            <rotationCenterOffset type="pointf" x="0" y="0"/>
            <transformAroundRotationCenter value="0" type="value"/>
            <aX value="0" type="value"/>
            <aY value="0" type="value"/>
            <aZ value="0" type="value"/>
            <cameraPos z="1024" type="vector3d" x="0" y="0"/>
            <scaleX value="{self.s}" type="value"/>
            <scaleY value="{self.s}" type="value"/>
            <shearX value="0" type="value"/>
            <shearY value="0" type="value"/>
            <keepAspectRatio value="0" type="value"/>
            <flattenedPerspectiveTransform m23="0" m31="0" m32="0" type="transform" m33="1" m12="0" m13="0" m22="1" m11="1" m21="0"/>
            <filterId value="Bicubic" type="value"/>
        </free_transform>
        </data>
        </transform_params>
        """
        return transform

class Alignment(IntEnum):
    TOP_LEFT = 0
    TOP = 1
    TOP_RIGHT = 2
    LEFT = 3
    CENTER = 4
    RIGHT = 5
    BOTTOM_LEFT = 6
    BOTTOM = 7
    BOTTOM_RIGHT = 8

def computeTransform(
        container: K.QRect,
        img: K.QRect,
        alignment: Alignment = Alignment.CENTER,
        imageScale: float = 1.0,
        scaleToFit: bool = True,
        ) -> TransformParams:
    wc, hc = container.width(), container.height()
    wi, hi = img.width()*imageScale, img.height()*imageScale
    s = min(wc/wi, hc/hi, 1.0) if scaleToFit else 1.0
    x0 = img.x()
    y0 = img.y()
    dx = container.x() + (wc - wi*s)*(alignment % 3)/2
    dy = container.y() + (hc - hi*s)*(alignment // 3)/2
    return TransformParams(x0, y0, dx, dy, s*imageScale)

class LabelNumberUnit(K.QWidget):
    def __init__(self, label: str, units: List[str], includeLock: bool = False) -> None:
        super().__init__()
        layout = K.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.label =  K.QLabel(label)
        self.label.setSizePolicy(K.QSizePolicy.Fixed, K.QSizePolicy.Fixed)
        self.number = K.QSpinBox()
        self.unit = K.QComboBox()
        self.unit.addItems(units)
        if len(units) == 1:
            self.unit.setEnabled(False)
        self.unit.setSizePolicy(K.QSizePolicy.Fixed, K.QSizePolicy.Fixed)
        self.setLayout(layout)
        layout.addWidget(self.label)
        layout.addWidget(self.number)
        layout.addWidget(self.unit)
        layout.setSpacing(3)

def matchWidths(widgets: List[K.QWidget]) -> None:
    """Find max width and set all widths to it."""
    width = 0
    for widget in widgets:
        width = max(width, widget.sizeHint().width())
    for widget in widgets:
        widget.setFixedWidth(width)

class RefLayerWidget(K.QWidget):
    validImageExt = [
        '.webp',
        '.avif',
        '.png',
        '.jpg',
        '.jpeg',
    ]

    def __init__(self) -> None:
        super().__init__()
        # State
        self._alignment = Alignment.CENTER
        self._margins = [0, 0, 0, 0]
        self._imageScale = 1.0
        self._scaleToFit = True
        # Krita state
        self._instance = K.Krita.instance()
        self._notifier = self._instance.notifier()
        self._window = None
        # Widgets
        self._fileDialog = K.QFileDialog()
        self._fileButton = K.QPushButton()
        self._fileText = K.QLineEdit('Select a file.')
        self._nextButton = K.QPushButton('Next Image')
        self._prevButton = K.QPushButton('Prev Image')
        self._visibleButton = K.QPushButton()
        self._alignmentButtons = [K.QCheckBox() for _ in range(9)]
        self._marginTextInputs = [
            LabelNumberUnit(label, ['px'])
            for label in ['Top:', 'Left:', 'Bottom:', 'Right:']]
        self._scaleTextInput = LabelNumberUnit('Scale:', ['%'])
        self._scaleToFitCheckBox = K.QCheckBox('Scale down to fit.')
        self._scaleText = K.QLabel('Current Scale: 100%')
        # Configuration
        self._configureNotifier()
        self._configureLayout()
        self._configureFileSelection()
        self._configureNavigation()
        self._configureVisible()
        self._configureAlignment()
        self._configureMargin()
        self._configureScale()
        self._configureExtension()

    def _handleActiveViewChanged(self) -> None:
        refLayer = self._getRefLayer()
        if refLayer:
            self._fileText.setText(refLayer.path())
            isVisible = refLayer.visible()
            self._visibleButton.setIcon(self._instance.icon('visible' if isVisible else 'novisible'))
        else:
            self._fileText.setText('Select a file.')

    def _handleWindowCreated(self) -> None:
        self._window = self._instance.activeWindow()
        self._window.activeViewChanged.connect(self._handleActiveViewChanged)

    def _configureNotifier(self) -> None:
        self._notifier.windowCreated.connect(self._handleWindowCreated)

    def _configureLayout(self) -> None:
        mainLayout = K.QVBoxLayout()
        mainLayout.setAlignment(K.Qt.AlignTop)
        mainWidget = K.QWidget()
        mainWidget.setLayout(mainLayout)

        scrollArea = K.QScrollArea()
        scrollArea.setWidget(mainWidget)
        scrollArea.setWidgetResizable(True)
        scrollLayout = K.QVBoxLayout()
        scrollLayout.setAlignment(K.Qt.AlignTop)
        scrollLayout.addWidget(scrollArea)
        self.setLayout(scrollLayout)

        fileLayout = K.QHBoxLayout()
        fileLayout.setContentsMargins(0, 0, 0, 0)
        fileWidget = K.QWidget()
        fileWidget.setLayout(fileLayout)
        fileLayout.addWidget(self._fileText)
        fileLayout.addWidget(self._fileButton)
        self._fileText.setReadOnly(True)
        self._fileButton.setIcon(self._instance.icon('folder'))
        mainLayout.addWidget(fileWidget)

        navLayout = K.QHBoxLayout()
        navLayout.setContentsMargins(0, 0, 0, 0)
        navWidget = K.QWidget()
        navWidget.setLayout(navLayout)
        navLayout.addWidget(self._prevButton)
        navLayout.addWidget(self._nextButton)
        self._visibleButton.setIcon(self._instance.icon('visible'))
        self._visibleButton.setSizePolicy(K.QSizePolicy.Fixed, K.QSizePolicy.Fixed)
        navLayout.addWidget(self._visibleButton)
        mainLayout.addWidget(navWidget)

        tabWidget = K.QTabWidget()
        mainLayout.addWidget(tabWidget)

        alignLayout = K.QVBoxLayout()
        alignLayout.setAlignment(K.Qt.AlignTop)
        alignWidget = K.QWidget()
        alignWidget.setLayout(alignLayout)
        gridLayout = K.QGridLayout()
        gridLayout.setAlignment(K.Qt.AlignCenter)
        gridWidget = K.QWidget()
        gridWidget.setLayout(gridLayout)
        for i, button in enumerate(self._alignmentButtons):
            gridLayout.addWidget(button, i // 3, i % 3)
        alignLayout.addWidget(gridWidget)
        tabWidget.addTab(alignWidget, 'Alignment')

        marginLayout = K.QGridLayout()
        marginLayout.setAlignment(K.Qt.AlignTop)
        marginWidget = K.QWidget()
        marginWidget.setLayout(marginLayout)
        for i, widget in enumerate(self._marginTextInputs):
            marginLayout.addWidget(widget, i // 2, i % 2)
        matchWidths([widget.label for widget in self._marginTextInputs[0::2]])
        matchWidths([widget.label for widget in self._marginTextInputs[1::2]])
        tabWidget.addTab(marginWidget, 'Margins')

        scaleLayout = K.QVBoxLayout()
        scaleLayout.setAlignment(K.Qt.AlignTop)
        scaleWidget = K.QWidget()
        scaleWidget.setLayout(scaleLayout)
        scaleLayout.addWidget(self._scaleTextInput)
        scaleLayout.addWidget(self._scaleToFitCheckBox)
        scaleLayout.addWidget(self._scaleText)
        tabWidget.addTab(scaleWidget, 'Scale')

    def _getRefLayer(self) -> Optional[K.Node]:
        doc = self._instance.activeDocument()
        return doc.nodeByName('##RefLayer') if doc else None

    def _updateRefLayer(self, path: Path) -> K.Node:
        self._fileText.setText(str(path))
        self._fileDialog.setDirectory(str(path.parent))
        refLayer = self._getRefLayer()
        props = (str(path), 'None', 'Bicubic')
        if refLayer:
            refLayer.setProperties(*props)
        else:
            doc = self._instance.activeDocument()
            refLayer = doc.createFileLayer('##RefLayer', *props)
            activeNode = doc.activeNode()
            parentNode = activeNode.parentNode()
            parentNode.addChildNode(refLayer, activeNode)
        return refLayer

    def _getTransformMask(self) -> Optional[K.Node]:
        doc = self._instance.activeDocument()
        return doc.nodeByName('##RefLayer#Transform') if doc else None

    def _updateTransformMask(self, refLayer: K.Node) -> K.Node:
        doc = self._instance.activeDocument()
        docRect = doc.bounds()
        container = K.QRect(
            docRect.x() + self._margins[1],
            docRect.y() + self._margins[0],
            docRect.width() - self._margins[1] - self._margins[3],
            docRect.height() - self._margins[0] - self._margins[2])
        transformMask = self._getTransformMask()
        if transformMask is None:
            transformMask = doc.createTransformMask('##RefLayer#Transform')
            refLayer.addChildNode(transformMask, None)
        transform = computeTransform(
            container,
            refLayer.bounds(),
            self._alignment,
            self._imageScale,
            self._scaleToFit)
        transformMask.fromXML(transform.xml())
        self._scaleText.setText(f'Current Scale: {transform.s*100:.3g}%')
        doc.refreshProjection()
        return transformMask

    def _handleFileButtonClick(self):
        if self._instance.activeDocument() and self._fileDialog.exec():
            files = self._fileDialog.selectedFiles()
            path = Path(files[0])
            refLayer = self._updateRefLayer(path)
            self._updateTransformMask(refLayer)

    def _configureFileSelection(self) -> None:
        ext = ' '.join(map(lambda s: '*' + s, RefLayerWidget.validImageExt))
        self._fileDialog.setNameFilter(f'Images ({ext})')
        self._fileButton.clicked.connect(self._handleFileButtonClick)

    def _nextImage(self, fn) -> None:
        refLayer = self._getRefLayer()
        if refLayer is None:
            return
        path = Path(refLayer.path())
        paths = list(path.parent.iterdir())
        i = paths.index(path)
        for j in range(len(paths)):
            idx = fn(i, j) % len(paths)
            if paths[idx].suffix in RefLayerWidget.validImageExt:
                nextPath = paths[idx]
                refLayer = self._updateRefLayer(nextPath)
                self._updateTransformMask(refLayer)
                return

    def _handleNextButtonClick(self) -> None:
        self._nextImage(lambda i, j: i+j+1)

    def _handlePrevButtonClick(self) -> None:
        self._nextImage(lambda i, j: i-j-1)

    def _configureNavigation(self) -> None:
        self._nextButton.clicked.connect(self._handleNextButtonClick)
        self._prevButton.clicked.connect(self._handlePrevButtonClick)

    def _handleVisibleButtonClick(self) -> None:
        refLayer = self._getRefLayer()
        if refLayer:
            isVisible = not refLayer.visible()
            refLayer.setVisible(isVisible)
            self._visibleButton.setIcon(self._instance.icon('visible' if isVisible else 'novisible'))
            # Document must exist since refLayer exists.
            self._instance.activeDocument().refreshProjection()

    def _configureVisible(self) -> None:
        self._visibleButton.clicked.connect(self._handleVisibleButtonClick)

    def _handleAlignmentButtonClick(self, a: Alignment) -> Callable[[], None]:
        def _handle() -> None:
            self._alignment = a
            for i, button in enumerate(self._alignmentButtons):
                button.setChecked(i == a)
            refLayer = self._getRefLayer()
            if refLayer:
                self._updateTransformMask(refLayer)
        return _handle

    def _configureAlignment(self) -> None:
        for i, button in enumerate(self._alignmentButtons):
            button.setChecked(i == Alignment.CENTER)
            button.clicked.connect(self._handleAlignmentButtonClick(i))

    def _handleTransformChange(self) -> None:
        self._margins = [m.number.value() for m in self._marginTextInputs]
        self._imageScale = self._scaleTextInput.number.value() / 100
        self._scaleToFit = self._scaleToFitCheckBox.isChecked()
        refLayer = self._getRefLayer()
        if refLayer:
            self._updateTransformMask(refLayer)

    def _configureMargin(self) -> None:
        labels = ['Top', 'Left', 'Bottom', 'Right']
        for widget, label in zip(self._marginTextInputs, labels):
            #widget.setPrefix(label + ': ')
            #widget.setSuffix(' px')
            widget.number.setRange(0, 10000)
            widget.number.setValue(0)
            line = widget.number.lineEdit()
            line.editingFinished.connect(self._handleTransformChange)
            line.returnPressed.connect(self._handleTransformChange)

    def _configureScale(self) -> None:
        self._scaleTextInput.number.setRange(1, 1000)
        self._scaleTextInput.number.setValue(100)
        line = self._scaleTextInput.number.lineEdit()
        line.editingFinished.connect(self._handleTransformChange)
        line.returnPressed.connect(self._handleTransformChange)
        self._scaleToFitCheckBox.setChecked(True)
        self._scaleToFitCheckBox.clicked.connect(self._handleTransformChange)

    def _configureExtension(self) -> None:
        ext = RefLayerExt(self._instance, self)
        self._instance.addExtension(ext)

class RefLayerExt(K.Extension):
    def __init__(self, parent, widget: RefLayerWidget):
        super().__init__(parent)
        self._widget = widget

    def setup(self):
        pass

    def createActions(self, window):
        refLayerMenu = K.QtWidgets.QMenu('RefLayer_Menu', window.qwindow())
        refLayerMenuAction = window.createAction('RefLayer_Menu', 'RefLayer', 'tools/scripts')
        refLayerMenuAction.setMenu(refLayerMenu)
        loc = 'tools/scripts/RefLayer_Menu'
        nextAction = window.createAction('RefLayer_NextImage', 'Next Image', loc)
        prevAction = window.createAction('RefLayer_PrevImage', 'Prev Image', loc)
        visibleAction = window.createAction('RefLayer_Visible', 'Visible Toggle', loc)
        nextAction.triggered.connect(self._widget._handleNextButtonClick)
        prevAction.triggered.connect(self._widget._handlePrevButtonClick)
        visibleAction.triggered.connect(self._widget._handleVisibleButtonClick)

class RefLayer(K.DockWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('RefLayer')
        global _refLayerWidget
        _refLayerWidget = RefLayerWidget()
        self.setWidget(_refLayerWidget)

    def canvasChanged(self, canvas):
        pass

factory = K.DockWidgetFactory(
    'RefLayer',
    K.DockWidgetFactoryBase.DockRight,
    RefLayer)
instance = K.Krita.instance()
instance.addDockWidgetFactory(factory)
