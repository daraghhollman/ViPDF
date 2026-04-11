import sys
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np
import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from keybinds import CARET_KEYBINDS, NORMAL_KEYBINDS


@dataclass
class Character:
    char: str
    page: int
    bbox: tuple[float, float, float, float]
    x: float
    y: float
    width: float
    height: float
    row: int = 0
    column: int = 0


class PDFDocument:
    ROW_TOLERANCE = 3

    def __init__(self, path: str):
        self.doc = pymupdf.open(path)
        self.pages: List[Dict[str, Any]] = []
        self._calculate_page_positions()
        self._extract_all_characters()
        self._cluster_rows()

    def _calculate_page_positions(self):
        self.page_positions = []
        self.total_height = 0
        self.page_heights: List[int] = []

        for page in self.doc:
            h = int(page.rect.height)
            self.page_heights.append(h)
            self.page_positions.append((self.total_height, h))
            self.total_height += h

    def _extract_all_characters(self):
        for page_id, page in enumerate(self.doc):  # type: ignore[arg-type]
            page_dict = page.get_text("rawdict")
            assert isinstance(page_dict, Dict)

            page_characters: List[Character] = []

            blocks: List[Dict[str, Any]] = page_dict["blocks"]
            for block in blocks:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        character_dict: Dict[str, Any]
                        for character_dict in span["chars"]:
                            x0, y0, x1, y1 = character_dict["bbox"]
                            page_characters.append(
                                Character(
                                    char=character_dict["c"],
                                    page=page_id,
                                    bbox=character_dict["bbox"],
                                    x=x0,
                                    y=y0,
                                    width=x1 - x0,
                                    height=y1 - y0,
                                )
                            )

            self.pages.append({"Characters": page_characters})

    def _cluster_rows(self):
        for page in self.pages:
            page["Characters"].sort(key=lambda char: char.y)
            page["Rows"] = []

            for char in page["Characters"]:
                placed = False
                for row in page["Rows"]:
                    if abs(row["y"] - char.y) < self.ROW_TOLERANCE:
                        row["Characters"].append(char)
                        row["y"] = np.mean([c.y for c in row["Characters"]])
                        placed = True
                        break
                if not placed:
                    page["Rows"].append({"y": char.y, "Characters": [char]})

            for row in page["Rows"]:
                row["Characters"].sort(key=lambda char: char.x)

            for row_index, row in enumerate(page["Rows"]):
                for column_index, character in enumerate(row["Characters"]):
                    character.row = row_index
                    character.column = column_index

    def get_character(
        self, page_index: int, row_index: int, column_index: int
    ) -> Character | None:
        for character in self.pages[page_index]["Characters"]:
            if character.row == row_index and character.column == column_index:
                return character
        return None

    def get_new_character(
        self, current_character: Character | None, delta: Tuple[int, int]
    ) -> Character | None:

        if current_character is None:
            return None

        current_page = current_character.page
        current_row = current_character.row
        current_column = current_character.column

        new_character = self.get_character(
            current_page, current_row + delta[0], current_column + delta[1]
        )
        if new_character is not None:
            return new_character

        match delta:
            case (1, 0):
                try:
                    row_below = self.pages[current_page]["Rows"][current_row + 1]
                except IndexError:
                    new_character = deepcopy(current_character)
                    new_character.page += 1
                    new_character.row = -1
                    return self.get_new_character(new_character, delta)

                new_row = current_character.row + 1
                new_column = row_below["Characters"][-1].column
                return self.get_character(current_page, new_row, new_column)

            case (-1, 0):
                try:
                    row_above = self.pages[current_page]["Rows"][current_row - 1]
                    if current_row == 0:
                        raise IndexError
                except IndexError:
                    new_character = deepcopy(current_character)
                    new_character.page -= 1
                    new_character.row = len(self.pages[current_page - 1]["Rows"])
                    return self.get_new_character(new_character, delta)

                new_row = current_character.row - 1
                new_column = row_above["Characters"][-1].column
                return self.get_character(current_page, new_row, new_column)

            case _:
                raise ValueError("Incorrect input for 'delta'")


