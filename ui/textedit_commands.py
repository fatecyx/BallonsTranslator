from typing import List, Union, Tuple

from qtpy.QtGui import QTextCursor
from qtpy.QtCore import QPointF, QRectF
try:
    from qtpy.QtWidgets import QUndoCommand
except:
    from qtpy.QtGui import QUndoCommand

from .textitem import TextBlkItem, TextBlock
from .textedit_area import TransTextEdit, SourceTextEdit, TransPairWidget
from utils.fontformat import FontFormat
import utils.config as C
from .misc import doc_replace, doc_replace_no_shift
from .texteditshapecontrol import TextBlkShapeControl
from .page_search_widget import PageSearchWidget, Matched
from utils.proj_imgtrans import ProjImgTrans
from .scene_textlayout import PUNSET_HALF


def propagate_user_edit(src_edit: Union[TransTextEdit, TextBlkItem], target_edit: Union[TransTextEdit, TextBlkItem], pos: int, added_text: str, joint_previous: bool = False):
    ori_count = target_edit.document().characterCount()
    new_count = src_edit.document().characterCount()
    removed = ori_count + len(added_text) - new_count

    cursor = target_edit.textCursor()
    cursor.setPosition(pos)
    if joint_previous:
        cursor.joinPreviousEditBlock()
    else:
        cursor.beginEditBlock()
    if removed > 0:
        cursor.setPosition(pos + removed, QTextCursor.MoveMode.KeepAnchor)
    cursor.insertText(added_text)
    cursor.endEditBlock()
    target_edit.old_undo_steps = target_edit.document().availableUndoSteps()


class MoveBlkItemsCommand(QUndoCommand):
    def __init__(self, items: List[TextBlkItem], shape_ctrl: TextBlkShapeControl):
        super(MoveBlkItemsCommand, self).__init__()
        self.items = items
        self.old_pos_lst: List[QPointF] = []
        self.new_pos_lst: List[QPointF] = []
        self.shape_ctrl = shape_ctrl
        for item in items:
            padding = item.padding()
            padding = QPointF(padding, padding)
            self.old_pos_lst.append(item.oldPos + padding)
            self.new_pos_lst.append(item.pos() + padding)
            item.oldPos = item.pos()

    def redo(self):
        for item, new_pos in zip(self.items, self.new_pos_lst):
            padding = item.padding()
            padding = QPointF(padding, padding)
            item.setPos(new_pos - padding)
            if self.shape_ctrl.blk_item == item and self.shape_ctrl.pos() != new_pos:
                self.shape_ctrl.setPos(new_pos)

    def undo(self):
        for item, old_pos in zip(self.items, self.old_pos_lst):
            padding = item.padding()
            padding = QPointF(padding, padding)
            item.setPos(old_pos - padding)
            if self.shape_ctrl.blk_item == item and self.shape_ctrl.pos() != old_pos:
                self.shape_ctrl.setPos(old_pos)


class ApplyFontformatCommand(QUndoCommand):
    def __init__(self, items: List[TextBlkItem], trans_widget_lst: List[TransTextEdit], fontformat: FontFormat):
        super(ApplyFontformatCommand, self).__init__()
        self.items = items
        self.old_html_lst = []
        self.old_rect_lst = []
        self.old_fmt_lst = []
        self.new_fmt = fontformat
        self.trans_widget_lst = trans_widget_lst
        for item in items:
            self.old_html_lst.append(item.toHtml())
            self.old_fmt_lst.append(item.get_fontformat())
            self.old_rect_lst.append(item.absBoundingRect(qrect=True))

    def redo(self):
        for item, edit in zip(self.items, self.trans_widget_lst):
            item.set_fontformat(self.new_fmt, set_char_format=True)
            edit.document().clearUndoRedoStacks()

    def undo(self):
        for rect, item, html, fmt, edit in zip(self.old_rect_lst, self.items, self.old_html_lst, self.old_fmt_lst, self.trans_widget_lst):
            item.setHtml(html)
            item.set_fontformat(fmt)
            item.setRect(rect)
            edit.document().clearUndoRedoStacks()

    
