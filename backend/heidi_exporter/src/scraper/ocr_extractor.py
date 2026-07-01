from pathlib import Path
import logging

class OcrExtractor:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        try:
            import pytesseract
            import cv2
            self.pytesseract = pytesseract
            self.cv2 = cv2
            self.available = True
        except ImportError:
            self.logger.warning("[WARNING] pytesseract or cv2 not installed. OCR will be unavailable.")
            self.available = False

    def extract_text_from_image(self, image_path: Path) -> str | None:
        if not self.available:
            return None
        try:
            # Read image using OpenCV
            image = self.cv2.imread(str(image_path))
            if image is None:
                self.logger.error(f"[ERROR] Failed to load image for OCR: {image_path}")
                return None
            
            # Preprocessing: Convert to grayscale
            gray = self.cv2.cvtColor(image, self.cv2.COLOR_BGR2GRAY)
            
            # Preprocessing: Adaptive Thresholding (optional, helps with UI text)
            # thresh = self.cv2.adaptiveThreshold(gray, 255, self.cv2.ADAPTIVE_THRESH_GAUSSIAN_C, self.cv2.THRESH_BINARY, 11, 2)
            
            # Run Tesseract
            text = self.pytesseract.image_to_string(gray)
            return text.strip() if text else None
        except Exception as e:
            self.logger.error(f"[ERROR] OCR extraction failed: {e}")
            return None
