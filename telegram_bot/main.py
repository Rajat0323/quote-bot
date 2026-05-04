import argparse
import logging

from current_affairs_bot.config import Settings
from current_affairs_bot.service import build_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Telegram bot for current-affairs posts or book-based motivational quote posts."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single fetch/generate/post cycle and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate content without posting to Telegram.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    args = parse_args()
    configure_logging(args.debug)
    settings = Settings.from_env()
    service = build_service(settings)

    if args.once:
        processed = service.run_cycle(dry_run=args.dry_run)
        logging.getLogger(__name__).info("Cycle complete. Processed %s articles.", processed)
        return

    if args.dry_run:
        logging.getLogger(__name__).warning(
            "--dry-run is only applied to a single cycle, so combining it with continuous mode is not supported."
        )
        processed = service.run_cycle(dry_run=True)
        logging.getLogger(__name__).info("Cycle complete. Processed %s articles.", processed)
        return

    service.run_forever()


if __name__ == "__main__":
    main()