class ReshapeItemCommand(QUndoCommand):
    def __init__(self, item: TextBlkItem):
        super(ReshapeItemCommand, self).__init__()
        self.item = item
        self.oldRect = item.oldRect
        self.newRect = item.absBoundingRect(qrect=True)
        self.idx = -1

    def redo(self):
        if self.idx < 0:
            self.idx += 1
            return
        self.item.setRect(self.newRect)

    def undo(self):
        self.item.setRect(self.oldRect)

    def mergeWith(self, command: QUndoCommand):
        item = command.item
        if self.item != item:
            return False
        self.newRect = item.rect()
        return True


class RotateItemCommand(QUndoCommand):
    def __init__(self, item: TextBlkItem, new_angle: float, shape_ctrl: TextBlkShapeControl):
        super(RotateItemCommand, self).__init__()
        self.item = item
        self.old_angle = item.rotation()
        self.new_angle = new_angle
        self.shape_ctrl = shape_ctrl

    def redo(self):
        self.item.setRotation(self.new_angle)
        self.item.blk.angle = self.new_angle
        if self.shape_ctrl.blk_item == self.item and self.shape_ctrl.rotation() != self.new_angle:
            self.shape_ctrl.setRotation(self.new_angle)

    def undo(self):
        self.item.setRotation(self.old_angle)
        self.item.blk.angle = self.old_angle
        if self.shape_ctrl.blk_item == self.item and self.shape_ctrl.rotation() != self.old_angle:
            self.shape_ctrl.setRotation(self.old_angle)

    def mergeWith(self, command: QUndoCommand):
        item = command.item
        if self.item != item:
            return False
        self.new_angle = item.angle
        return True


class AutoLayoutCommand(QUndoCommand):
    def __init__(self, items: List[TextBlkItem], old_rect_lst: List, old_html_lst: List, trans_widget_lst: List[TransTextEdit]):
        super(AutoLayoutCommand, self).__init__()
        self.items = items
        self.old_html_lst = old_html_lst
        self.old_rect_lst = old_rect_lst
        self.trans_widget_lst = trans_widget_lst
        self.new_rect_lst = []
        self.new_html_lst = []
        for item in items:
            self.new_html_lst.append(item.toHtml())
            self.new_rect_lst.append(item.absBoundingRect(qrect=True))
        self.counter = 0

    def redo(self):
        self.counter += 1
        if self.counter <= 1:
            return
        for item, trans_widget, html, rect  in zip(self.items, self.trans_widget_lst, self.new_html_lst, self.new_rect_lst):
            trans_widget.setPlainText(item.toPlainText())
            item.setPlainText('')
            item.setRect(rect, repaint=False)
            item.setHtml(html)
            if item.fontformat.letter_spacing != 1:
                item.setLetterSpacing(item.fontformat.letter_spacing, force=True)
            
    def undo(self):
        for item, trans_widget, html, rect  in zip(self.items, self.trans_widget_lst, self.old_html_lst, self.old_rect_lst):
            trans_widget.setPlainText(item.toPlainText())
            item.setPlainText('')
            item.setRect(rect, repaint=False)
            item.setHtml(html)
            if item.fontformat.letter_spacing != 1:
                item.setLetterSpacing(item.fontformat.letter_spacing, force=True)


class SqueezeCommand(QUndoCommand):
    def __init__(self, blkitem_lst: List[TextBlkItem], ctrl: TextBlkShapeControl):
        super(SqueezeCommand, self).__init__()
        self.blkitem_lst = blkitem_lst
        self.old_rect_lst = []
        self.ctrl = ctrl
        for item in blkitem_lst:
            self.old_rect_lst.append(item.absBoundingRect(qrect=True))
    
    def redo(self):
        for blk in self.blkitem_lst:
            blk.squeezeBoundingRect()

    def undo(self):
        for blk, rect in zip(self.blkitem_lst, self.old_rect_lst):
            blk.setRect(rect, repaint=True)
            if blk.under_ctrl:
                self.ctrl.updateBoundingRect()

