from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_ai.app.market_baseline import evaluate_baseline, load_bars, result_as_dict, save_predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the chronological market baseline.")
    parser.add_argument("csv", help="CSV with timestamp,symbol,open,high,low,close,volume")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--lookback", type=int, default=3)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--predictions-db", default="data/baseline.sqlite3")
    args = parser.parse_args()

    result = evaluate_baseline(
        load_bars(args.csv),
        symbol=args.symbol,
        horizon=args.horizon,
        lookback=args.lookback,
        train_ratio=args.train_ratio,
        cost_bps=args.cost_bps,
    )
    save_predictions(args.predictions_db, result)
    print(json.dumps(result_as_dict(result), indent=2, default=list))


if __name__ == "__main__":
    main()
