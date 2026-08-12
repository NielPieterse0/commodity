from __future__ import annotations

import sys

import pandas as pd

from commodity.config import REPO_ROOT, model_config


class KronosMiniAdapter:
    def __init__(self) -> None:
        cfg = model_config()["models"]["kronos_mini"]
        local_path = REPO_ROOT / cfg["local_path"]
        if not local_path.exists():
            raise RuntimeError("Kronos source is not installed under vendor/Kronos")
        import_path = str(local_path)
        if import_path not in sys.path:
            sys.path.insert(0, import_path)
        try:
            from model import Kronos, KronosPredictor, KronosTokenizer
        except ImportError as exc:
            raise RuntimeError("Install the 'kronos' extra before using Kronos") from exc
        tokenizer = KronosTokenizer.from_pretrained(
            cfg["tokenizer_id"], revision=cfg["tokenizer_revision"]
        )
        model = Kronos.from_pretrained(cfg["model_id"], revision=cfg["model_revision"])
        self.predictor = KronosPredictor(
            model, tokenizer, device=cfg["device"], max_context=cfg["max_context"]
        )

    def forecast(self, ohlcv: pd.DataFrame, future_index: pd.DatetimeIndex) -> pd.DataFrame:
        x = ohlcv[["open", "high", "low", "close", "volume"]].copy()
        return self.predictor.predict(
            df=x, x_timestamp=pd.Series(x.index), y_timestamp=pd.Series(future_index),
            pred_len=len(future_index), T=1.0, top_p=0.9, sample_count=1,
        )
