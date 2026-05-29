from typing import Tuple, List, Dict, Union, Callable
import numpy as np
import cv2
import os
from collections import OrderedDict

from utils.textblock import TextBlock
from utils.registry import Registry
from utils.imgproc_utils import rgba2rgb
OCR = Registry('OCR')
register_OCR = OCR.register_module

from ..base import BaseModule, DEFAULT_DEVICE, DEVICE_SELECTOR, LOGGER

class OCRBase(BaseModule):

    _postprocess_hooks = OrderedDict()
    _preprocess_hooks = OrderedDict()
    _line_only: bool = False

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.name = ''
        for key in OCR.module_dict:
            if OCR.module_dict[key] == self.__class__:
                self.name = key
                break

    def run_ocr(self, img: np.ndarray, blk_list: List[TextBlock] = None, *args, **kwargs) -> Union[List[TextBlock], str]:

        if not self.all_model_loaded():
            self.load_model()

        img = rgba2rgb(img)

        if blk_list is None:
            text = self.ocr_img(img)
            return text
        elif isinstance(blk_list, TextBlock):
            blk_list = [blk_list]

        for blk in blk_list:
            if self.name != 'none_ocr':
                blk.text = []

        # Save crops of current batch in logs directory for debugging
        log_dir = os.path.abspath("logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
            # Remove any existing debug ocr crops to keep only the latest batch
            for filename in os.listdir(log_dir):
                if filename.startswith("ocr_crop_") and filename.endswith(".png"):
                    try:
                        os.remove(os.path.join(log_dir, filename))
                    except Exception:
                        pass
            
            im_h, im_w = img.shape[:2]
            for idx, blk in enumerate(blk_list):
                x1, y1, x2, y2 = blk.xyxy
                if 0 <= y1 < y2 <= im_h and 0 <= x1 < x2 <= im_w:
                    crop = img[y1:y2, x1:x2]
                    if crop.size > 0:
                        crop_path = os.path.join(log_dir, f"ocr_crop_{idx}.png")
                        # The internal img is RGB, OpenCV imwrite expects BGR
                        crop_bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
                        cv2.imwrite(crop_path, crop_bgr)
        except Exception as e:
            if hasattr(self, 'logger') and self.logger:
                self.logger.warning(f"Failed to save debug OCR crops: {e}")
                
        self._ocr_blk_list(img, blk_list, *args, **kwargs)
        for callback_name, callback in self._postprocess_hooks.items():
            callback(textblocks=blk_list, img=img, ocr_module=self)

        return blk_list

    def _ocr_blk_list(self, img: np.ndarray, blk_list: List[TextBlock], *args, **kwargs) -> None:
        raise NotImplementedError

    def ocr_img(self, img: np.ndarray) -> str:
        raise NotImplementedError
