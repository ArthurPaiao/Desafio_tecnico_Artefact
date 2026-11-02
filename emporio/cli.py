"""Chat with the agent in the terminal.

    python -m emporio                      # new conversation
    python -m emporio --session maria      # resume (or start) a saved conversation
    python -m emporio --verbose            # also print each tool call the agent makes
    python -m emporio --provider openai-compatible  # default provider is gemini (free tier)
"""

import argparse
import json
import os
import sys
from datetime import datetime

from emporio.agent import Agent
from emporio.providers import PROVIDERS, ProviderError, make_client


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="emporio", description="Empório da Música support agent")
    parser.add_argument("--session", default=datetime.now().strftime("session-%Y%m%d-%H%M%S"),
                        help="session name; reusing a name resumes that conversation")
    parser.add_argument("--provider", default=None, choices=sorted(PROVIDERS),
                        help="model provider (default: EMPORIO_PROVIDER or gemini)")
    parser.add_argument("--model", default=None, help="model id (default: EMPORIO_MODEL or the provider's default)")
    parser.add_argument("--verbose", action="store_true", help="print tool calls")
    args = parser.parse_args(argv)

    try:
        client, default_model = make_client(args.provider)
    except ProviderError as e:
        print(e, file=sys.stderr)
        return 1
    model = args.model or os.environ.get("EMPORIO_MODEL") or default_model

    def show(call):
        print(f"  [tool] {call['name']}({json.dumps(call['input'], ensure_ascii=False)})")

    agent = Agent(client, args.session, model=model,
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
            answer = agent.reply(text)
            if agent.last_error:   # the customer sees a friendly message; the developer sees why
                print(f"  [erro] {type(agent.last_error).__name__}: {agent.last_error}", file=sys.stderr)
            print(f"\nTom: {answer}\n")


if __name__ == "__main__":
    sys.exit(main())