class Window(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # Config parameters
        self.move_speed: int = 60  # in pixels
        self.page_gap: int = 5  # in pixels
        self.zoom_rate: float = 0.1

        # Layout things
        self.label = QLabel(self)
        self.label.setScaledContents(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.pdf = PDFDocument(sys.argv[1])
        self.caret = CaretNavigator(self.pdf)

        # Initial Params
        self.x_scroll_offset: int = 0
        self.y_scroll_offset: int = 0
        self.zoom: float = 1
        self.mode: str = "normal"  # normal, caret, visual

        # Assign keybinds
        self.set_keybinds()
        self.change_mode("normal")

        # Render the pdf
        self.render_pdf()

    def change_mode(self, mode: str):

        if mode == "normal":
            for shortcut in self.normal_keybinds:
                shortcut.setEnabled(True)

            for shortcut in self.caret_keybinds + self.visual_keybinds:
                shortcut.setEnabled(False)

        elif mode == "caret":
            for shortcut in self.caret_keybinds:
                shortcut.setEnabled(True)

            for shortcut in self.normal_keybinds + self.visual_keybinds:
                shortcut.setEnabled(False)

        elif mode == "visual":
            for shortcut in self.visual_keybinds:
                shortcut.setEnabled(True)

            for shortcut in self.normal_keybinds + self.caret_keybinds:
                shortcut.setEnabled(False)

        else:
            raise ValueError(f"Unknown mode: {mode}")

        self.mode = mode

    def render_pdf(self):
        viewport_h = self.label.height()
        viewport_w = self.label.width()

        canvas = QImage(viewport_w, viewport_h, QImage.Format.Format_RGB888)
        canvas.fill(Qt.GlobalColor.lightGray)

        painter = QPainter(canvas)

        visible_top = self.y_scroll_offset
        visible_bottom = self.y_scroll_offset + viewport_h

        for i, (page_y, page_h) in enumerate(self.pdf.page_positions):

            scaled_page_y = int(page_y * self.zoom) + i * self.page_gap
            page_bottom = page_y + page_h

            if page_bottom < visible_top:
                continue
            if scaled_page_y > visible_bottom:
                break

            page = self.pdf.doc[i]
            matrix = pymupdf.Matrix(self.zoom, self.zoom)
            pix = page.get_pixmap(matrix=matrix)

            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            )

            draw_x = (viewport_w - img.width()) // 2 + self.x_scroll_offset
            draw_y = scaled_page_y - visible_top + i * int(self.page_gap * self.zoom)
            painter.drawImage(draw_x, draw_y, img)

            if (
                self.mode == "caret"
                and self.caret.current_character is not None
                and self.caret.current_character.page == i
            ):
                self.highlight_character(
                    painter, self.caret.current_character, draw_x, draw_y
                )

        painter.end()
        self.label.setPixmap(QPixmap.fromImage(canvas))

    def scroll_pdf(self, x_delta: int = 0, y_delta: int = 0):
        self.x_scroll_offset += x_delta
        self.y_scroll_offset += y_delta
        self.clamp_scroll()
        self.render_pdf()

    def clamp_scroll(self):
        y_max_scroll = max(0, self.pdf.total_height - self.label.height())
        self.y_scroll_offset = max(0, min(self.y_scroll_offset, y_max_scroll))

    def set_keybinds(self):
        self.normal_keybinds: list[QShortcut] = []
        self.caret_keybinds: list[QShortcut] = []
        self.visual_keybinds: list[QShortcut] = []

        for binds, shortcut_list in [
            (NORMAL_KEYBINDS, self.normal_keybinds),
            (CARET_KEYBINDS, self.caret_keybinds),
        ]:
            for key, action in binds:
                sc = QShortcut(QKeySequence(key), self)
                sc.activated.connect(getattr(self, action))
                shortcut_list.append(sc)

        # Initially disable all keybinds
        for shortcut in (
            self.normal_keybinds + self.caret_keybinds + self.visual_keybinds
        ):
            shortcut.setEnabled(False)

    def enter_caret(self):
        self.change_mode("caret")
        self.render_pdf()

    def exit_caret(self):
        self.change_mode("normal")
        self.render_pdf()

    def highlight_character(
        self,
        painter: QPainter,
        character: Character,
        page_draw_x: int,
        page_draw_y: int,
    ):
        x0, y0, x1, y1 = character.bbox

        scaled_x0 = x0 * self.zoom
        scaled_y0 = y0 * self.zoom
        scaled_w = (x1 - x0) * self.zoom
        scaled_h = (y1 - y0) * self.zoom

        screen_x = int(page_draw_x + scaled_x0)
        screen_y = int(page_draw_y + scaled_y0)

        painter.fillRect(
            screen_x,
            screen_y,
            int(scaled_w),
            int(scaled_h),
            QColor(255, 0, 0, 120),
        )

    def move_down(self):
        if self.mode == "normal":
            self.scroll_pdf(y_delta=self.move_speed)
        elif self.mode == "caret":
            self.caret.move((1, 0))
            self.render_pdf()

    def move_up(self):
        if self.mode == "normal":
            self.scroll_pdf(y_delta=-self.move_speed)
        elif self.mode == "caret":
            self.caret.move((-1, 0))
            self.render_pdf()

    def move_left(self):
        if self.mode == "normal":
            self.scroll_pdf(x_delta=self.move_speed)
        elif self.mode == "caret":
            self.caret.move_left()
            self.render_pdf()

    def move_right(self):
        if self.mode == "normal":
            self.scroll_pdf(x_delta=-self.move_speed)
        elif self.mode == "caret":
            self.caret.move_right()
            self.render_pdf()

    def half_page_down(self):
        self.scroll_pdf(y_delta=self.pdf.page_heights[0] // 2)

    def half_page_up(self):
        self.scroll_pdf(y_delta=-(self.pdf.page_heights[0] // 2))

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
        self.y_scroll_offset = self.pdf.total_height - self.pdf.page_heights[-1]
        self.render_pdf()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_pdf()


class CaretNavigator:

    def __init__(self, pdf: PDFDocument):
        self.pdf = pdf
        self.current_character = pdf.get_character(0, 0, 0)

    def move(self, delta: Tuple[int, int]):
        new = self.pdf.get_new_character(self.current_character, delta)
        if new is not None:
            self.current_character = new

    def move_left(self):
        if self.current_character is None:
            return

        c = self.current_character

        new = self.pdf.get_character(c.page, c.row, c.column - 1)
        if new is not None:
            self.current_character = new

    def move_right(self):
        if self.current_character is None:
            return

        c = self.current_character

        new = self.pdf.get_character(c.page, c.row, c.column + 1)
        if new is not None:
            self.current_character = new


def main():
    if len(sys.argv) == 1:
        print("ViPdf by Daragh Hollman")
        print("Usage: vipdf <file.pdf>")
        return

    app = QApplication([])
    window = Window()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
