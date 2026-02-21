import sys

import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class Window(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.move_speed: int = 60  # in pixels
        self.page_gap: int = 5  # in pixels
        self.zoom_rate: float = 0.1

        self.label = QLabel(self)
        self.label.setScaledContents(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.load_pdf()

        self.x_scroll_offset: int = 0
        self.y_scroll_offset: int = 0
        self.zoom: float = 1

        self.render_pdf()

        # Movement
        shortcut_move_left = QShortcut(QKeySequence("H"), self)
        shortcut_move_left.activated.connect(self.move_left)
        shortcut_move_down = QShortcut(QKeySequence("J"), self)
        shortcut_move_down.activated.connect(self.move_down)
        shortcut_move_up = QShortcut(QKeySequence("K"), self)
        shortcut_move_up.activated.connect(self.move_up)
        shortcut_move_right = QShortcut(QKeySequence("L"), self)
        shortcut_move_right.activated.connect(self.move_right)

        # Move Page
        shortcut_half_page_down = QShortcut(QKeySequence("Ctrl+D"), self)
        shortcut_half_page_down.activated.connect(self.half_page_down)

        shortcut_half_page_up = QShortcut(QKeySequence("Ctrl+U"), self)
        shortcut_half_page_up.activated.connect(self.half_page_up)

        # Zoom
        shortcut_reset_zoom = QShortcut(QKeySequence("Equals"), self)
        shortcut_reset_zoom.activated.connect(self.reset_zoom)

        shortcut_zoom_in = QShortcut(QKeySequence("Ctrl+Shift+="), self)
        shortcut_zoom_in.activated.connect(self.zoom_in)

        shortcut_zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        shortcut_zoom_out.activated.connect(self.zoom_out)

        shortcut_move_to_bottom = QShortcut(QKeySequence("Shift+G"), self)
        shortcut_move_to_bottom.activated.connect(self.move_to_bottom)

    def load_pdf(self):
        self.doc = fitz.open(sys.argv[1])
        self.calculate_page_positions()

    def calculate_page_positions(self):
        self.page_positions = []
        self.total_height = 0

        for page in self.doc:
            h = int(page.rect.height)
            self.page_height = h
            self.page_positions.append((self.total_height, h))
            self.total_height += h

    def render_pdf(self):
        viewport_h = self.label.height()
        viewport_w = self.label.width()

        canvas = QImage(viewport_w, viewport_h, QImage.Format.Format_RGB888)
        canvas.fill(Qt.GlobalColor.lightGray)

        painter = QPainter(canvas)

        visible_top = self.y_scroll_offset
        visible_bottom = self.y_scroll_offset + viewport_h

        for i, (page_y, page_h) in enumerate(self.page_positions):

            # We need to scale to account for zoom level
            scaled_page_y = int(page_y * self.zoom) + i * self.page_gap

            page_bottom = page_y + page_h

            # Skip pages not visible
            if page_bottom < visible_top:
                continue
            if scaled_page_y > visible_bottom:
                break

            page = self.doc[i]

            matrix = fitz.Matrix(self.zoom, self.zoom)
            pix = page.get_pixmap(matrix=matrix)

            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            )

            # Centre pdf in window
            draw_x = (viewport_w - img.width()) // 2 + self.x_scroll_offset
            draw_y = scaled_page_y - visible_top + i * int(self.page_gap * self.zoom)
            painter.drawImage(draw_x, draw_y, img)

        painter.end()

        self.label.setPixmap(QPixmap.fromImage(canvas))

    def scroll_pdf(self, x_delta: int = 0, y_delta: int = 0):
        self.x_scroll_offset += x_delta
        self.y_scroll_offset += y_delta
        self.clamp_scroll()
        self.render_pdf()

    def clamp_scroll(self):
        y_max_scroll = max(0, self.total_height - self.label.height())
        self.y_scroll_offset = max(0, min(self.y_scroll_offset, y_max_scroll))

    def half_page_down(self):
        self.scroll_pdf(y_delta=self.page_height / 2)

    def half_page_up(self):
        self.scroll_pdf(y_delta=-self.page_height / 2)

    def move_down(self):
        self.scroll_pdf(y_delta=self.move_speed)

    def move_up(self):
        self.scroll_pdf(y_delta=-self.move_speed)

    def move_left(self):
        self.scroll_pdf(x_delta=self.move_speed)

    def move_right(self):
        self.scroll_pdf(x_delta=-self.move_speed)

    def zoom_in(self):
        self.zoom += self.zoom_rate
        self.render_pdf()

    def zoom_out(self):
        self.zoom -= self.zoom_rate
        self.render_pdf()

    def reset_zoom(self):
        self.zoom = 1
        self.render_pdf()

    def move_to_top(self):
        self.y_scroll_offset = 0
        self.render_pdf()

    def move_to_bottom(self):
        self.y_scroll_offset = self.total_height - self.page_height
        self.render_pdf()

    # Ensure that the pdf is updated on window resize
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_pdf()


if __name__ == "__main__":
    app = QApplication([])
    window = Window()
    window.show()
    app.exec()
