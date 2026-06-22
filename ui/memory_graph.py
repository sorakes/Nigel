from __future__ import annotations
"""
ui/memory_graph.py - Grafo de memoria estilo Obsidian para o Nigel.

Foco desta versao:
- Visual limpo e leve, mais proximo do Obsidian.
- Animacao force-directed continua e fluida.
- Nos simples com glow, labels pequenas e arestas retas.
- Sem painel de detalhe ocupando area do canvas.
"""
import math
import random
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient, QBrush
from PyQt6.QtWidgets import QFrame, QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from ui.icons import IconButton, IconWidget
from ui.theme import C_GOLD, C_GOLD_BRIGHT, FONT, GOLD_BRIGHT_CSS, LABEL_SECTION, TEXT_CSS, TEXT_MID_CSS

SOURCE_COLORS = {'persona': QColor(156, 104, 230, 238), 'persona_related': QColor(190, 139, 205, 232), 'outlook': QColor(201, 168, 76, 230), 'gmail': QColor(225, 142, 62, 230), 'manual': QColor(170, 154, 118, 230), 'agenda_chat': QColor(184, 162, 96, 230), 'ai': QColor(201, 168, 76, 220)}

def _node_color(source: str) -> QColor:
    return SOURCE_COLORS.get(source, SOURCE_COLORS['manual'])

def _is_persona_item(item: dict) -> bool:
    if item.get('node_type', '').lower() == 'persona':
        return True
    source = item.get('source', '').lower()
    item_id = str(item.get('id', ''))
    subject = item.get('subject', '').lower()
    return source == 'persona' or item_id.startswith('persona:') or subject.startswith('persona:')

def _short_label(text: str, limit: int = 18) -> str:
    text = text.strip() if text else '?'
    if len(text) <= limit:
        return text
    return text[:limit - 1] + '...'

