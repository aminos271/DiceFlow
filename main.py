from __future__ import annotations

import argparse

from diceflow.app.cli import run_cli


def main() -> None:
    parser = argparse.ArgumentParser(description="DiceFlow TRPG MVP")
    parser.add_argument("--script", default="tomb_entrance", help="剧本名称，默认 tomb_entrance")
    parser.add_argument("--no-llm", action="store_true", help="使用本地保底解析和叙事，不调用 API")
    parser.add_argument("--no-debug", action="store_true", help="隐藏每轮调试日志")
    args = parser.parse_args()

    run_cli(script_name=args.script, use_llm=not args.no_llm, debug=not args.no_debug)


if __name__ == "__main__":
    main()
