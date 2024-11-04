"""
Later:
>>> img = QImage('W:\\Media\\Images\\genshinCharacter\\Furina_Profile.webp')
>>> QApplication.instance().clipboard().setImage(img)
"""
import json
import random
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import krita as K

@dataclass
class TransformParams:
    x0: float
    y0: float
    dx: float
    dy: float
    s: float
    w: float
    h: float

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
    return TransformParams(x0, y0, dx, dy, s*imageScale, wi*s, hi*s)

class LabelNumberUnit(K.QWidget):
    def __init__(self, label: str, units: List[str], includeLock: bool = False) -> None:
        super().__init__()
        layout = K.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
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
        if includeLock:
            self.isLocked = False
            self.lock = K.QPushButton()
            self.lock.setIcon(K.Krita.instance().icon('unlocked'))
            self.lock.setSizePolicy(K.QSizePolicy.Fixed, K.QSizePolicy.Fixed)
            self.lock.clicked.connect(self._toggleLock)
            layout.addWidget(self.lock)

    def _toggleLock(self):
        self.isLocked = not self.isLocked
        inst = K.Krita.instance()
        self.lock.setIcon(inst.icon('locked' if self.isLocked else 'unlocked'))

    def setValue(self, v: int) -> None:
        self.number.blockSignals(True)
        self.number.setValue(v)
        self.number.blockSignals(False)

def matchWidths(widgets: List[K.QWidget]) -> None:
    """Find max width and set all widths to it."""
    width = 0
    for widget in widgets:
        width = max(width, widget.sizeHint().width())
    for widget in widgets:
        widget.setFixedWidth(width)

@dataclass
class Margins:
    left: int = 0
    right: int = 0
    top: int = 0
    bottom: int = 0

    def toJson(self) -> dict:
        obj = {
            'left': self.left,
            'right': self.right,
            'top': self.top,
            'bottom': self.bottom,
        }
        return obj

def loadImageToNode(image: K.QImage, node: K.Node) -> None:
    # The format is hardcoded. Maybe condition on it later.
    image = image.convertToFormat(K.QImage.Format_ARGB32)
    w = image.width()
    h = image.height()
    size = 4*w*h
    imageData = image.constBits().asstring(size)
    node.setPixelData(imageData, 0, 0, w, h)

validImageExt = set(
    '.' + fmt.data().decode('utf-8')
    for fmt in K.QImageReader.supportedImageFormats()
)
validImageExt.discard('.kra')

def getImagePaths(pathDir: Path) -> List[Path]:
    paths = [
        path for path in pathDir.iterdir()
        if path.suffix in validImageExt
    ]
    return paths

def getNextPath(path: Path) -> Path:
    paths = getImagePaths(path.parent)
    i = paths.index(path)
    p = paths[(i+1) % len(paths)]
    return p

def getPrevPath(path: Path) -> Path:
    paths = getImagePaths(path.parent)
    i = paths.index(path)
    p = paths[(i-1) % len(paths)]
    return p

@dataclass
class LayerState:
    doc: K.Document
    node: K.Node
    path: Path
    alignment: Alignment = Alignment.CENTER
    margins: Margins = field(default_factory=Margins)
    scale: float = 1.0
    scaleToFit: bool = True
    currentScale: float = 1.0

    def __post_init__(self) -> None:
        self._prevPath = None
        self._prevBounds = self.doc.bounds()

    def toJson(self) -> dict:
        obj = {
            'node': self.node.name(),
            'path': str(self.path),
            'alignment': self.alignment.name,
            'margins': self.margins.toJson(),
            'scale': self.scale,
            'scaleToFit': self.scaleToFit,
            'currentScale': self.currentScale,
        }
        return obj

    @staticmethod
    def fromJson(obj: dict, doc: K.Document) -> Optional['LayerState']:
        node = doc.nodeByName(obj['node'])
        if node is None:
            return None
        state = LayerState(
            doc=doc,
            node=node,
            path=Path(obj['path']),
            alignment=Alignment[obj['alignment']],
            margins=Margins(**obj['margins']),
            scale=obj['scale'],
            scaleToFit=obj['scaleToFit'],
            currentScale=obj['currentScale'])
        return state

    def update(self) -> None:
        if self.path == self._prevPath:
            t = self._getTransform(self._prevBounds)
            if t.s == self.currentScale:
                self.node.move(int(t.dx-t.x0), int(t.dy-t.y0))
                self.doc.refreshProjection()
                return
        image = K.QImage(str(self.path))
        node = self.doc.createNode(self.node.name(), 'paintlayer')
        loadImageToNode(image, node)
        bounds = K.QRect(node.bounds())
        transform = self._getTransform(bounds)
        self._applyTransform(node, transform)
        self.node.setAlphaLocked(True)
        self.doc.refreshProjection()
        self._prevPath = self.path
        self._prevBounds = bounds

    def _getTransform(self, bounds: K.QRect) -> TransformParams:
        docRect = self.doc.bounds()
        container = K.QRect(
            docRect.x() + self.margins.left,
            docRect.y() + self.margins.top,
            docRect.width() - self.margins.left - self.margins.right,
            docRect.height() - self.margins.top - self.margins.bottom)
        transform = computeTransform(
            container=container,
            img=bounds,
            alignment=self.alignment,
            imageScale=self.scale,
            scaleToFit=self.scaleToFit)
        return transform

    def _applyTransform(self, node: K.Node, transform: TransformParams) -> None:
        # Node needs to have a parent to be scaled.
        node.setVisible(False)
        parent = self.node.parentNode()
        if parent:
            parent.addChildNode(node, self.node)
        t = transform
        node.scaleNode(K.QPointF(t.x0, t.y0), int(t.w), int(t.h), 'Bicubic')
        node.move(int(t.dx-t.x0), int(t.dy-t.y0))
        node.setVisible(self.node.visible())
        self.node.remove()
        self.node = node
        self.currentScale = t.s

    def index(self) -> Tuple:
        root = self.doc.rootNode()
        indices = []
        node = self.node
        while node and node != root:
            indices.append(node.index())
            node = node.parentNode()
        return tuple(reversed(indices))