class ResetAngleCommand(QUndoCommand):
    def __init__(self, blkitem_lst: List[TextBlkItem], ctrl: TextBlkShapeControl):
        super(ResetAngleCommand, self).__init__()
        self.blkitem_lst = blkitem_lst
        self.angle_lst = []
        self.ctrl = ctrl
        blkitem_lst = []
        for blk in self.blkitem_lst:
            rotation = blk.rotation()
            if rotation != 0:
                self.angle_lst.append(rotation)
                blkitem_lst.append(blk)
        self.blkitem_lst = blkitem_lst
    
    def redo(self):
        for blk in self.blkitem_lst:
            blk.setAngle(0)
            if self.ctrl.blk_item == blk:
                self.ctrl.setAngle(0)

    def undo(self):
        for blk, angle in zip(self.blkitem_lst, self.angle_lst):
            blk.setAngle(angle)
            if self.ctrl.blk_item == blk:
                self.ctrl.setAngle(angle)

class TextItemEditCommand(QUndoCommand):
    def __init__(self, blkitem: TextBlkItem, trans_edit: TransTextEdit, num_steps: int, formatpanel=None):
        super(TextItemEditCommand, self).__init__()
        self.op_counter = 0
        self.edit = trans_edit
        self.blkitem = blkitem
        self.num_steps = num_steps
        self.is_formatting = blkitem.is_formatting
        self.old_ffmt_values = self.new_ffmt_values = None
        if blkitem.is_formatting and blkitem.old_ffmt_values is not None:
            self.old_ffmt_values = blkitem.old_ffmt_values.copy()
            self.new_ffmt_values = self.old_ffmt_values.copy()
            for k in self.new_ffmt_values:
                self.new_ffmt_values[k] = getattr(blkitem.fontformat, k)
        self.formatpanel = formatpanel

    def redo(self):
        if self.op_counter == 0:
            self.op_counter += 1
            return
        
        self.blkitem.repaint_on_changed = False
        if self.new_ffmt_values is not None:
            for k, v in self.new_ffmt_values.items():
                self.blkitem.fontformat[k] = v
        self.blkitem.redo()
        self.blkitem.repaint_on_changed = True
        if self.num_steps > 0:
            self.blkitem.repaint_background()

        if self.is_formatting and self.blkitem == self.formatpanel.textblk_item:
            multi_size = not self.blkitem.isEditing() and self.blkitem.isMultiFontSize()
            self.formatpanel.set_active_format(self.blkitem.get_fontformat(), multi_size)

        if self.edit is not None and not self.is_formatting:
            self.edit.redo()

    def undo(self):
        self.blkitem.repaint_on_changed = False
        if self.old_ffmt_values is not None:
            for k, v in self.old_ffmt_values.items():
                self.blkitem.fontformat[k] = v
        self.blkitem.undo()
        self.blkitem.repaint_on_changed = True
        if self.num_steps > 0:
            self.blkitem.repaint_background()

        if self.is_formatting and self.blkitem == self.formatpanel.textblk_item:
            multi_size = not self.blkitem.isEditing() and self.blkitem.isMultiFontSize()
            self.formatpanel.set_active_format(self.blkitem.get_fontformat(), multi_size)

        if self.edit is not None:
            self.edit.undo()


class TextEditCommand(QUndoCommand):
    def __init__(self, edit: Union[SourceTextEdit, TransTextEdit], num_steps: int, blkitem: TextBlkItem) -> None:
        super().__init__()
        # TODO: remove it for transtextedit
        self.edit = edit
        self.blkitem = blkitem
        self.op_counter = 0
        self.num_steps = num_steps

    def redo(self):
        if self.op_counter == 0:
            self.op_counter += 1
            return
        self.edit.redo()
        if self.blkitem is not None:
            self.blkitem.redo()

    def undo(self):
        self.edit.undo()
        if self.blkitem is not None:
            self.blkitem.undo()


