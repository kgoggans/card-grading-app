"""
Vision-based Card Grade Prediction — EfficientNet-B0 Transfer Learning

Fine-tunes EfficientNet-B0 (pretrained on ImageNet) to predict PSA grade
directly from card images.  Dramatically more accurate than the CV feature
approach because it learns card surface features automatically.

Requirements:
    pip install torch torchvision pillow

GPU: Apple Silicon MPS is used automatically when available.

Architecture:
    EfficientNet-B0 backbone (frozen for first 5 epochs)
    → Dropout(0.3) → Linear(1280, 128) → ReLU → Dropout(0.2) → Linear(128, 1)
    Output: raw PSA grade (1.0 – 10.0), snapped to nearest valid grade at inference

Training strategy:
    Phase 1 (epochs 1-5):  train head only  — fast, prevents catastrophic forgetting
    Phase 2 (epochs 6+):   fine-tune full network with lower LR + cosine schedule
"""

import os
import json
from datetime import datetime

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torchvision.transforms as T
    from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights
    from PIL import Image
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

_DIR = os.path.dirname(os.path.abspath(__file__))
_MODEL_PATH = os.path.join(_DIR, 'training_data', 'vision_model.pt')
_META_PATH  = os.path.join(_DIR, 'training_data', 'vision_model_meta.json')

_VALID_PSA_GRADES = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5,
                     5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 10.0]
MIN_SAMPLES = 20  # minimum labeled images to start training


def _get_device():
    if not _TORCH_AVAILABLE:
        return None
    if torch.backends.mps.is_available():
        return torch.device('mps')
    if torch.cuda.is_available():
        return torch.device('cuda')
    return torch.device('cpu')


def _snap_grade(raw):
    return min(_VALID_PSA_GRADES, key=lambda g: abs(g - raw))


