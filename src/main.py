import sys
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np
import pymupdf
from pymupdf import Page
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


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

        # Load the document
        self.load_pdf()

        # Initial Params
        self.x_scroll_offset: int = 0
        self.y_scroll_offset: int = 0
        self.zoom: float = 1
        self.mode: str = "normal"  # normal, caret, visual

        # Assign keybinds
        self.set_keybinds()
        self.change_mode("normal")

        self.pages: List[Dict[str, Any]] = []
        self.extract_all_characters()

        self.ROW_TOLERANCE = 3
        self.cluster_rows()

        self.current_character = self.get_character(0, 0, 0)

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

    def load_pdf(self):
        self.doc = pymupdf.open(sys.argv[1])
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

            matrix = pymupdf.Matrix(self.zoom, self.zoom)
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

            assert self.current_character is not None
            character_on_this_page = self.current_character.page == i
            if self.mode == "caret" and character_on_this_page:
                self.highlight_character(
                    painter, self.current_character, draw_x, draw_y
                )

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

    def set_keybinds(self):
        self.normal_keybinds: list[QShortcut] = []
        self.caret_keybinds: list[QShortcut] = []
        self.visual_keybinds: list[QShortcut] = []

        # ====== NORMAL MODE ====== #
        # Change mode
        enter_caret = QShortcut(QKeySequence("V"), self)
        enter_caret.activated.connect(self.enter_caret)

        # Movement
        move_left = QShortcut(QKeySequence("H"), self)
        move_left.activated.connect(self.move_left)
        move_down = QShortcut(QKeySequence("J"), self)
        move_down.activated.connect(self.move_down)
        move_up = QShortcut(QKeySequence("K"), self)
        move_up.activated.connect(self.move_up)
        move_right = QShortcut(QKeySequence("L"), self)
        move_right.activated.connect(self.move_right)

        # Move Page
        half_page_down = QShortcut(QKeySequence("Ctrl+D"), self)
        half_page_down.activated.connect(self.half_page_down)

        half_page_up = QShortcut(QKeySequence("Ctrl+U"), self)
        half_page_up.activated.connect(self.half_page_up)

        # Zoom
        reset_zoom = QShortcut(QKeySequence("Equals"), self)
        reset_zoom.activated.connect(self.reset_zoom)

        zoom_in = QShortcut(QKeySequence("Ctrl+Shift+="), self)
        zoom_in.activated.connect(self.zoom_in)

        zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        zoom_out.activated.connect(self.zoom_out)

        move_to_bottom = QShortcut(QKeySequence("Shift+G"), self)
        move_to_bottom.activated.connect(self.move_to_bottom)

        self.normal_keybinds.extend(
            [
                move_left,
                move_up,
                move_down,
                move_right,
                half_page_down,
                half_page_up,
                reset_zoom,
                zoom_in,
                zoom_out,
                move_to_bottom,
            ]
        )

        # ====== CARET MODE ====== #
        exit_caret = QShortcut(QKeySequence("Escape"), self)
        exit_caret.activated.connect(self.exit_caret)

        # Movement
        caret_move_left = QShortcut(QKeySequence("H"), self)
        caret_move_left.activated.connect(self.move_left)
        caret_move_down = QShortcut(QKeySequence("J"), self)
        caret_move_down.activated.connect(self.move_down)
        caret_move_up = QShortcut(QKeySequence("K"), self)
        caret_move_up.activated.connect(self.move_up)
        caret_move_right = QShortcut(QKeySequence("L"), self)
        caret_move_right.activated.connect(self.move_right)

        self.caret_keybinds.extend(
            [
                caret_move_left,
                caret_move_up,
                caret_move_down,
                caret_move_right,
            ]
        )

        # Initially disable all keybinds
        for shortcut in (
            self.normal_keybinds + self.caret_keybinds + self.visual_keybinds
        ):
            shortcut.setEnabled(False)

    def enter_caret(self):
        self.mode = "caret"
        self.render_pdf()

    def exit_caret(self):
        self.mode = "normal"
        self.render_pdf()

    def highlight_character(
        self,
        painter: QPainter,
        character: Character,
        page_draw_x: int,
        page_draw_y: int,
    ):
        """
        Highlights a character
        """
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

    def get_character(
        self, page_index: int, row_index: int, column_index: int
    ) -> Character | None:
        """
        Access a character from row and column index
        """

        page_characters = self.pages[page_index]["Characters"]

        selected_character: Character | None = None

        for character in page_characters:

            if character.row == row_index and character.column == column_index:
                selected_character = character

            else:
                continue

        # Except if we can't find a character
        if selected_character is None:
            return None

        return selected_character

    def cluster_rows(self):
        """
        Not all characters on (visual) rows may not be on the exact same y
        value. We hence need to define our rows based on clusters of character
        y values.
        """

        # First sort all characters on each page by y value
        for page in self.pages:
            # Each page contains a list of character dictionaries
            page["Characters"].sort(key=lambda char: char.y)

            page["Rows"] = []

            # Iterrate through each character and add them to rows.
            for char in page["Characters"]:
                placed = False

                for row in page["Rows"]:

                    # Look through rows for characters with similar y values to
                    # this character.
                    if abs(row["y"] - char.y) < self.ROW_TOLERANCE:
                        row["Characters"].append(char)

                        # Define a row y coordinate based on the average of all
                        # current characters in this row.
                        row["y"] = np.mean([c.y for c in row["Characters"]])

                        placed = True
                        break

                # If we can't find a similar row, create a new row.
                if not placed:
                    page["Rows"].append({"y": char.y, "Characters": [char]})

            # Lastly, we need to sort each row in x, and give each an index.
            for row in page["Rows"]:
                row["Characters"].sort(key=lambda char: char.x)

            for row_index, row in enumerate(page["Rows"]):
                for column_index, character in enumerate(row["Characters"]):
                    character.row = row_index
                    character.column = column_index

    def extract_all_characters(self):
        # We need to loop through every character in the document.
        # Our selection could be on any page...
        page_id: int = 0
        page: Page
        for page in self.doc:
            page_dict = page.get_text("rawdict")
            assert isinstance(page_dict, Dict)

            page_characters: List[Character] = []

            # ...in any block...
            blocks: List[Dict[str, Any]] = page_dict["blocks"]
            for block in blocks:
                # ...on any line...
                # Keys: type, number, flags, bbox, lines
                line: Dict[str, Any]
                # Not all blocks have lines, e.g. figures, tables, so we use
                # the get method to return an empty list in those cases.
                for line in block.get("lines", []):

                    # ...in any span... (wtf is a span???)
                    # Keys: spans, wmode, dir, bbox
                    span: Dict[str, Any]
                    for span in line["spans"]:

                        # ...in any character...
                        # (oh wait this is what we want!)
                        character_dict: Dict[str, Any]
                        for character_dict in span["chars"]:

                            # Keys: origin, bbox, c, synthetic
                            x0, y0, x1, y1 = character_dict["bbox"]
                            page_characters.append(
                                Character(
                                    char=character_dict["c"],
                                    page=page_id,
                                    bbox=character_dict["bbox"],
                                    x=x0,
                                    y=y0,  # y local to the page not the document
                                    width=x1 - x0,
                                    height=y1 - y0,
                                )
                            )

            self.pages.append({"Characters": page_characters})
            page_id += 1

    def get_new_character(
        self, current_character: Character, delta: Tuple[int, int]
    ) -> Character | None:
        """
        Get a new character based on the current character and the motion delta.
        """

        current_page = current_character.page
        current_row = current_character.row
        current_column = current_character.column

        # If it is a simple jump, do that
        new_character = self.get_character(
            current_page, current_row + delta[0], current_column + delta[1]
        )

        if new_character is not None:
            return new_character

        # If not, we need to do some checks to determine where we should be
        # going.

        match delta:

            # Currently I'm just gonna write some clauses, but ideally this
            # would be generic to any delta input for maximum functionality.
            # This will be useful for things like half page down etc.
            case (1, 0):
                # Trying to move down.
                # If we fail to move down, we are either at the bottom of the
                # page, or the row below is shorter than the current row. We
                # can tell the difference by attempting to index the row below.
                try:
                    row_below = self.pages[current_page]["Rows"][current_row + 1]

                except IndexError:
                    # If we have an error, we know we just want to go to the
                    # next page. We can do some fancy recursion :)
                    new_character = deepcopy(current_character)
                    new_character.page += 1

                    # Reset to the first row and column of the new page This is
                    # actually setting it to one before the first row, which
                    # doesn't exist, but makes for nice recursion here.
                    new_character.row = -1

                    return self.get_new_character(new_character, delta)

                # Otherwise, we are just trying to move to a row with less
                # columns. We can return the last character of the next row
                new_row = current_character.row + 1
                new_column = row_below["Characters"][-1].column

                new_character = self.get_character(current_page, new_row, new_column)

                return new_character

            case (-1, 0):
                # Trying to move up.
                # If we fail to move up, we are either at the top of the
                # page, or the row above is shorter than the current row.
                # We can tell the difference by attempting to index the row above.
                try:
                    row_above = self.pages[current_page]["Rows"][current_row - 1]

                    # If current_row is 0, this will incorrectly wrap to -1,
                    # so we explicitly guard against that case.
                    if current_row == 0:
                        raise IndexError

                except IndexError:
                    # If we have an error, we know we just want to go to the
                    # previous page. We can do some fancy recursion :)
                    new_character = deepcopy(current_character)
                    new_character.page -= 1

                    # Reset to the first row and column of the new page. Again,
                    # this is actually setting it to one after the last row,
                    # which doesn't exist, but makes for nice recursion here.
                    new_character.row = len(self.pages[current_page - 1]["Rows"])

                    return self.get_new_character(new_character, delta)

                # Otherwise, we are just trying to move to a row with less
                # columns. We can return the last character of the previous row
                new_row = current_character.row - 1
                new_column = row_above["Characters"][-1].column

                new_character = self.get_character(current_page, new_row, new_column)

                return new_character

            case _:
                raise ValueError("Incorrect input for 'delta'")

    def move_down(self):
        if self.mode == "normal":
            self.scroll_pdf(y_delta=self.move_speed)

        elif self.mode == "caret":
            assert self.current_character is not None

            new_character = self.get_new_character(self.current_character, (1, 0))
            if new_character is not None:
                self.current_character = new_character

            self.render_pdf()

    def move_up(self):
        if self.mode == "normal":
            self.scroll_pdf(y_delta=-self.move_speed)

        elif self.mode == "caret":
            assert self.current_character is not None

            new_character = self.get_new_character(self.current_character, (-1, 0))
            if new_character is not None:
                self.current_character = new_character

            self.render_pdf()

    def move_left(self):
        if self.mode == "normal":
            self.scroll_pdf(x_delta=self.move_speed)

        elif self.mode == "caret":
            assert self.current_character is not None
            current_page = self.current_character.page
            current_row = self.current_character.row
            current_column = self.current_character.column

            new_character = self.get_character(
                current_page, current_row, current_column - 1
            )

            if new_character is not None:
                self.current_character = new_character
                self.render_pdf()

    def move_right(self):
        if self.mode == "normal":
            self.scroll_pdf(x_delta=-self.move_speed)

        elif self.mode == "caret":
            assert self.current_character is not None
            current_page = self.current_character.page
            current_row = self.current_character.row
            current_column = self.current_character.column

            new_character = self.get_character(
                current_page, current_row, current_column + 1
            )

            if new_character is not None:
                self.current_character = new_character
                self.render_pdf()

    def half_page_down(self):
        self.scroll_pdf(y_delta=int(self.page_height / 2))

    def half_page_up(self):
        self.scroll_pdf(y_delta=-int(self.page_height / 2))

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