class PageReplaceOneCommand(QUndoCommand):
    def __init__(self, se: PageSearchWidget, parent=None):
        super(PageReplaceOneCommand, self).__init__(parent)
        self.op_counter = 0
        self.sw = se
        self.reptxt = self.sw.replace_editor.toPlainText()
        self.repl_len = len(self.reptxt)
        
        self.sel_start = self.sw.current_cursor.selectionStart()
        self.oritxt = self.sw.current_cursor.selectedText()
        self.ori_len = len(self.oritxt)
        self.edit: Union[SourceTextEdit, TransTextEdit] = self.sw.current_edit
        self.edit_is_src = type(self.edit) == SourceTextEdit
        self.blkitem = self.sw.textblk_item_list[self.sw.current_edit.idx]

        if self.sw.current_edit is not None and self.sw.isVisible():
            move = self.sw.move_cursor(1)
            if move == 0:
                self.sw.result_pos = min(self.sw.counter_sum - 1, self.sw.result_pos + 1)
            else:
                self.sw.result_pos = 0

        if not self.edit_is_src:
            cursor = self.blkitem.textCursor()
            cursor.setPosition(self.sel_start)
            cursor.setPosition(self.sel_start+self.ori_len, QTextCursor.MoveMode.KeepAnchor)
            cursor.beginEditBlock()
            cursor.insertText(self.reptxt)
            cursor.endEditBlock()

        self.rep_cursor = self.edit.textCursor()
        self.rep_cursor.setPosition(self.sel_start)
        self.rep_cursor.setPosition(self.sel_start+self.ori_len, QTextCursor.MoveMode.KeepAnchor)
        self.rep_cursor.insertText(self.reptxt)
        self.edit.updateUndoSteps()

    def redo(self):
        if self.op_counter == 0:
            self.op_counter += 1
            return

        if self.sw.current_edit is not None and self.sw.isVisible():
            move = self.sw.move_cursor(1)
            if move == 0:
                self.sw.result_pos = min(self.sw.counter_sum - 1, self.sw.result_pos + 1)
            else:
                self.sw.result_pos = 0

        if not self.edit_is_src:
            self.blkitem.redo()
        self.edit.redo()

    def undo(self):
        if not self.edit_is_src:
            self.blkitem.undo()
        self.sw.update_cursor_on_insert = False
        self.edit.undo()
        self.sw.update_cursor_on_insert = True
        if self.sw.current_edit is not None and self.sw.isVisible():
            move = self.sw.move_cursor(-1)
            if move == 0:
                self.sw.result_pos = max(self.sw.result_pos - 1, 0)
            else:
                self.sw.result_pos = self.sw.counter_sum - 1
            self.sw.updateCounterText()


class PageReplaceAllCommand(QUndoCommand):

    def __init__(self, search_widget: PageSearchWidget) -> None:
        super().__init__()
        self.op_counter = 0
        self.sw = search_widget

        self.rstedit_list: List[SourceTextEdit] = []
        self.blkitem_list: List[TextBlkItem] = []
        curpos_list: List[List[Matched]] = []
        for edit, highlighter in zip(self.sw.search_rstedit_list, self.sw.highlighter_list):
            self.rstedit_list.append(edit)
            curpos_list.append(list(highlighter.matched_map.values()))

        replace = self.sw.replace_editor.toPlainText()
        for edit, curpos_lst in zip(self.rstedit_list, curpos_list):
            redo_blk = type(edit) == TransTextEdit
            if redo_blk:
                blkitem = self.sw.textblk_item_list[edit.idx]
                self.blkitem_list.append(blkitem)
            span_list = [[matched.start, matched.end] for matched in curpos_lst]
            sel_list = doc_replace(edit.document(), span_list, replace)
            if redo_blk:
                doc_replace_no_shift(blkitem.document(), sel_list, replace)
                blkitem.updateUndoSteps()

    def redo(self):
        if self.op_counter == 0:
            self.op_counter += 1
            return

        for edit in self.rstedit_list:
            edit.redo()
        for blkitem in self.blkitem_list:
            blkitem.redo()

    def undo(self):
        for edit in self.rstedit_list:
            edit.undo()
        for blkitem in self.blkitem_list:
            blkitem.undo()


