# Optional ML direction model

This is a **separate research model**, not the live default. The deployed bot
still uses `STRATEGY=ema_rsi`.

Model: small logistic regression on 13 price/volume/time features, trained on
cached 5-minute candles. Inference is pure Python (`bot/ml_model.py`), so the
container does not need numpy or scikit-learn.

## Train / validate

```bash
cd content-factory/invest-bot
PYTHONPATH=. ../.venv/bin/python ml/train.py --history data/history
```

The script trains on data up to `--train-end` and evaluates on the later period,
then writes `models/ml_logit.json`. Training needs numpy (`ml/requirements.txt`);
the live bot does not.

## Enable (not recommended yet)

```env
STRATEGY=ml
ML_MODEL_PATH=/app/models/ml_logit.json
ML_THRESHOLD=0.60
```

## Validation warning

On the 180-day sample the model's trading simulation was negative on both train
and test periods. It is integrated behind `STRATEGY=ml` for research only; do
not enable it with real money without a fresh out-of-sample test.

## Add more data

```bash
CANDLES_DELAY=0.5 PYTHONPATH=. ../.venv/bin/python ml/download_history.py --days 365
```

The trainer loads `*_365d.json` automatically and falls back to `*_180d.json`.
