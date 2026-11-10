"""
Sarbon detektori (D:\\Sarbon) — Ultralytics YOLO o'rniga, xuddi shu interfeys bilan.

DetectorGroup modeldan faqat .names, .to(), .fuse(), .predict(frames, conf=..., max_det=...)
va natijada .boxes.xyxy / .conf / .cls ni ishlatadi; SarbonModel shularni beradi.

Model o'qitilgan ko'rinishda ishlatiladi: kadr nisbati saqlanib imgsz x imgsz ga letterbox
(kulrang 114 bilan to'ldiriladi), RGB, bf16. Shu ko'rinishda o'lchangan: smart_v4 testida
hech bir model ko'rmagan 214 kadrda 77.7 AP (Sarbon yengil, 1024).
DETR uslubi: NMS yo'q — har so'rov (query) bitta obyekt.

Sarbon kodi D:\\Sarbon dan olinadi (SARBON_DIR muhit o'zgaruvchisi bilan o'zgartiriladi).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import cv2
import numpy as np
import torch

SARBON_DIR = os.environ.get("SARBON_DIR", r"D:\Sarbon")
NAMES = {0: "person", 1: "helmet", 2: "no_helmet"}


def is_sarbon_model(path: str) -> bool:
    return "sarbon" in os.path.basename(str(path)).lower()


@dataclass
class _Boxes:
    xyxy: torch.Tensor
    conf: torch.Tensor
    cls: torch.Tensor

    def __len__(self):
        return len(self.conf)


@dataclass
class _Result:
    boxes: _Boxes


class SarbonModel:
    def __init__(self, path: str, imgsz: int = 1024):
        if SARBON_DIR not in sys.path:
            sys.path.insert(0, SARBON_DIR)
        from sarbon.models.sarbon_det import load_detector

        self.model = load_detector(path, "s", len(NAMES), halo_zero=False).eval()
        self.names = dict(NAMES)
        self.imgsz = int(imgsz)  # o'qitilgan o'lcham; predict(imgsz=...) e'tiborga olinmaydi
        self.device = torch.device("cpu")
        self._mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1) * 255
        self._std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1) * 255

    def to(self, device):
        self.device = torch.device(device)
        self.model.to(self.device)
        self._mean, self._std = self._mean.to(self.device), self._std.to(self.device)
        return self

    def fuse(self):
        return self

    def _letterbox(self, frame):
        h, w = frame.shape[:2]
        s = min(self.imgsz / h, self.imgsz / w)
        nh, nw = round(h * s), round(w * s)
        py, px = (self.imgsz - nh) // 2, (self.imgsz - nw) // 2
        out = np.full((self.imgsz, self.imgsz, 3), 114, np.uint8)
        out[py:py + nh, px:px + nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)[..., ::-1]
        return out, s, px, py

    @torch.no_grad()
    def predict(self, frames, conf: float = 0.25, max_det: int = 100, **_):
        if not len(frames):
            return []
        boxed = [self._letterbox(f) for f in frames]
        x = torch.from_numpy(np.stack([b[0] for b in boxed])).to(self.device, non_blocking=True)
        x = (x.permute(0, 3, 1, 2).float() - self._mean) / self._std
        with torch.autocast(self.device.type, torch.bfloat16, enabled=self.device.type == "cuda"):
            out = self.model(x)
        scores = out["pred_logits"].float().sigmoid()
        b, q, c = scores.shape
        top, idx = scores.flatten(1).topk(min(int(max_det), q * c))
        cxcywh = out["pred_boxes"].float().gather(1, (idx // c)[..., None].expand(-1, -1, 4))
        xyxy = torch.cat([cxcywh[..., :2] - cxcywh[..., 2:] / 2, cxcywh[..., :2] + cxcywh[..., 2:] / 2], -1)
        xyxy, top, cls = (xyxy * self.imgsz).cpu(), top.cpu(), (idx % c).cpu()
        results = []
        for i, (frame, (_, s, px, py)) in enumerate(zip(frames, boxed)):
            keep = top[i] >= conf
            bx = (xyxy[i][keep] - torch.tensor([px, py, px, py])) / s
            h, w = frame.shape[:2]
            bx[:, 0::2] = bx[:, 0::2].clamp(0, w)
            bx[:, 1::2] = bx[:, 1::2].clamp(0, h)
            results.append(_Result(_Boxes(bx, top[i][keep], cls[i][keep].float())))
        return results


def load_model(path: str):
    """Fayl nomida 'sarbon' bo'lsa — Sarbon, aks holda Ultralytics YOLO."""
    if is_sarbon_model(path):
        return SarbonModel(path)
    from ultralytics import YOLO
    return YOLO(path, task="detect")
