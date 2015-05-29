#!/usr/bin/env python
from PySide import QtCore, QtGui
from functools import partial
import os

from . import logger
from . import options
from . import core
from . import ui
from . import prefs

reload(options)
reload(core)
reload(ui)
reload(prefs)


class SceneGraph(QtGui.QMainWindow):

    def __init__(self, parent=None, **kwargs):
        super(SceneGraph, self).__init__(parent)

        #self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self._current_file    = None              # current save file name (if any)
        self._startdir        = kwargs.get('start', os.getenv('HOME'))
        self.timer            = QtCore.QTimer()

        # preferences
        self.prefs_key        = 'SceneGraph'
        self.prefs            = prefs.RecentFiles(self, ui=self.prefs_key)
        self.recent_menu      = None

        self.settings_file    = self.prefs.qtsettings
        self.qtsettings       = QtCore.QSettings(self.settings_file, QtCore.QSettings.IniFormat)
        self.qtsettings.setFallbacksEnabled(False)

        # stylesheet
        self.stylesheet = os.path.join(options.SCENEGRAPH_STYLESHEET_PATH, 'stylesheet.css')
        ssf = QtCore.QFile(self.stylesheet)
        ssf.open(QtCore.QFile.ReadOnly)
        self.setStyleSheet(str(ssf.readAll()))
        ssf.close()

        # icon
        self.setWindowIcon(QtGui.QIcon(os.path.join(options.SCENEGRAPH_ICON_PATH, 'graph_icon.png')))

        self.menubar = QtGui.QMenuBar(self)
        self.centralwidget = QtGui.QWidget(self)
        self.gridLayout = QtGui.QGridLayout(self.centralwidget)
        self.tabWidget = QtGui.QTabWidget(self.centralwidget)
        self.graphTab = QtGui.QWidget()
        self.tabGridLayout = QtGui.QGridLayout(self.graphTab)
        self.main_splitter = QtGui.QSplitter(self.graphTab)
        self.main_splitter.setOrientation(QtCore.Qt.Horizontal)

        # Node view
        self.view = ui.GraphicsView(self.main_splitter, gui=self)
        self.right_splitter = QtGui.QSplitter(self.main_splitter)
        self.right_splitter.setOrientation(QtCore.Qt.Vertical)

        # Node Attributes
        self.detailGroup = QtGui.QGroupBox(self.right_splitter)
        self.detailGroupLayout = QtGui.QVBoxLayout(self.detailGroup)
        # add widgets here
        self.optionsBox = QtGui.QGroupBox(self.right_splitter)
        self.tabGridLayout.addWidget(self.main_splitter, 0, 0, 1, 1)

        self.tabWidget.addTab(self.graphTab, "Scene View")
        self.gridLayout.addWidget(self.tabWidget, 0, 0, 1, 1)
        self.setCentralWidget(self.centralwidget)
        self.menubar = QtGui.QMenuBar(self)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 978, 22))
        self.setMenuBar(self.menubar)
        self.statusbar = QtGui.QStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.initializeUI()
        self.readSettings()
        self.setupConnections()

    def initializeUI(self):
        """
        Set up the main UI
        """
        self.setupFonts()
        self.statusBar().setFont(self.fonts.get('status'))
        # event filter
        self.eventFilter = MouseEventFilter(self)
        self.installEventFilter(self.eventFilter)

        self.buildWindowTitle()
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setSizes([770, 300])
        self.setStyleSheet("QTabWidget {background-color:rgb(68, 68, 68)}")

        self._setupGraphicsView()
        self._setupNodeAttributes()
        self._setupOptions()

        self._buildMenuBar()
        self.resetStatus()

    def setupFonts(self, font='SansSerif', size=9):
        """
        Initializes the fonts attribute
        """
        self.fonts = dict()
        self.fonts["ui"] = QtGui.QFont(font)
        self.fonts["ui"].setPointSize(size)

        self.fonts["status"] = QtGui.QFont(font)
        self.fonts["status"].setStyleHint(QtGui.QFont.Courier)
        self.fonts["status"].setPointSize(size+1)

    def setupConnections(self):
        """
        Set up widget signals/slots
        """
        self.timer.timeout.connect(self.resetStatus)
        self.view.tabPressed.connect(partial(self.createTabMenu, self.view))

    def _setupGraphicsView(self, filter=False):
        # scene view
        self.scene = ui.GraphicsScene()
        self.view.setScene(self.scene)

        # initialize the Node Manager
        self.graph = core.Graph(self.view, gui=self)
        self.scene.setNodeManager(self.graph)
        self.view.setSceneRect(0, 0, 1000, 1000)
        #self.view.setSceneRect(-10000, -10000, 20000, 20000)

        # graphics View
        self.view.wheelEvent = self.graphicsView_wheelEvent
        self.view.resizeEvent = self.graphicsView_resizeEvent
        self.view.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(60, 60, 60, 255), QtCore.Qt.SolidPattern))

        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # event filter
        if filter:
            self.viewEventFilter = MouseEventFilter(self.view)
            self.view.viewport().installEventFilter(self.viewEventFilter)
        self.scene.selectionChanged.connect(self.nodesSelectedAction)

    def _setupNodeAttributes(self):
        self.detailGroup.setTitle('Node Attributes')

    def _setupOptions(self):
        self.optionsBox.setTitle('Scene')

    def _buildMenuBar(self):
        """
        Build the main menubar
        """
        # FILE MENU
        self.menuFile = QtGui.QMenu(self.menubar)
        self.menuFile.setTitle("File")

        self.action_save = QtGui.QAction(self)
        self.action_saveAs = QtGui.QAction(self)
        self.action_read = QtGui.QAction(self)
        self.action_reset = QtGui.QAction(self)

        self.menuFile.addAction(self.action_save)
        self.menuFile.addAction(self.action_saveAs)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.action_read)

        self.action_save.setText("Save graph...")
        self.action_saveAs.setText("Save graph as...")
        self.action_read.setText("Read graph...")
        self.action_reset.setText("Reset graph")

        self.action_saveAs.triggered.connect(self.saveGraphAs)
        self.action_save.triggered.connect(self.saveCurrentGraph)
        self.action_read.triggered.connect(self.readGraph)
        self.action_reset.triggered.connect(self.resetGraph)

        if not self._current_file:
            self.action_save.setEnabled(False)
        self.menubar.addAction(self.menuFile.menuAction())

        # GRAPH MENU
        self.menuGraph = QtGui.QMenu(self.menubar)
        self.menuGraph.setTitle("Graph")

        # Add generic node
        self.action_add_generic = QtGui.QAction(self)
        self.menuGraph.addAction(self.action_add_generic)
        self.action_add_generic.setText("Add Generic node...")
        self.action_add_generic.triggered.connect(partial(self.scene.graph.addNode, 'generic'))

        self.menubar.addAction(self.menuGraph.menuAction())

        # Build the recent files menu
        self._buildRecentFilesMenu()

        # add reset action to the bottom
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.action_reset)

    def _buildRecentFilesMenu(self):
        """
        Build a menu of recently opened scenes
        """
        recent_files = dict()

        # clear the menu
        if self.recent_menu:
            for action in self.recent_menu.children():
                self.recent_menu.removeAction(action)

        # build the menu
        else:
            self.recent_menu = QtGui.QMenu('Recent files...',self)
        self.menuFile.addMenu(self.recent_menu)
        self.recent_menu.setEnabled(False)

        recent_files = self.prefs.getRecentFiles()

        if recent_files:
            # Recent files menu
            for filename in recent_files:
                file_action = QtGui.QAction(filename, self.recent_menu)
                file_action.triggered.connect(partial(self.readRecentGraph, filename))
                self.recent_menu.addAction(file_action)
            self.recent_menu.setEnabled(True)

    def buildWindowTitle(self):
        """
        Build the window title
        """
        title_str = 'Scene Graph - v%s' % options.VERSION_AS_STRING
        if self._current_file:
            title_str = '%s - %s' % (title_str, self._current_file)
        self.setWindowTitle(title_str)

    #- STATUS MESSAGING ------
    # TODO: this is temp, find a better way to redirect output
    def updateStatus(self, val, level='info'):
        """
        Send output to logger/statusbar
        """
        if level == 'info':
            self.statusBar().showMessage(self._getInfoStatus(val))
            logger.getLogger().info(val)
        if level == 'error':
            self.statusBar().showMessage(self._getErrorStatus(val))
            logger.getLogger().error(val)
        if level == 'warning':
            self.statusBar().showMessage(self._getWarningStatus(val))
            logger.getLogger().warning(val)
        self.timer.start(4000)

    def resetStatus(self):
        self.statusBar().showMessage('[SceneGraph]: Ready')

    def _getInfoStatus(self, val):
        return '[SceneGraph]: Info: %s' % val

    def _getErrorStatus(self, val):
        return '[SceneGraph]: Error: %s' % val

    def _getWarningStatus(self, val):
        return '[SceneGraph]: Warning: %s' % val

    #- SAVING/LOADING ------
    def saveGraphAs(self, filename=None):
        """
        Save the current graph to a json file

        Pass the filename argument to override

        params:
            filename  - (str) file path
        """
        import os
        if not filename:
            if self._current_file:
                filename, filters = QtGui.QFileDialog.getSaveFileName(self, "Save graph file", self._current_file, "JSON files (*.json)")
                if filename == "":
                    return

        filename = str(os.path.normpath(filename))
        self.updateStatus('saving current graph "%s"' % filename)

        # update the graph attributes
        #root_node.addNodeAttributes(**{'sceneName':filename})

        self.scene.graph.write(filename)
        self._current_file = str(filename)
        self.action_save.setEnabled(True)
        self.buildWindowTitle()

        self.prefs.addFile(filename)
        self._buildRecentFilesMenu()

    # TODO: figure out why this has to be a separate method from saveGraphAs
    def saveCurrentGraph(self):
        """
        Save the current graph file
        """
        self._current_file = '/home/%s/graphs/scene_graph_v001.json' % os.getenv('USER')
        self.updateStatus('saving current graph "%s"' % self._current_file)
        self.graph.write(self._current_file)
        self.buildWindowTitle()

        self.prefs.addFile(self._current_file)
        self._buildRecentFilesMenu()

    def readGraph(self):
        """
        Read the current graph from a json file
        """
        filename, ok = QtGui.QFileDialog.getOpenFileName(self, "Open graph file", self._startdir, "JSON files (*.json)")
        if filename == "":
            return

        self.resetGraph()
        self.updateStatus('reading graph "%s"' % filename)
        self.scene.graph.read(filename)
        self._current_file = str(filename)
        self.action_save.setEnabled(True)
        self.buildWindowTitle()

    # TODO: combine this with readGraph
    def readRecentGraph(self, filename):
        self.resetGraph()
        self.updateStatus('reading graph "%s"' % filename)
        self.scene.graph.read(filename)
        self._current_file = filename
        self.action_save.setEnabled(True)
        self.buildWindowTitle()

    def resetGraph(self):
        """
        Reset the current graph
        """
        self.scene.graph.reset()
        self._current_file = None
        self.action_save.setEnabled(False)
        self.buildWindowTitle()

    def sizeHint(self):
        return QtCore.QSize(1070, 800)

    def removeDetailWidgets(self):
        """
        Remove a widget from the detailGroup box
        """
        for i in reversed(range(self.detailGroupLayout.count())):
            widget = self.detailGroupLayout.takeAt(i).widget()
            if widget is not None:
                widget.deleteLater()

    #- ACTIONS ----
    def nodesSelectedAction(self):
        """
        Action that runs whenever a node is selected in the UI
        """
        self.removeDetailWidgets()
        nodes = self.scene.selectedItems()
        if len(nodes) == 1:
            node = nodes[0]
            if node._is_node:
                nodeAttrWidget = ui.AttributeEditor(self.detailGroup, manager=self.scene.graph, gui=self)
                nodeAttrWidget.setNode(node)
                self.detailGroupLayout.addWidget(nodeAttrWidget)

    #- Events ----
    def closeEvent(self, event):
        """
        Write window prefs when UI is closed
        """
        self.writeSettings()
        event.accept()

    def graphicsView_wheelEvent(self, event):
        factor = 1.41 ** ((event.delta()*.5) / 240.0)
        self.view.scale(factor, factor)

    def graphicsView_resizeEvent(self, event):
        self.scene.setSceneRect(0, 0, self.view.width(), self.view.height())

    #- Menus -----
    def createTabMenu(self, parent):
        """
        Build a context menu at the current pointer pos.
        """
        menu=QtGui.QMenu(parent)
        menu.clear()
        add_action = menu.addAction('Add generic node')
        add_action.triggered.connect(partial(self.scene.graph.addNode, 'generic'))
        qcurs=QtGui.QCursor()
        menu.exec_(qcurs.pos())


    #- Settings -----
    def readSettings(self):
        """
        Read Qt settings from file
        """
        self.qtsettings.beginGroup(self.prefs_key)
        self.resize(self.qtsettings.value("size", QtCore.QSize(400, 256)))
        self.move(self.qtsettings.value("pos", QtCore.QPoint(200, 200)))
        self.qtsettings.endGroup()

    def writeSettings(self):
        """
        Write Qt settings to file
        """
        self.qtsettings.beginGroup(self.prefs_key)
        width = self.width()
        height = self.height()
        self.qtsettings.setValue("size", QtCore.QSize(width, height))
        self.qtsettings.setValue("pos", self.pos())
        self.qtsettings.endGroup()


class MouseEventFilter(QtCore.QObject):
    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            # call a function here..
            # obj.doSomething()
            return True
        return False