class ObsidianScene(QGraphicsScene):
    """Cena com fundo pontilhado discreto, sem bordas pesadas."""

    def __init__(self):
        super().__init__()
        self.setSceneRect(-600, -420, 1200, 840)
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Desenha o fundo pontilhado."""
        painter.fillRect(rect, QColor(250, 246, 238, 255))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor(201, 168, 76, 34), 1))
        step = 28
        left = int(rect.left()) - int(rect.left()) % step
        top = int(rect.top()) - int(rect.top()) % step
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                painter.drawPoint(x, y)
                y += step
            x += step

class ObsidianView(QGraphicsView):

    def __init__(self, scene: ObsidianScene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.setStyleSheet('QGraphicsView { background: rgba(250,246,238,255); border: none; }')
        self._zoom = 1.0

    def wheelEvent(self, event):
        factor = 1.12 if event.angleDelta().y() > 0 else 0.89
        self._zoom *= factor
        self.scale(factor, factor)

    def fit_graph(self):
        rect = self.scene().itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            return
        self.fitInView(rect.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()

class GraphEdge(QGraphicsLineItem):

    def __init__(self, source: 'GraphNode', dest: 'GraphNode', strong: bool = False, relation: str = 'related'):
        super().__init__()
        self.source = source
        self.dest = dest
        self.strong = strong
        self.relation = relation
        self.setZValue(-2)
        if relation == 'mentions_persona' or self.source.is_persona or self.dest.is_persona:
            color = QColor(156, 104, 230, 170)
        elif relation == 'ai_related':
            color = QColor(201, 168, 76, 110)
        else:
            color = QColor(201, 168, 76, 125 if strong else 80)
        pen = QPen(color, 1.35 if relation == 'mentions_persona' else (1.25 if strong else 0.95))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        if not strong:
            pen.setStyle(Qt.PenStyle.DotLine)
        self.setPen(pen)
        self.source.edges.append(self)
        self.dest.edges.append(self)
        self.update_position()

    def update_position(self):
        self.setLine(self.source.x(), self.source.y(), self.dest.x(), self.dest.y())

class GraphNode(QGraphicsEllipseItem):

    def __init__(self, x: float, y: float, item: dict):
        relevance = max(1, min(100, int(item.get('relevance_score', 50))))
        self.is_persona = _is_persona_item(item)
        self.persona_related = bool(item.get('_persona_related', False))
        radius = int(12 + relevance / 100 * 18) if self.is_persona else int(9 + relevance / 100 * 18)
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.radius = radius
        self.item = item
        self.node_id = item.get('id')
        self.edges = []
        self.vx = random.uniform(-0.4, 0.4)
        self.vy = random.uniform(-0.4, 0.4)
        self.fx = 0.0
        self.fy = 0.0
        self._hover = False
        self._selected = False
        self.on_selected = None
        self.setPos(x, y)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(1)
        if self.is_persona:
            color = _node_color('persona')
        elif self.persona_related:
            color = _node_color('persona_related')
        else:
            color = _node_color(item.get('source', 'manual'))
        self.base_color = color
        self.setPen(QPen(QColor(201, 168, 76, 170), 1.2))
        self.setBrush(QBrush(color))
        title = item.get('title') or item.get('subject') or item.get('ai_summary') or 'Memoria'
        label = QGraphicsTextItem(_short_label(title), self)
        label.setDefaultTextColor(QColor(42, 30, 8, 205))
        label.setFont(QFont(FONT, 8))
        bw = label.boundingRect().width()
        label.setPos(-bw / 2, radius + 4)
        self.label = label
        source = 'Persona' if self.is_persona else (item.get('source') or 'manual').title()
        preview = (item.get('body') or item.get('body_preview') or '').strip()
        tooltip = f"<b>{title}</b><br/>Fonte: {source}<br/>Relevancia: {relevance}/100"
        if preview:
            tooltip += f"<hr/>{preview[:180]}"
        self.setToolTip(tooltip)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.radius
        if self._hover or self._selected:
            glow = QRadialGradient(0, 0, r + 16)
            glow.setColorAt(0.0, QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), 95))
            glow.setColorAt(1.0, QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(0, 0), r + 14, r + 14)
        body = QRadialGradient(-r * 0.35, -r * 0.35, r * 1.5)
        body.setColorAt(0.0, self.base_color.lighter(132))
        body.setColorAt(0.75, self.base_color)
        body.setColorAt(1.0, self.base_color.darker(112))
        if self.is_persona:
            border = QColor(185, 130, 255, 235)
            width = 1.9
        elif self.persona_related:
            border = QColor(185, 130, 255, 235) if self._hover else QColor(176, 116, 230, 190)
            width = 1.45
        else:
            border = C_GOLD_BRIGHT if self._hover else C_GOLD
            width = 1.5 if self._hover else 1.0
        painter.setPen(QPen(border, width))
        painter.setBrush(body)
        painter.drawEllipse(QPointF(0, 0), r, r)
        if self._selected:
            painter.setPen(QPen(QColor(42, 30, 8, 170), 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r + 4, r + 4)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_position()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._hover = True
        self.setZValue(5)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.setZValue(1)
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        if event.button() == Qt.MouseButton.LeftButton and callable(self.on_selected):
            self.on_selected(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

class ObsidianForce:
    """Fisica continua, leve e parecida com o grafo do Obsidian."""

    def __init__(self):
        self.repulsion = 3600.0
        self.center_pull = 0.01
        self.spring_k = 0.025
        self.spring_len = 115.0
        self.damping = 0.88
        self.max_speed = 10.0

    def step(self, nodes: list[GraphNode], edges: list[GraphEdge]):
        if not nodes:
            return
        for node in nodes:
            node.fx = 0.0
            node.fy = 0.0
        for i in range(len(nodes)):
            a = nodes[i]
            for j in range(i + 1, len(nodes)):
                b = nodes[j]
                dx = a.x() - b.x()
                dy = a.y() - b.y()
                dist_sq = dx * dx + dy * dy
                if dist_sq < 4:
                    dx = random.uniform(-1, 1)
                    dy = random.uniform(-1, 1)
                    dist_sq = dx * dx + dy * dy + 4
                dist = math.sqrt(dist_sq)
                force = self.repulsion / dist_sq
                fx = dx / dist * force
                fy = dy / dist * force
                a.fx += fx
                a.fy += fy
                b.fx -= fx
                b.fy -= fy
        for edge in edges:
            a, b = edge.source, edge.dest
            dx = b.x() - a.x()
            dy = b.y() - a.y()
            dist = math.hypot(dx, dy)
            if dist < 0.1:
                continue
            length = self.spring_len * (0.88 if edge.strong else 1.12)
            force = (dist - length) * self.spring_k
            fx = dx / dist * force
            fy = dy / dist * force
            a.fx += fx
            a.fy += fy
            b.fx -= fx
            b.fy -= fy
        scene = nodes[0].scene()
        grabbed = scene.mouseGrabberItem() if scene else None
        for node in nodes:
            if node.is_persona:
                target_x, target_y = (-175, 0)
                node.fx += (target_x - node.x()) * 0.04
                node.fy += (target_y - node.y()) * 0.04
            else:
                node.fx += (85 - node.x()) * self.center_pull
                node.fy += -node.y() * self.center_pull
            if node is grabbed:
                node.vx = 0
                node.vy = 0
                continue
            node.vx = (node.vx + node.fx) * self.damping
            node.vy = (node.vy + node.fy) * self.damping
            speed = math.hypot(node.vx, node.vy)
            if speed > self.max_speed:
                node.vx = node.vx / speed * self.max_speed
                node.vy = node.vy / speed * self.max_speed
            if speed < 0.018 and not node.is_persona:
                node.vx += random.uniform(-0.015, 0.015)
                node.vy += random.uniform(-0.015, 0.015)
            node.setPos(node.x() + node.vx, node.y() + node.vy)

class GraphTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._persistent_edges = []
        self._last_hash = None
        self._nodes = []
        self._edges = []
        self._selected = None
        self._force = ObsidianForce()
        self._fit_done = False
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._physics_step)
        self._timer.start(16)
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.addWidget(IconWidget('graph', 16))
        title = QLabel('GRAFO DE MEMORIA')
        title.setStyleSheet(LABEL_SECTION)
        self.status = QLabel('')
        self.status.setStyleSheet(f"color: {GOLD_BRIGHT_CSS}; font-size: 11px; font-family: {FONT}; font-style: italic;")
        self.stats = QLabel('')
        self.stats.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 10px; font-family: {FONT};")
        fit_btn = IconButton('fit', 28, 'Centralizar')
        fit_btn.clicked.connect(self._fit_graph)
        header.addWidget(title)
        header.addSpacing(8)
        header.addWidget(self.status)
        header.addStretch()
        header.addWidget(self.stats)
        header.addWidget(fit_btn)
        layout.addLayout(header)
        self.scene = ObsidianScene()
        self.view = ObsidianView(self.scene)
        layout.addWidget(self.view, 1)
        self.info = QLabel('Roxo = Persona. Clique em uma memória para ver detalhes. Arraste nós e use scroll para zoom.')
        self.info.setWordWrap(True)
        self.info.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 10px; font-family: {FONT};")
        layout.addWidget(self.info)

    def _physics_step(self):
        self._force.step(self._nodes, self._edges)

    def _fit_graph(self):
        self.view.fit_graph()

    def refresh(self):
        from core.database import SeqDB
        graph = SeqDB.get_instance().get_knowledge_graph(limit=80)
        items = graph['nodes']
        self._persistent_edges = graph['edges']
        current_hash = hash(str([(i.get('id'), i.get('relevance_score'), i.get('updated_at')) for i in items] + [(e.get('source_id'), e.get('target_id'), e.get('relation'), e.get('updated_at')) for e in self._persistent_edges]))
        if current_hash != self._last_hash:
            self._last_hash = current_hash
            self._build_graph(items)
            return
        self._build_graph(items)

    def _build_graph(self, items: list[dict]):
        self.scene.clear()
        self._nodes = []
        self._edges = []
        self._selected = None
        self.info.setText('Roxo = Persona. Clique em uma memória para ver detalhes. Arraste nós e use scroll para zoom.')
        persona_title = self.scene.addText('PERSONA')
        persona_title.setDefaultTextColor(QColor(126, 75, 205, 150))
        persona_title.setFont(QFont(FONT, 9, QFont.Weight.Bold))
        persona_title.setPos(-235, -130)
        memory_title = self.scene.addText('MEMÓRIAS')
        memory_title.setDefaultTextColor(QColor(150, 120, 55, 135))
        memory_title.setFont(QFont(FONT, 9, QFont.Weight.Bold))
        memory_title.setPos(20, -130)
        if not items:
            empty = self.scene.addText('Nenhuma memoria ainda.')
            empty.setDefaultTextColor(QColor(140, 110, 50))
            empty.setFont(QFont(FONT, 11))
            self.stats.setText('')
            return
        node_by_id = {}
        persona_items = [i for i in items if _is_persona_item(i)]
        memory_items = [i for i in items if not _is_persona_item(i)]
        persona_related_ids = set()
        for edge_def in self._persistent_edges:
            if edge_def.get('relation') != 'mentions_persona':
                continue
            a, b = str(edge_def.get('source_id')), str(edge_def.get('target_id'))
            if a.startswith('persona:') and not b.startswith('persona:'):
                persona_related_ids.add(b)
                continue
            if b.startswith('persona:') and not a.startswith('persona:'):
                persona_related_ids.add(a)
        if persona_items:
            core_item = {'id': 'persona:core', 'source': 'persona', 'node_type': 'persona', 'title': 'Persona', 'subject': 'Persona', 'body': 'Identidade e preferências do usuário', 'body_preview': 'Identidade e preferências do usuário', 'ai_summary': 'Persona', 'relevance_score': 100}
            core_node = GraphNode(-175, 0, core_item)
            core_node.on_selected = self._select_node
            self.scene.addItem(core_node)
            self._nodes.append(core_node)
            node_by_id[core_item['id']] = core_node
            count_p = len(persona_items)
            for idx, item in enumerate(persona_items):
                angle = idx / max(1, count_p) * math.tau
                x = -175 + math.cos(angle) * 72
                y = math.sin(angle) * 72
                node = GraphNode(x, y, item)
                node.on_selected = self._select_node
                self.scene.addItem(node)
                self._nodes.append(node)
                node_by_id[item['id']] = node
                self._add_edge(core_node, node, strong=True)
        count = max(1, len(memory_items))
        radius = 90 + min(190, count * 12)
        for idx, item in enumerate(memory_items):
            item = {**item, **{'_persona_related': item.get('id') in persona_related_ids}}
            angle = idx / count * math.tau
            rel = max(1, min(100, int(item.get('relevance_score', 50))))
            jitter = random.uniform(-22, 22)
            dist = radius * (1.12 - rel / 180) + jitter
            x = 85 + math.cos(angle) * dist
            y = math.sin(angle) * dist
            node = GraphNode(x, y, item)
            node.on_selected = self._select_node
            self.scene.addItem(node)
            self._nodes.append(node)
            node_by_id[item['id']] = node
        seen_pairs = set()
        for edge_def in self._persistent_edges:
            a, b = edge_def.get('source_id'), edge_def.get('target_id')
            relation = edge_def.get('relation', 'related')
            if a == 'persona:core' or b == 'persona:core':
                continue
            key = tuple(sorted((str(a), str(b), relation)))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if a in node_by_id and b in node_by_id and (a != b):
                strong = relation in ('ai_related', 'mentions_persona')
                self._add_edge(node_by_id[a], node_by_id[b], strong=strong, relation=relation)
        self.stats.setText(f"{len(self._nodes)} nós · {len(self._edges)} conexões")
        if not self._fit_done:
            self._fit_done = True
            QTimer.singleShot(250, self._fit_graph)

    def _add_edge(self, a: GraphNode, b: GraphNode, strong: bool = False, relation: str = 'related'):
        edge = GraphEdge(a, b, strong=strong, relation=relation)
        self.scene.addItem(edge)
        self._edges.append(edge)

    def _select_node(self, node: GraphNode):
        if self._selected is not node:
            if self._selected:
                self._selected.set_selected(False)
        self._selected = node
        node.set_selected(True)
        item = node.item
        title = item.get('title') or item.get('subject') or item.get('ai_summary') or 'Memória'
        source = 'Persona' if _is_persona_item(item) else (item.get('source') or 'manual').title()
        score = item.get('relevance_score', 50)
        saved = (item.get('updated_at') or item.get('saved_at') or '')[:10]
        preview = (item.get('body') or item.get('body_preview') or '').strip()
        meta = f"<b>{title}</b> · {source} · relevância {score}/100"
        if saved:
            meta += f" · {saved}"
        if preview:
            meta += f"<br/>{preview[:220]}"
        self.info.setText(meta)