class GlobalRepalceAllCommand(QUndoCommand):
    def __init__(self, sceneitem_list: dict, background_list: dict, target_text: str, proj: ProjImgTrans) -> None:
        super().__init__()
        self.op_counter = -1
        self.target_text = target_text
        self.proj = proj
        self.trans_list = sceneitem_list['trans']
        self.src_list = sceneitem_list['src']
        self.btrans_list = background_list['trans']
        self.bsrc_list = background_list['src']

        for trans_dict in self.trans_list:
            edit: TransTextEdit = trans_dict['edit']
            item: TextBlkItem = trans_dict['item']
            matched_map = trans_dict['matched_map']
            sel_list = doc_replace(edit.document(), matched_map, target_text)

            doc_replace_no_shift(item.document(), sel_list, target_text)
            item.updateUndoSteps()
            item.updateUndoSteps()

            trans_dict.pop('matched_map')

        for src_dict in self.src_list:
            edit: SourceTextEdit = src_dict['edit']
            edit.setPlainTextAndKeepUndoStack(src_dict['replace'])
            edit.updateUndoSteps()
            src_dict.pop('replace')

    def redo(self):
        if self.op_counter == 0:
            self.op_counter += 1
            return

        for trans_dict in self.trans_list:
            edit: TransTextEdit = trans_dict['edit']
            item: TextBlkItem = trans_dict['item']
            edit.redo()
            item.redo()

        for src_dict in self.src_list:
            edit: SourceTextEdit = src_dict['edit']
            edit.redo()

        for trans_dict in self.btrans_list:
            blk: TextBlock = self.proj.pages[trans_dict['pagename']][trans_dict['idx']]
            blk.translation = trans_dict['replace']
            blk.rich_text = trans_dict['replace_html']

        for src_dict in self.bsrc_list:
            blk: TextBlock = self.proj.pages[src_dict['pagename']][src_dict['idx']]
            blk.text = src_dict['replace']

    def undo(self):
        for trans_dict in self.trans_list:
            edit: TransTextEdit = trans_dict['edit']
            item: TextBlkItem = trans_dict['item']
            edit.undo()
            item.undo()

        for src_dict in self.src_list:
            edit: SourceTextEdit = src_dict['edit']
            edit.undo()

        for trans_dict in self.btrans_list:
            blk: TextBlock = self.proj.pages[trans_dict['pagename']][trans_dict['idx']]
            blk.translation = trans_dict['ori']
            blk.rich_text = trans_dict['ori_html']

        for src_dict in self.src_list:
            blk: TextBlock = self.proj.pages[src_dict['pagename']][src_dict['idx']]
            blk.text = src_dict['ori']


class MultiPasteCommand(QUndoCommand):
    def __init__(self, text_list: Union[str, List], blkitems: List[TextBlkItem], etrans: List[TransTextEdit]) -> None:
        super().__init__()
        self.op_counter = -1
        self.blkitems = blkitems
        self.etrans = etrans

        if len(blkitems) > 0:
            if isinstance(text_list, str):
                text_list = [text_list] * len(blkitems)

        for blkitem, etran, text in zip(self.blkitems, self.etrans, text_list):
            etran.setPlainTextAndKeepUndoStack(text)
            blkitem.setPlainTextAndKeepUndoStack(text)

    def redo(self):
        if self.op_counter == 0:
            self.op_counter += 1
            return
        for blkitem, etran in zip(self.blkitems, self.etrans):
            blkitem.redo()
            etran.redo()

    def undo(self):
        for blkitem, etran in zip(self.blkitems, self.etrans):
            blkitem.undo()
            etran.undo()


