"""Pipeline entry point: python -m src.pipeline {ingest,load,metrics,all} [--sample N]"""
import argparse
import logging


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["ingest", "load", "metrics", "all"])
    parser.add_argument("--sample", type=int, help="ingest only the first N schemes (plus benchmarks)")
    parser.add_argument("--refresh", action="store_true", help="re-download cached NAV histories")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("src.clean.schemes").setLevel(logging.WARNING)
    logging.getLogger("pgserver").setLevel(logging.WARNING)

    if args.step in ("ingest", "all"):
        from src.ingest.run import run as ingest
        ingest(sample=args.sample, refresh=args.refresh)
    if args.step in ("load", "all"):
        from src.load import run as load
        load()
    if args.step in ("metrics", "all"):
        from src.metrics.build import run as metrics
        metrics()


if __name__ == "__main__":
    main()
