"""Chat with the agent in the terminal.

    python -m emporio                      # new conversation
    python -m emporio --session maria      # resume (or start) a saved conversation
    python -m emporio --verbose            # also print each tool call the agent makes
"""

import argparse
import json
import os
import sys
from datetime import datetime

import anthropic

from emporio.agent import Agent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="emporio", description="Empório da Música support agent")
    parser.add_argument("--session", default=datetime.now().strftime("session-%Y%m%d-%H%M%S"),
                        help="session name; reusing a name resumes that conversation")
    parser.add_argument("--model", default=None, help="model id (default: EMPORIO_MODEL or claude-sonnet-5-5)")
    parser.add_argument("--verbose", action="store_true", help="print tool calls")
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Defina ANTHROPIC_API_KEY (veja o README).", file=sys.stderr)
        return 1

    def show(call):
        print(f"  [tool] {call['name']}({json.dumps(call['input'], ensure_ascii=False)})")

    agent = Agent(anthropic.Anthropic(), args.session, model=args.model,
                  on_tool_call=show if args.verbose else None)
    resumed = f" (retomando {len(agent.messages)} mensagens)" if agent.messages else ""
    print(f"Empório da Música | sessão: {args.session}{resumed} | digite /sair para encerrar\n")
    while True:
        try:
            text = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if text in ("/sair", "/exit", "/quit"):
            return 0
        if text:
            print(f"\nTom: {agent.reply(text)}\n")


if __name__ == "__main__":
    sys.exit(main())