class SplitBlkItemsCommand(QUndoCommand):
    """Split selected TextBlkItems by translation lines into multiple blocks.
    
    - Horizontal blocks: split top-to-bottom along Y axis
    - Vertical blocks: split right-to-left along X axis
    - Supports multiple selected blocks simultaneously
    - Maintains relative ordering of blocks
    """

    def __init__(self, blk_list: List[TextBlkItem], ctrl, parent=None):
        super().__init__(parent)
        import copy
        import numpy as np

        self.ctrl = ctrl  # SceneTextManager

        # Sort by idx to maintain ordering
        blk_list = sorted(blk_list, key=lambda b: b.idx)
        self.blk_list = blk_list
        self.pwidget_list: List[TransPairWidget] = [ctrl.pairwidget_list[b.idx] for b in blk_list]

        # Record the original idx of each block (stable reference for reinsertion positions)
        self.orig_idxs = [b.idx for b in blk_list]

        # Snapshot for undo
        self.old_rects = [b.absBoundingRect(qrect=True) for b in blk_list]
        self.old_trans_texts = [pw.e_trans.toPlainText() for pw in self.pwidget_list]
        self.old_src_texts = [pw.e_source.toPlainText() for pw in self.pwidget_list]
        self.old_html_list = [b.toHtml() for b in blk_list]

        # Pre-build the child block data for each source block (without adding them yet)
        # Each group is a list of (TextBlock data, trans_text, src_text, QRectF)
        self.child_data_groups = []  # List[List[dict]]

        for blk, pw, rect, trans_text, src_text in zip(
                blk_list, self.pwidget_list,
                self.old_rects, self.old_trans_texts, self.old_src_texts):

            lines = trans_text.split('\n')
            non_empty = [l for l in lines if l.strip()]

            if len(non_empty) < 2:
                self.child_data_groups.append([])
                continue

            n = len(non_empty)
            is_vertical = blk.blk.vertical
            child_data = []

            for i, line_text in enumerate(non_empty):
                new_blk_data = copy.deepcopy(blk.blk)
                new_blk_data.rich_text = ''

                if is_vertical:
                    # Vertical text: split columns right-to-left
                    col_w = rect.width() / n
                    new_x = rect.x() + (n - 1 - i) * col_w
                    new_rect = QRectF(new_x, rect.y(), col_w, rect.height())
                else:
                    # Horizontal text: split rows top-to-bottom
                    row_h = rect.height() / n
                    new_y = rect.y() + i * row_h
                    new_rect = QRectF(rect.x(), new_y, rect.width(), row_h)

                new_blk_data._bounding_rect = [
                    int(new_rect.x()), int(new_rect.y()),
                    int(new_rect.width()), int(new_rect.height())
                ]
                xywh = np.array([new_rect.x(), new_rect.y(), new_rect.width(), new_rect.height()])
                new_blk_data.set_lines_by_xywh(xywh)
                new_blk_data.translation = line_text
                new_blk_data.text = [src_text] if i == 0 else ['']

                child_data.append({
                    'blk_data': new_blk_data,
                    'trans_text': line_text,
                    'src_text': src_text if i == 0 else '',
                })

            self.child_data_groups.append(child_data)

        # These will be populated on first redo
        self.new_blk_groups: List[List[TextBlkItem]] = []
        self.new_pwidget_groups: List[List[TransPairWidget]] = []
        self.op_counter = 0

    def redo(self):
        if self.op_counter == 0:
            self.op_counter += 1
            self._do_split_first_time()
        else:
            self._do_split_recover()

    def _do_split_first_time(self):
        """First execution: create child items, delete originals, reorder."""
        self.new_blk_groups = []
        self.new_pwidget_groups = []

        # Create new blocks for each source
        for child_data_list in self.child_data_groups:
            new_blks = []
            new_pws = []
            for cd in child_data_list:
                new_blkitem = self.ctrl.addTextBlock(cd['blk_data'])
                new_blkitem.setPlainText(cd['trans_text'])
                new_pw = self.ctrl.pairwidget_list[-1]
                new_pw.e_trans.setPlainText(cd['trans_text'])
                new_pw.e_source.setPlainText(cd['src_text'])
                new_blks.append(new_blkitem)
                new_pws.append(new_pw)
            self.new_blk_groups.append(new_blks)
            self.new_pwidget_groups.append(new_pws)

        # Delete originals that were successfully split
        to_delete_blks = []
        to_delete_pws = []
        for blk, pw, new_blks in zip(self.blk_list, self.pwidget_list, self.new_blk_groups):
            if new_blks:
                to_delete_blks.append(blk)
                to_delete_pws.append(pw)
        if to_delete_blks:
            self.ctrl.deleteTextblkItemList(to_delete_blks, to_delete_pws)

        # Reorder new blocks to sit at original positions
        self._reorder_to_original_positions()

    def _do_split_recover(self):
        """Subsequent redo: delete originals, recover children, reorder."""
        to_delete_blks = []
        to_delete_pws = []
        for blk, pw, new_blks in zip(self.blk_list, self.pwidget_list, self.new_blk_groups):
            if new_blks:
                to_delete_blks.append(blk)
                to_delete_pws.append(pw)
        if to_delete_blks:
            self.ctrl.deleteTextblkItemList(to_delete_blks, to_delete_pws)

        for new_blks, new_pws in zip(self.new_blk_groups, self.new_pwidget_groups):
            if new_blks:
                self.ctrl.recoverTextblkItemList(new_blks, new_pws)

        self._reorder_to_original_positions()

    def _reorder_to_original_positions(self):
        """
        Physically reorder textblk_item_list and pairwidget_list so that 
        child groups appear at the position where the original block was.
        
        At this point: original blocks are deleted, new child blocks are appended at tail.
        We need to splice them into the right positions.
        """
        blk_item_list = self.ctrl.textblk_item_list
        pairwidget_list = self.ctrl.pairwidget_list

        # Collect all child items (in insertion order)
        all_new_blk_set = set()
        for new_blks in self.new_blk_groups:
            for b in new_blks:
                all_new_blk_set.add(id(b))

        # Items that are NOT new children (the "kept" items)
        kept = [(b, pairwidget_list[b.idx])
                for b in blk_item_list if id(b) not in all_new_blk_set]

        # Map: original_idx -> (child_blks, child_pws)
        # orig_idxs references the idx each original block had BEFORE deletion.
        # After deletion those slots are gone; we need to insert children in original order.
        insert_map = {}  # orig_idx -> (child_blks, child_pws)
        for orig_idx, new_blks, new_pws in zip(
                self.orig_idxs, self.new_blk_groups, self.new_pwidget_groups):
            if new_blks:
                insert_map[orig_idx] = (new_blks, new_pws)

        # Build the final ordered list:
        # Walk through slots 0..N (N = total count after split).
        # For each original position that had children, insert them; otherwise take from kept.
        sorted_orig_idxs = sorted(insert_map.keys())

        result_blks = []
        result_pws = []
        kept_iter = iter(kept)

        # Total slots = len(kept) + sum(len(children) for split originals)
        # We interleave: at each original slot, place its children; fill rest with kept items.

        # Determine insertion positions accounting for removed originals:
        # If original at idx=5 and there are 2 originals before it (idx 1 and 3),
        # then after removal the "natural" position shifts to 5-2=3. But we want to keep order,
        # so simply: process positions in original index order, inserting children groups,
        # and fill remaining from kept.

        # Simple approach: iterate 0 to total_count, at each slot figure out if it's a
        # child group slot or a kept slot.
        # After deleting len(split_originals) items and adding total_children items,
        # total size = len(blk_item_list) (already reflects this).

        n_total = len(blk_item_list)
        n_split = len(sorted_orig_idxs)

        # We'll use a position pointer approach:
        # For each original index (in sorted order), we insert that group at that position.
        # Between groups, we insert kept items.

        pos = 0  # Current position in the result
        kept_remaining = list(kept)
        
        for orig_idx in sorted_orig_idxs:
            # How many kept items go before this group?
            # After removing prior split originals: if orig_idx was at position orig_idx,
            # and n_removed_before = number of split originals with idx < orig_idx,
            n_removed_before = sum(1 for oi in sorted_orig_idxs if oi < orig_idx)
            target_pos = orig_idx - n_removed_before
            
            # Fill kept items up to target_pos
            while pos < target_pos and kept_remaining:
                b, pw = kept_remaining.pop(0)
                result_blks.append(b)
                result_pws.append(pw)
                pos += 1

            # Insert child group
            child_blks, child_pws = insert_map[orig_idx]
            result_blks.extend(child_blks)
            result_pws.extend(child_pws)
            pos += len(child_blks)

        # Append remaining kept items
        for b, pw in kept_remaining:
            result_blks.append(b)
            result_pws.append(pw)

        # Apply reorder
        self.ctrl.textblk_item_list.clear()
        self.ctrl.pairwidget_list.clear()
        for ii, (b, pw) in enumerate(zip(result_blks, result_pws)):
            b.idx = ii
            pw.idx = ii
            pw.e_source.idx = ii
            pw.e_trans.idx = ii
            self.ctrl.textblk_item_list.append(b)
            self.ctrl.pairwidget_list.append(pw)

        # Reorder widgets in the text panel layout
        layout = self.ctrl.textEditList.vlayout
        for pw in result_pws:
            layout.removeWidget(pw)
        for ii, pw in enumerate(result_pws):
            layout.insertWidget(ii, pw)
            pw.idx_label.setText(str(ii + 1).zfill(2))
            pw.setVisible(True)

        self.ctrl.updateTextBlkItemIdx()

    def undo(self):
        # Delete all child blocks
        all_new_blks = []
        all_new_pws = []
        for new_blks, new_pws in zip(self.new_blk_groups, self.new_pwidget_groups):
            all_new_blks.extend(new_blks)
            all_new_pws.extend(new_pws)
        if all_new_blks:
            self.ctrl.deleteTextblkItemList(all_new_blks, all_new_pws)

        # Recover original split blocks
        to_recover = []
        to_recover_pws = []
        for blk, pw, new_blks in zip(self.blk_list, self.pwidget_list, self.new_blk_groups):
            if new_blks:
                to_recover.append(blk)
                to_recover_pws.append(pw)
        if to_recover:
            self.ctrl.recoverTextblkItemList(to_recover, to_recover_pws)

        # Restore original texts and rects
        for blk, pw, rect, html, src_text, trans_text in zip(
                self.blk_list, self.pwidget_list,
                self.old_rects, self.old_html_list,
                self.old_src_texts, self.old_trans_texts):
            blk.setRect(rect)
            blk.setHtml(html)
            pw.e_source.setPlainText(src_text)
            pw.e_trans.setPlainText(trans_text)



