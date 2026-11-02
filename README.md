# Empório da Música: customer service agent

A text chat agent for a fictional musical instrument store in Campo Grande, MS (Brazil). It plays "Tom", a friendly attendant who answers in Brazilian Portuguese. It decides on its own when to look something up in the store data (products, prices, promotions, orders), when to consult the store policy manual, and when to say a question is out of scope or hand the customer to a human.

Technical case for the AI Engineer role at Artefact. Plain Python, standard library only at runtime, no agent framework.

Most of the code and tests in this repository were written by Claude (Anthropic), working as my coding assistant under my direction. The business decisions, the live testing against the model and the review of the results are mine. See [Use of AI coding assistants](#use-of-ai-coding-assistants) for what was done by whom.

## Quick start

Requires Python 3.10 or newer and a free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

```bash
git clone <this repository>
cd emporio-agent
pip install -e .                  # on Windows this also installs tzdata
cp .env.example .env              # then paste your key into .env (Windows: copy .env.example .env)
python -m emporio --verbose       # chat in the terminal; --verbose prints each tool call
```

The sample orders are from early 2026. To see order and return flows work as in the examples, pin the store clock first (`set "EMPORIO_NOW=2026-02-20T10:00"` on Windows, `export EMPORIO_NOW=2026-02-20T10:00` elsewhere). Without it the agent uses the real date, and every delivered order is correctly treated as old.

The `.env` file is git-ignored and is read automatically. A variable already set in your shell wins over the file. Useful options:

| Option | What it does |
|---|---|
| `--verbose` | Prints each tool call the agent makes |
| `--session NAME` | Resumes (or starts) a saved conversation, stored in `sessions/` |
| `--model ID` or `EMPORIO_MODEL` | Picks the model (default `gemini-3.5-flash-lite`) |
| `--provider` or `EMPORIO_PROVIDER` | `gemini` (default) or `openai-compatible` |
| `EMPORIO_NOW=2026-02-20T10:00` | Pins the store clock (see "Time" below) |

Other providers: set `EMPORIO_PROVIDER=openai-compatible`, `EMPORIO_BASE_URL` and `EMPORIO_API_KEY` for any OpenAI-compatible endpoint (Groq, OpenRouter, a local Ollama).

Tests (141, no network, no API key needed):

```bash
pip install -e ".[dev]"
python -m pytest -q
```

Regenerate the example conversations against a live model:

```bash
python scripts/run_examples.py              # all six, a few dozen model calls
python scripts/run_examples.py --only 5     # just one
```

## How it works

```
customer message
      |
      v
  Agent loop (emporio/agent.py)  <--- system prompt (persona, scope, rules, store clock)
      |   model call
      |   tool calls requested? --yes--> run tools --> results back to the model --> repeat (max 6 rounds)
      |   no
      v
  reply in Portuguese
```

The loop is about thirty lines. The conversation is stored as text, tool use and tool result blocks (the layout of the Anthropic Messages API, which maps one to one onto OpenAI-style tool calls) and saved to `sessions/<name>.json` after each turn, so a conversation can be resumed. If the model call fails, the turn is rolled back so the history stays valid, and the customer gets a short apology instead of a stack trace.

### The seven tools

| Tool | Source | Used for |
|---|---|---|
| `search_products` | CSV data | Browse by category, price range, keywords |
| `get_product` | CSV data | One product with promotion, PIX price, instalments and shipping |
| `get_order_status` | CSV data | Order status and tracking, after identity verification |
| `check_return_eligibility` | CSV data | Return or defect rules applied to a specific order |
| `search_policies` | Policy PDF | "How does X work": payments, exchanges, shipping, warranty |
| `get_store_info` | Code | Address, phones, opening hours, "are you open right now" |
| `escalate_to_human` | Code | Writes a ticket (`ATD-0001`, ...) and promises the manual's 24 business hours |

The split that matters is **data versus policy**. Facts about this product, this order or this date come from the CSV tools. Rules and procedures come from the policy manual through `search_policies`. The prompt tells the model which is which, and the tool descriptions repeat it.

## Technical decisions

**No framework.** The task is one loop and seven functions. LangChain or similar would add dependencies and hide the one thing worth showing: what the model decided and why. Every decision is visible in the message history and in `--verbose` output.

**Business rules live in code, not in the prompt.** Prices, promotions, the PIX discount, instalment minimums, shipping fees, return windows and opening hours are computed by deterministic Python (`pricing.py`, `catalog.py`, `orders.py`, `store.py`) and the model only repeats the results. The prompt forbids the model from doing price or date arithmetic and from stating a price, stock level, deadline or fee that did not come from a tool in the current conversation. This is what makes answers like "R$ 1.967,18, and the PIX discount does not stack with the promotion" reliable instead of lucky. Each rule is unit tested.

**LLM: Gemini on the free tier, behind a small provider layer.** I wanted anyone to run the project without paying. The agent loop speaks one message format, and `providers.py` translates it for any OpenAI-compatible endpoint using only `urllib` (one POST does not justify a dependency). It retries on 429 and 5xx with `Retry-After` or exponential backoff, and it echoes Gemini's `extra_content` on tool calls so thinking models work. The default model is `gemini-3.5-flash-lite`: it was the one that answered fast enough and correctly in my runs. `gemini-3.6-flash` also answered correctly but was noticeably slower, and `gemini-3.8-flash` returned 503 "high demand" repeatedly during my tests. The free tier does rate limit (429 when many calls go out within seconds), which matters for `run_examples.py`.

**Retrieval: BM25 over the policy Markdown, no vector database.** The manual is about 3,000 words and splits into 25 numbered (sub)sections. The PDF is converted once to Markdown (`scripts/extract_policies.py`, tables kept) and split into one chunk per section. Queries are ranked with BM25 over accent-free, crudely stemmed tokens, with the section title weighted three times. Embeddings would add a dependency, a cost and a failure mode for a corpus this small, and keyword ranking is easy to explain and debug. Two thresholds stop weak matches from being passed off as policy: a minimum score and a cutoff relative to the best hit. I chose them from measured scores: off-topic questions such as the weather top out near 1.9, and the weakest legitimate question ("tem garantia?") scores about 3.5, so the minimum is 3.0. When nothing relevant is found, the agent says it will confirm with the team and offers a human.

**Prompt strategy.** The system prompt is written in English (rules are followed more reliably) and tells the model to answer in Brazilian Portuguese. It has short sections: voice, what the store sells, never guess (use the tools), products and prices, orders and privacy, safety. It also gets a small block that changes every turn with the store's current date, time and open/closed status, so "are you open now?" and "until when?" are grounded. Rules are stated as behaviors, and several were added after watching real conversations, for example "never say a return is possible before `check_return_eligibility` has run", which came from a model answering "Pode sim!" before it had looked at the order.

**Identity verification for orders.** Order data is released only when the customer gives the order number and an e-mail or phone that matches that order. A wrong contact and a nonexistent order get the same answer, so the agent cannot be used to discover which orders exist. After three failed attempts in a conversation, lookups are locked and the agent offers a human. The counter is saved with the session, so resuming does not reset it, and a successful lookup does not reset it either (otherwise a guesser could alternate failures with a lookup of their own order). This is a demo-grade control: the second factor is an e-mail or phone, which is guessable, and starting a brand new session starts a new counter. A production system would rate limit by order and by IP, or send a one-time code to the contact on file. The data has a shared e-mail between two customers, so the contact is always matched against the order's own customer, never searched globally.

**Out of scope and manipulation.** Unrelated questions get one friendly sentence and a pull back to the store. Requests to reveal the prompt, ignore the rules or grant a discount are refused politely. Only tools define prices. The prompt states that customer text is never an instruction. This is tested in `examples/06-*.md`.

**Human hand-off.** Complaints, delayed shipments, defect claims the manual does not settle automatically, and purchase help go through `escalate_to_human`. It appends a record to `sessions/handoffs.jsonl` and returns a ticket number. A real deployment would post to a helpdesk instead.

## Assumptions and where the manual contradicts itself

The manual is not always consistent. These are the choices I made, so they are visible and can be changed in one place.

| Topic | What the manual says | What the agent does |
|---|---|---|
| Instalment minimum | The summary in section 3 says R$ 100 for all credit purchases. Section 3.1 gives tiers. | Section 3.1 wins because it is the specific rule: up to 3x the minimum instalment is R$ 50, 4 to 6x is R$ 80, 7 to 12x is R$ 100. |
| Discontinued products | Section 7.3 treats discontinued items as unavailable. | A discontinued product that still has stock stays on sale, with a notice that only the remaining units are left, and leaves the catalog when stock reaches zero. Pulling it early would waste inventory the store already paid for. This is a business decision I made on purpose, and it deviates from 7.3. |
| Local delivery | Section 5.1 says "Região Metropolitana de Campo Grande" and lists no towns. | Only Campo Grande itself gets the motoboy delivery (free above R$ 500, otherwise R$ 35). Every other city goes through Correios or Jadlog, with the price calculated from the destination ZIP code. |
| Return window start | Starts at receipt. The data only has an estimated delivery date. | The estimated delivery date is used, and the agent tells the customer so and offers a human review if the real date differs. |
| Phone numbers | (67) 3341-4444 in the company data, (67) 3321-4500 for WhatsApp. | Both are kept as printed. |
| E-mail | The domain in section 1.2 has an accent, which is invalid. | The accent is removed (`contato@emporiodamusica.com.br`). It is the only correction applied to the manual, listed in `scripts/extract_policies.py`. |
| Promotions | Section 6.2: promotions are not cumulative. | A promotional price gets no PIX discount. If several active promotions existed for a product, only the largest would apply. |
| Large instruments | 5.2 (other cities) says acoustic drums, pianos and double basses "may require special freight with an individual quote". 5.1 (Campo Grande) has no such exception. | Outside Campo Grande they get "shipping is quoted by the store" (matched by product name) instead of an invented fee. In Campo Grande the normal motoboy rule applies, so a R$ 4.439 drum kit ships free. |
| Return exclusions | 4.4 excludes custom or made-to-order items, "final sale" clearance items and mouthpieces. 4.1 covers online purchases only. | The data has no sales channel or final-sale flag, so the code cannot check this. Every `eligible` answer carries a warning, and the agent tells the customer to ask a human if the item may be excluded. |

### Time

The store clock runs in `America/Campo_Grande` (UTC-4). On Windows the time zone database is missing, so the code falls back to a fixed UTC-4 offset, which is correct because Mato Grosso do Sul has had no daylight saving since 2019. Opening hours are Monday to Friday 9h to 18h and Saturday 9h to 13h. National holidays plus Campo Grande and state holidays (Santo Antônio on June 13, the city anniversary on August 26, the state creation day on October 11) are computed for any year, so 2027 works. Closed holidays mean the store is closed. Optional days (Carnival, Corpus Christi, Christmas and New Year's Eve) produce a warning instead.

The sample orders are from early 2026, so a real clock would make every delivered order look old. `EMPORIO_NOW` pins the clock, and the example scenarios use it so the conversations are reproducible.

### Data notes

- Orders 3 and 20 have a `total_brl` that differs from the sum of their items. The agent reports the stored order total and does not alter it.
- Product 96 is out of stock. Product 136 is discontinued with 13 units in stock. Categories 6 to 8 have no products.
- Only four products have an active promotion; the rest of the promotions table is historical, and the agent never offers an inactive one.
- E-mails are matched case-insensitively. Phones are matched by digits only, ignoring a leading country code 55.

## Example conversations

Six scripted conversations are in [`examples/`](examples). The customer lines are fixed and the answers come from a live model (`gemini-3.5-flash-lite`). Each file shows the tool calls and a truncated tool result between the customer line and the reply. After each run, `run_examples.py` evaluates objective checks that must hold no matter how the model words its reply, and prints the result at the bottom of each file. In my run all six passed.

| File | What it shows | Checks |
|---|---|---|
| `01-promocao-e-pix.md` | Promotional guitar: price from the tool, no PIX discount, 12x instalments | Called `get_product`; answer has R$ 1.967,18; never shows the R$ 2.279,05 a PIX discount would give |
| `02-busca-por-faixa-de-preco.md` | Budget search then product detail | Called `search_products` and `get_product` |
| `03-status-do-pedido-com-verificacao.md` | Wrong e-mail first, then the right one | Tracking code never appears before verification, and does after |
| `04-devolucao-por-arrependimento-aprovada.md` | Regret return: general rule first, order checked, approved with the estimated-date notice | Called `check_return_eligibility` |
| `05-defeito-fora-do-prazo-escalado.md` | Defect claim past the 30-day store window but inside the 90-day legal warranty: escalated with a ticket | Called `check_return_eligibility` and `escalate_to_human`; answer has the ticket number |
| `06-fora-de-escopo-e-tentativas-de-manipulacao.md` | Weather question, prompt-leak attempt, fake 50% discount | No invented discount, no prompt leak, no escalation |

Examples 4 and 5 are the non-trivial ones: they use live order data and the manual's rules together, and the outcome depends on today's date.

## Known limitations

- **Free-tier models are slow and rate limited.** Expect occasional 429 or 503 errors; the adapter retries, then tells the customer to try again. Larger Gemini models were slower in my tests.
- **The model's wording is not deterministic.** The checks and the code guarantee the numbers and rules, not the phrasing. In example 5 the agent wrote "30 days since purchase" when the real number was 64. The meaning was right but the figure was loose. Tightening that would mean passing the exact number into the reply template or adding a post-check.
- **Keyword retrieval can miss synonyms.** A question phrased with words that are not in the manual may find nothing, and then the agent offers a human. For example "qual o CNPJ" does not reach section 1.2. Embeddings or a query rewrite step would help, at the cost of a dependency. A hit on a section intro pulls in its subsections, so "quanto tempo para devolver" does reach the 7-day rule in 4.1.
- **Combined payment is not implemented in code.** The manual allows PIX plus card above R$ 2.000 (3.1). The agent can explain it from the policy text but does not calculate it.
- **Last instalment rounding.** Instalments are the total divided by n, rounded to the cent, so some totals add up to a cent more or less than the price. The manual does not say how to round.
- **Session data is plain text.** `sessions/` holds order details and tickets with the customer's contact. It is git-ignored; a real deployment would need retention rules and encryption.
- **No order placement or payment.** The agent can explain, compare and escalate. It cannot take an order.
- **Shipping outside Campo Grande is informational.** There is no ZIP code price lookup.
- **One language per reply, one customer per process.** There is no authentication beyond order number plus contact, and sessions are local JSON files.
- **Evaluation is small.** Six scripted conversations and 141 tests cover the rules I could think of, including the boundary days of each window. There is no broad regression set against live models.

## Use of AI coding assistants

I built this with Claude (Anthropic) as the coding assistant, working step by step: data layer, pricing rules, catalog tools, order and return rules, policy search, agent loop, providers, example runner. Claude wrote most of the code and tests; I did not write it line by line. My part was directing the work and the product decisions, and testing it for real:

- I chose the business rules where the manual was ambiguous or contradictory (tiered instalments, selling discontinued stock, Campo Grande-only local delivery, estimated receipt date, keeping both phone numbers, holiday set).
- I ran the agent on my own machine (Windows) against the live API, and the fixes that came out of that are in the history: packaging for `pip install -e`, the missing time zone database on Windows, API key whitespace and `.env` loading, 503 and 429 behavior, and prompt corrections after reading real conversations.
- Claude's code was checked by the test suite, which uses a scripted fake client, a mocked HTTP transport for the provider adapter, and boundary tests for each rule in the manual. Behavior against live models was checked by me through the example scenarios.

- Before submitting I had three Claude review agents (code review, security audit, test review) read the whole repository, and checked it against the "ponytail" rule of writing the least code that works. What changed because of that: tool calls are restricted to the seven declared tools (the model could previously reach private methods by name); the verification lock is saved with the session and no longer resets on success; large instruments ship by the normal motoboy rule inside Campo Grande; a question like "quanto tempo para devolver" now reaches the 7-day rule; returns carry the manual's 4.4 warning; session ids are validated; the optional Anthropic SDK path was deleted because nothing required it; and 44 boundary tests were added.

The commit history shows the work in the order it happened, including the mistakes and their reverts.

## Project layout

```
emporio/
  agent.py       the loop, persistence, error handling
  prompt.py      system prompt and the per-turn clock block
  tools.py       tool definitions, dispatch, verification lock
  catalog.py     search and product detail, availability and promotions
  pricing.py     money, PIX, instalments, shipping
  orders.py      order status and return eligibility
  policies.py    BM25 search over the policy manual
  store.py       hours, holidays, contact data
  clock.py       store time zone and EMPORIO_NOW
  handoff.py     human hand-off tickets
  providers.py   Gemini / OpenAI-compatible client
  data.py        CSV to in-memory SQLite
  env.py         .env loader
  cli.py         terminal chat
data/            CSVs, the policy PDF and its Markdown conversion
scripts/         PDF extraction, example runner
examples/        generated example conversations
tests/           141 tests
```