class DynamicComboBox(K.QComboBox):
    def __init__(self, getItems: Callable[[], List[str]]) -> None:
        self._getItems = getItems
        super().__init__()

    def showPopup(self) -> None:
        text = self.currentText()
        self.clear()
        self.addItems(self._getItems())
        self.setCurrentText(text)
        super().showPopup()

State = Tuple[List[LayerState], Optional[LayerState]]

class RefLayerWidget(K.QWidget):
    def __init__(self) -> None:
        super().__init__()
        # State
        self._state: Dict[str, State] = {}
        # Krita state
        self._instance = K.Krita.instance()
        self._notifier = self._instance.notifier()
        self._window = None
        # Widgets
        self._comboBox = DynamicComboBox(self._getLayerNames)
        self._addLayerButton = K.QPushButton()
        self._deleteLayerButton = K.QPushButton()
        self._fileDialog = K.QFileDialog()
        self._fileButton = K.QPushButton()
        self._fileText = K.QLineEdit('Select a file.')
        self._nextButton = K.QPushButton('Next Image')
        self._prevButton = K.QPushButton('Prev Image')
        self._visibleButton = K.QPushButton()
        self._alignmentButtons = [K.QCheckBox() for _ in range(9)]
        self._marginFromLayerButton = K.QPushButton('Margins from Active Layer.')
        self._marginInputs = [
            LabelNumberUnit(label, ['px'])
            for label in ['Left:', 'Right:', 'Top:', 'Bottom:']]
        self._containerWidth = LabelNumberUnit('Container Width:', ['px'], True)
        self._containerHeight = LabelNumberUnit('Container Height:', ['px'], True)
        self._scaleTextInput = LabelNumberUnit('Image Scale:', ['%'])
        self._scaleToFitCheckBox = K.QCheckBox('Scale image down to fit.')
        self._scaleText = K.QLabel('Current Image Scale: 100%')
        # Configuration
        self._configureNotifier()
        self._configureLayout()
        self._configureCombo()
        self._configureFileSelection()
        self._configureNavigation()
        self._configureVisible()
        self._configureAlignment()
        self._configureMargin()
        self._configureScale()
        self._configureExtension()

    def _getActiveState(self) -> Optional[State]:
        doc = self._instance.activeDocument()
        if doc is None:
            return None
        if doc.name() not in self._state:
            layers = []
            if 'RefLayer' in doc.annotationTypes():
                data = doc.annotation('RefLayer').data()
                for obj in json.loads(data):
                    layer = LayerState.fromJson(obj, doc)
                    if layer:
                        layers.append(layer)
            activeLayer = layers[0] if layers else None
            self._state[doc.name()] = (layers, activeLayer)
        return self._state.get(doc.name())

    def _setActiveState(self, state: State) -> None:
        doc = self._instance.activeDocument()
        if doc:
            self._state[doc.name()] = state

    def _cleanState(self) -> None:
        state = self._getActiveState()
        if state is None:
            return
        layers, activeLayer = state
        layers = [
            layer for layer in layers
            if layer.node.parentNode() is not None
        ]
        layers.sort(key=lambda x: x.index(), reverse=True)
        if activeLayer is None or activeLayer.node.parentNode() is None:
            activeLayer = layers[0] if layers else None
        self._setActiveState((layers, activeLayer))

    def _getLayerNames(self) -> List[str]:
        # Routinely cleanup orphaned nodes. Maybe there is a signal for this?
        self._cleanState()
        state = self._getActiveState()
        if state is None:
            return []
        return [layer.node.name() for layer in state[0]]

    def _updateState(self, state: State) -> None:
        layers, activeLayer = state
        if activeLayer:
            activeLayer.update()
            text = f'Current Image Scale: {activeLayer.currentScale*100:.3g}%'
            self._scaleText.setText(text)
        doc = self._instance.activeDocument()
        if doc:
            obj = [layer.toJson() for layer in layers]
            data = json.dumps(obj).encode('utf-8')
            doc.setAnnotation('RefLayer', 'RefLayer Metadata', data)

    def _updateStateUI(self, state: State) -> None:
        layerNames = self._getLayerNames()
        self._comboBox.clear()
        self._comboBox.addItems(layerNames)
        layers, activeLayer = state
        if activeLayer:
            self._comboBox.setCurrentText(activeLayer.node.name())
            self._fileText.setText(str(activeLayer.path))
            self._fileDialog.setDirectory(str(activeLayer.path.parent))
            isVisible = activeLayer.node.visible()
            icon = self._instance.icon('visible' if isVisible else 'novisible')
            self._visibleButton.setIcon(icon)
            for i, button in enumerate(self._alignmentButtons):
                button.setChecked(i == activeLayer.alignment)
            m = activeLayer.margins
            for lnu, v in zip(self._marginInputs, [m.left, m.right, m.top, m.bottom]):
                lnu.setValue(v)
            docRect = activeLayer.doc.bounds()
            self._containerWidth.setValue(docRect.width() - m.left - m.right)
            self._containerHeight.setValue(docRect.height() - m.top - m.bottom)
            self._scaleTextInput.setValue(int(activeLayer.scale*100))
            self._scaleToFitCheckBox.setChecked(activeLayer.scaleToFit)
            text = f'Current Image Scale: {activeLayer.currentScale*100:.3g}%'
            self._scaleText.setText(text)

    def _handleActiveViewChanged(self) -> None:
        state = self._getActiveState()
        if state:
            self._updateStateUI(state)

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

        comboLayout = K.QHBoxLayout()
        comboLayout.setContentsMargins(0, 0, 0, 0)
        comboWidget = K.QWidget()
        comboWidget.setLayout(comboLayout)
        comboLayout.addWidget(self._addLayerButton)
        comboLayout.addWidget(self._comboBox)
        comboLayout.addWidget(self._deleteLayerButton)
        self._addLayerButton.setIcon(self._instance.icon('addlayer'))
        self._addLayerButton.setSizePolicy(K.QSizePolicy.Fixed, K.QSizePolicy.Fixed)
        self._deleteLayerButton.setIcon(self._instance.icon('deletelayer'))
        self._deleteLayerButton.setSizePolicy(K.QSizePolicy.Fixed, K.QSizePolicy.Fixed)
        mainLayout.addWidget(comboWidget)

        fileLayout = K.QHBoxLayout()
        fileLayout.setContentsMargins(0, 0, 0, 0)
        fileWidget = K.QWidget()
        fileWidget.setLayout(fileLayout)
        fileLayout.addWidget(self._fileButton)
        fileLayout.addWidget(self._fileText)
        self._fileText.setReadOnly(True)
        self._fileButton.setIcon(self._instance.icon('folder'))
        mainLayout.addWidget(fileWidget)

        navLayout = K.QHBoxLayout()
        navLayout.setContentsMargins(0, 0, 0, 0)
        navWidget = K.QWidget()
        navWidget.setLayout(navLayout)
        navLayout.addWidget(self._visibleButton)
        navLayout.addWidget(self._prevButton)
        navLayout.addWidget(self._nextButton)
        self._visibleButton.setIcon(self._instance.icon('visible'))
        self._visibleButton.setSizePolicy(K.QSizePolicy.Fixed, K.QSizePolicy.Fixed)
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

        marginLayout = K.QVBoxLayout()
        marginLayout.setAlignment(K.Qt.AlignTop)
        marginWidget = K.QWidget()
        marginWidget.setLayout(marginLayout)
        marginLayout.addWidget(self._marginFromLayerButton)
        for marginInput in self._marginInputs:
            marginLayout.addWidget(marginInput)
        matchWidths([m.label for m in self._marginInputs])
        marginLayout.addWidget(self._containerWidth)
        marginLayout.addWidget(self._containerHeight)
        matchWidths([self._containerWidth.label, self._containerHeight.label])
        tabWidget.addTab(marginWidget, 'Margins')

        scaleLayout = K.QVBoxLayout()
        scaleLayout.setAlignment(K.Qt.AlignTop)
        scaleWidget = K.QWidget()
        scaleWidget.setLayout(scaleLayout)
        scaleLayout.addWidget(self._scaleTextInput)
        scaleLayout.addWidget(self._scaleToFitCheckBox)
        scaleLayout.addWidget(self._scaleText)
        tabWidget.addTab(scaleWidget, 'Scale')

    def _handleIndexChanged(self, index: int) -> None:
        state = self._getActiveState()
        if state and 0 <= index and index < len(state[0]):
            layers, activeLayer = state
            if layers[index] != activeLayer:
                state = (layers, layers[index])
                self._setActiveState(state)
                self._comboBox.blockSignals(True)
                self._updateStateUI(state)
                self._comboBox.blockSignals(False)

    def _createLayerName(self, layers: List[LayerState]) -> str:
        # Some extra work to avoid duplicate names.
        maxNum = 0
        for layer in layers:
            name = layer.node.name()
            i = len(name) - 1
            num = 0
            while name[i].isdigit() and i >= 0:
                i -= 1
            if i + 1 < len(name):
                maxNum = max(maxNum, int(name[i+1:]))
        return f'##RefLayer {maxNum+1}'

    def _handleAddLayer(self) -> None:
        doc = self._instance.activeDocument()
        state = self._getActiveState()
        if doc and state and self._fileDialog.exec():
            files = self._fileDialog.selectedFiles()
            path = Path(files[0])
            nodeName = self._createLayerName(state[0])
            node = doc.createNode(nodeName, 'paintlayer')
            activeNode = doc.activeNode()
            activeNode.parentNode().addChildNode(node, activeNode)
            activeLayer = LayerState(doc, node, path)
            state[0].append(activeLayer)
            state = (state[0], activeLayer)
            self._setActiveState(state)
            self._updateStateUI(state)
            self._updateState(state)

    def _handleDeleteLayer(self) -> None:
        state = self._getActiveState()
        if state and state[1]:
            layers, activeLayer = state
            activeLayer.node.remove()
            layers.remove(activeLayer)
            if layers:
                state = (layers, layers[0])
                self._setActiveState(state)
                self._updateStateUI(state)

    def _configureCombo(self) -> None:
        self._comboBox.currentIndexChanged.connect(self._handleIndexChanged)
        self._addLayerButton.clicked.connect(self._handleAddLayer)
        self._deleteLayerButton.clicked.connect(self._handleDeleteLayer)

    def _handleFileButtonClick(self) -> None:
        state = self._getActiveState()
        if state and state[1] and self._fileDialog.exec():
            files = self._fileDialog.selectedFiles()
            path = Path(files[0])
            state[1].path = path
            self._fileDialog.setDirectory(str(path.parent))
            self._fileText.setText(str(path))
            self._updateState(state)

    def _configureFileSelection(self) -> None:
        ext = ' '.join(map(lambda s: '*' + s, validImageExt))
        self._fileDialog.setNameFilter(f'Images ({ext})')
        self._fileButton.clicked.connect(self._handleFileButtonClick)

    def _handleNextButtonClick(self) -> None:
        state = self._getActiveState()
        if state and state[1]:
            path = getNextPath(state[1].path)
            state[1].path = path
            self._fileText.setText(str(path))
            self._updateState(state)

    def _handlePrevButtonClick(self) -> None:
        state = self._getActiveState()
        if state and state[1]:
            path = getPrevPath(state[1].path)
            state[1].path = path
            self._fileText.setText(str(path))
            self._updateState(state)

    def _configureNavigation(self) -> None:
        self._nextButton.clicked.connect(self._handleNextButtonClick)
        self._prevButton.clicked.connect(self._handlePrevButtonClick)

    def _handleVisibleButtonClick(self) -> None:
        state = self._getActiveState()
        if state and state[1]:
            node = state[1]
            isVisible = not state[1].node.visible()
            state[1].node.setVisible(isVisible)
            icon = self._instance.icon('visible' if isVisible else 'novisible')
            self._visibleButton.setIcon(icon)
            state[1].doc.refreshProjection()

    def _configureVisible(self) -> None:
        self._visibleButton.clicked.connect(self._handleVisibleButtonClick)

    def _handleAlignmentButtonClick(self, a: Alignment) -> Callable[[], None]:
        def _handle() -> None:
            for i, button in enumerate(self._alignmentButtons):
                button.setChecked(i == a)
            state = self._getActiveState()
            if state and state[1]:
                state[1].alignment = a
                self._updateState(state)
        return _handle

    def _configureAlignment(self) -> None:
        for i, button in enumerate(self._alignmentButtons):
            button.setChecked(i == Alignment.CENTER)
            button.clicked.connect(self._handleAlignmentButtonClick(Alignment(i)))

    def _handleTransformChange(self) -> None:
        state = self._getActiveState()
        if state and state[1]:
            attrs = ['left', 'right', 'top', 'bottom']
            for m, attr in zip(self._marginInputs, attrs):
                setattr(state[1].margins, attr, m.number.value())
            state[1].scale = self._scaleTextInput.number.value() / 100
            state[1].scaleToFit = self._scaleToFitCheckBox.isChecked()
            self._updateState(state)

    def _handleEdgeChange(
            self,
            left: LabelNumberUnit,
            right: LabelNumberUnit,
            center: LabelNumberUnit,
            getTotalSize: Callable[[], Optional[int]],
            ) -> Callable[[], None]:
        def _handle() -> None:
            s = getTotalSize()
            if s is None:
                return
            l = left.number.value()
            r = right.number.value()
            c = center.number.value()
            if center.isLocked:
                right.setValue(s - l - c)
            else:
                co = s - l - r
                if co >= 0:
                    center.setValue(co)
                else:
                    center.setValue(0)
                    left.setValue(s - r)
        return _handle

    def _handleCenterChange(
            self,
            left: LabelNumberUnit,
            right: LabelNumberUnit,
            center: LabelNumberUnit,
            getTotalSize: Callable[[], Optional[int]],
            ) -> Callable[[], None]:
        def _handle() -> None:
            s = getTotalSize()
            if s is None:
                return
            l = left.number.value()
            c = center.number.value()
            right.setValue(s - l - c)
        return _handle

    def _handleMarginFromLayer(self) -> None:
        doc = self._instance.activeDocument()
        if doc is None:
            return
        activeNode = doc.activeNode()
        docRect = doc.bounds()
        rect = activeNode.bounds()
        margins = [
            rect.left() - docRect.left(),
            docRect.right() - rect.right(),
            rect.top() - docRect.top(),
            docRect.bottom() - rect.bottom(),
        ]
        for v, widget in zip(margins, self._marginInputs):
            widget.setValue(v)
        self._containerWidth.setValue(rect.width())
        self._containerHeight.setValue(rect.height())
        self._handleTransformChange()

    def _configureMargin(self) -> None:
        self._marginFromLayerButton.clicked.connect(self._handleMarginFromLayer)
        for widget in self._marginInputs:
            widget.number.setRange(-10000, 10000)
            widget.number.setValue(0)
        for widget in (self._marginInputs + [self._containerWidth, self._containerHeight]):
            line = widget.number.lineEdit()
            line.editingFinished.connect(self._handleTransformChange)
            line.returnPressed.connect(self._handleTransformChange)

        def _getDocWidth() -> Optional[int]:
            doc = self._instance.activeDocument()
            return doc.bounds().width() if doc else None
        def _getDocHeight() -> Optional[int]:
            doc = self._instance.activeDocument()
            return doc.bounds().height() if doc else None

        mis = self._marginInputs
        edgeHandles = [
            self._handleEdgeChange(mis[0], mis[1], self._containerWidth, _getDocWidth),
            self._handleEdgeChange(mis[1], mis[0], self._containerWidth, _getDocWidth),
            self._handleEdgeChange(mis[2], mis[3], self._containerHeight, _getDocHeight),
            self._handleEdgeChange(mis[3], mis[2], self._containerHeight, _getDocHeight),
        ]
        for widget, handle in zip(self._marginInputs, edgeHandles):
            widget.number.valueChanged.connect(handle)

        self._containerWidth.number.setRange(0, 50000)
        self._containerHeight.number.setRange(0, 50000)
        centerHandles = [
            self._handleCenterChange(mis[0], mis[1], self._containerWidth, _getDocWidth),
            self._handleCenterChange(mis[2], mis[3], self._containerHeight, _getDocHeight),
        ]
        self._containerWidth.number.valueChanged.connect(centerHandles[0])
        self._containerHeight.number.valueChanged.connect(centerHandles[1])

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