def _build_transforms():
    train_tf = T.Compose([
        T.Resize((256, 256)),
        T.RandomCrop(224),
        T.RandomHorizontalFlip(),
        T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    eval_tf = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    return train_tf, eval_tf


def _build_model():
    """EfficientNet-B0 backbone with regression head."""
    backbone = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)
    in_features = backbone.classifier[1].in_features
    backbone.classifier = nn.Sequential(
        nn.Dropout(p=0.3),
        nn.Linear(in_features, 128),
        nn.ReLU(),
        nn.Dropout(p=0.2),
        nn.Linear(128, 1),
    )
    return backbone


class _LazyCardDataset(torch.utils.data.Dataset):
    """Lazy dataset: loads images from disk on demand (no RAM pre-load)."""

    def __init__(self, records, transform):
        # records: [(path, grade_float, weight_float), ...]
        self.records = records
        self.transform = transform

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        path, grade, weight = self.records[idx]
        try:
            img = Image.open(path).convert('RGB')
            tensor = self.transform(img)
        except Exception:
            tensor = torch.zeros(3, 224, 224)
        return (tensor,
                torch.tensor(grade,  dtype=torch.float32),
                torch.tensor(weight, dtype=torch.float32))


class CardVisionModel:
    """EfficientNet-B0 fine-tuned for PSA grade prediction."""

    def __init__(self):
        self._net = None
        self._meta = {}
        self._device = _get_device()
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def _load(self):
        if not _TORCH_AVAILABLE or not os.path.exists(_MODEL_PATH):
            return
        try:
            net = _build_model()
            state = torch.load(_MODEL_PATH, map_location='cpu', weights_only=True)
            net.load_state_dict(state)
            net.to(self._device)
            net.eval()
            self._net = net
            if os.path.exists(_META_PATH):
                with open(_META_PATH) as f:
                    self._meta = json.load(f)
        except Exception:
            self._net = None

    def _save(self):
        os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
        self._net.cpu()
        torch.save(self._net.state_dict(), _MODEL_PATH)
        self._net.to(self._device)
        with open(_META_PATH, 'w') as f:
            json.dump(self._meta, f, indent=2)

    # ------------------------------------------------------------------ #
    # Training                                                             #
    # ------------------------------------------------------------------ #

    def train(self, image_pairs, epochs=15, batch_size=16, progress_cb=None):
        """
        Fine-tune on labeled card images.

        Args:
            image_pairs: list of (front_path, back_path, psa_grade, weight)
                         or (front_path, back_path, psa_grade) — weight defaults to 1.0
                         Personal scans should use weight=5.0; eBay/auction=1.0
            epochs:      Total training epochs (default 15)
            batch_size:  Images per batch (default 16)
            progress_cb: Optional callback(epoch, total_epochs, loss)

        Returns:
            dict with accuracy info.
        """
        if not _TORCH_AVAILABLE:
            raise ValueError(
                'PyTorch not installed. '
                'Run: pip install torch torchvision pillow'
            )
        if len(image_pairs) < MIN_SAMPLES:
            raise ValueError(
                f'Need at least {MIN_SAMPLES} labeled image pairs (have {len(image_pairs)}). '
                'Keep adding cards and try again.'
            )

        train_tf, eval_tf = _build_transforms()

        # Build record list (paths only — no disk I/O yet)
        records = []
        loaded_pairs = 0
        for entry in image_pairs:
            if len(entry) == 4:
                front_path, back_path, grade, weight = entry
            else:
                front_path, back_path, grade = entry
                weight = 1.0
            added = False
            for path in (front_path, back_path):
                if path and os.path.exists(path):
                    records.append((path, float(grade), float(weight)))
                    added = True
            if added:
                loaded_pairs += 1

        if len(records) < MIN_SAMPLES:
            raise ValueError(
                f'Only {len(records)} valid image paths found; need {MIN_SAMPLES}.'
            )

        net = _build_model()
        net.to(self._device)

        # Lazy dataset — images load per batch, not all upfront
        dataset = _LazyCardDataset(records, train_tf)
        loader = torch.utils.data.DataLoader(
            dataset, batch_size=batch_size, shuffle=True,
            num_workers=0, pin_memory=False
        )

        loss_fn = nn.MSELoss(reduction='none')
        n_batches = len(loader)

        def _epoch_cb(epoch, total, loss):
            if progress_cb:
                progress_cb(epoch, total, loss)

        # Phase 1: head only
        head_epochs = min(5, epochs)
        for param in net.features.parameters():
            param.requires_grad = False
        optimizer = torch.optim.Adam(
            filter(lambda p: p.requires_grad, net.parameters()), lr=1e-3
        )

        net.train()
        for epoch in range(head_epochs):
            epoch_loss = _run_epoch(net, loader, optimizer, loss_fn, self._device)
            _epoch_cb(epoch + 1, epochs, epoch_loss)

        # Phase 2: full fine-tune
        if epochs > head_epochs:
            for param in net.features.parameters():
                param.requires_grad = True
            optimizer_full = torch.optim.Adam(net.parameters(), lr=5e-5)
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer_full, T_max=epochs - head_epochs
            )
            for epoch in range(head_epochs, epochs):
                epoch_loss = _run_epoch(net, loader, optimizer_full, loss_fn, self._device)
                scheduler.step()
                _epoch_cb(epoch + 1, epochs, epoch_loss)

        # Evaluate
        net.eval()
        eval_dataset = _LazyCardDataset(records, eval_tf)
        eval_loader  = torch.utils.data.DataLoader(
            eval_dataset, batch_size=batch_size * 2, shuffle=False, num_workers=0
        )
        all_preds, all_grades = [], []
        with torch.no_grad():
            for xb, yb, _wb in eval_loader:
                xb = xb.to(self._device)
                pred = net(xb).squeeze(-1).cpu().numpy()
                all_preds.extend(pred.tolist())
                all_grades.extend(yb.numpy().tolist())

        all_preds  = np.clip(np.array(all_preds), 1.0, 10.0)
        all_grades = np.array(all_grades)
        mae = float(np.mean(np.abs(all_preds - all_grades)))
        correct = sum(
            1 for p, t in zip(all_preds, all_grades)
            if abs(_snap_grade(float(p)) - t) <= 0.5
        )
        grade_acc = round(100.0 * correct / len(all_grades), 1)

        self._net = net
        self._meta = {
            'n_samples':          len(records),
            'n_pairs':            loaded_pairs,
            'train_mae':          round(mae, 3),
            'grade_accuracy_pct': grade_acc,
            'epochs':             epochs,
            'device':             str(self._device),
            'trained_at':         datetime.utcnow().isoformat(),
        }
        self._save()
        return dict(self._meta)

    # ------------------------------------------------------------------ #
    # Prediction                                                           #
    # ------------------------------------------------------------------ #

    def predict(self, front_path, back_path):
        """
        Predict PSA grade from card image paths.
        Averages predictions from both sides for a more robust estimate.

        Returns:
            (snapped_grade: float, raw_prediction: float)
        """
        if not self.is_trained:
            raise ValueError('Vision model not trained yet.')
        if not _TORCH_AVAILABLE:
            raise ValueError('PyTorch not available.')

        _, eval_tf = _build_transforms()
        imgs = []
        for path in (front_path, back_path):
            if path and os.path.exists(path):
                try:
                    img = Image.open(path).convert('RGB')
                    imgs.append(eval_tf(img))
                except Exception:
                    pass

        if not imgs:
            raise ValueError('No valid images to predict from.')

        batch = torch.stack(imgs).to(self._device)
        self._net.eval()
        with torch.no_grad():
            preds = self._net(batch).squeeze(-1).cpu().numpy()

        raw = float(np.mean(np.clip(preds, 1.0, 10.0)))
        return _snap_grade(raw), round(raw, 2)

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    @property
    def is_trained(self):
        return self._net is not None

    def status(self):
        return {
            'is_trained':         self.is_trained,
            'torch_available':    _TORCH_AVAILABLE,
            'device':             str(self._device) if self._device else None,
            'n_samples':          self._meta.get('n_samples', 0),
            'n_pairs':            self._meta.get('n_pairs', 0),
            'train_mae':          self._meta.get('train_mae'),
            'grade_accuracy_pct': self._meta.get('grade_accuracy_pct'),
            'epochs':             self._meta.get('epochs'),
            'trained_at':         self._meta.get('trained_at'),
        }


def _run_epoch(net, loader, optimizer, loss_fn, device):
    """One training epoch; returns average loss."""
    total_loss = 0.0
    net.train()
    for xb, yb, wb in loader:
        xb  = xb.to(device)
        yb  = yb.to(device)
        wb  = wb.to(device)
        pred = net(xb).squeeze(-1)
        loss = (loss_fn(pred, yb) * wb).mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    return total_loss / max(len(loader), 1)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_vision_instance = None


def get_vision_model():
    global _vision_instance
    if _vision_instance is None:
        _vision_instance = CardVisionModel()
    return _vision_instance


def reload_vision_model():
    global _vision_instance
    _vision_instance = CardVisionModel()
    return _vision_instance