class MergeBlkItemsCommand(QUndoCommand):
    """Merge multiple selected TextBlkItems into one, combining their bounding rects and text."""
    def __init__(self, blk_list: List[TextBlkItem], ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl  # SceneTextManager
        # Sort by idx so text order is top-to-bottom / left to right
        blk_list = sorted(blk_list, key=lambda b: b.idx)
        self.blk_list = blk_list
        self.pwidget_list: List[TransPairWidget] = [ctrl.pairwidget_list[b.idx] for b in blk_list]

        # Snapshot state for undo
        self.old_rects = [b.absBoundingRect(qrect=True) for b in blk_list]
        self.old_trans_texts = [pw.e_trans.toPlainText() for pw in self.pwidget_list]
        self.old_src_texts = [pw.e_source.toPlainText() for pw in self.pwidget_list]
        self.old_html_list = [b.toHtml() for b in blk_list]

        # Compute union bounding rect (scene coordinates)
        union = QRectF()
        for b in blk_list:
            union = union.united(b.absBoundingRect(qrect=True))
        self.merged_rect = union

        # Merge text: source and translation joined with newline
        self.merged_src = '\n'.join(t for t in self.old_src_texts if t.strip())
        self.merged_trans = '\n'.join(t for t in self.old_trans_texts if t.strip())

        # Primary item (first one) will become the merged block
        self.primary = blk_list[0]
        self.primary_pwidget = self.pwidget_list[0]
        # Secondary items to be deleted
        self.secondary_list = blk_list[1:]
        self.secondary_pwidget_list = self.pwidget_list[1:]

        self.op_counter = 0

    def redo(self):
        if self.op_counter == 0:
            self.op_counter += 1
            # First call: state already set up in __init__, just apply
        # Expand primary to union rect and set merged text
        self.primary.setRect(self.merged_rect)
        self.primary_pwidget.e_source.setPlainText(self.merged_src)
        self.primary_pwidget.e_trans.setPlainText(self.merged_trans)
        self.primary.setPlainText(self.merged_trans)
        # Delete secondary items
        if self.secondary_list:
            self.ctrl.deleteTextblkItemList(self.secondary_list, self.secondary_pwidget_list)

    def undo(self):
        # Restore secondary items first
        if self.secondary_list:
            self.ctrl.recoverTextblkItemList(self.secondary_list, self.secondary_pwidget_list)
        # Restore all items to original state
        for b, pw, rect, html, src_text, trans_text in zip(
                self.blk_list, self.pwidget_list,
                self.old_rects, self.old_html_list,
                self.old_src_texts, self.old_trans_texts):
            b.setRect(rect)
            b.setHtml(html)
            pw.e_source.setPlainText(src_text)
            pw.e_trans.setPlainText(trans_text)