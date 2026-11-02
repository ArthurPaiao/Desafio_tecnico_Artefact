# Catalog search by category and budget

> A budget question must become a filtered search, not a guess from memory.

Store clock pinned to `2026-02-20T10:00` (America/Campo_Grande). Model: `gemini-3.5-flash-lite`.

**Customer:** Quero um violão de até R$ 1000, o que vocês têm?

    tool: search_products({"category": "violões", "max_price": 1000})
    result: {"total_found": 12, "products": [{"product_id": 83, "name": "Tagima Memphis AC-39 Nylon Natural", "category": "Violões", "availability": "available", "list_price": 429.9, "list_price_text": "R$ 429,90", "stock_quantity": 15}, {"product_id": 85, "name": "Rozini ...

**Tom:** Temos várias opções legais de violões até R$ 1000! Para te ajudar a escolher, você prefere cordas de nylon (mais macias) ou de aço (com aquele som mais brilhante)?

**Customer:** Me conta mais sobre o mais barato

    tool: get_product({"product_id": 83})
    result: {"product_id": 83, "name": "Tagima Memphis AC-39 Nylon Natural", "category": "Violões", "availability": "available", "list_price": 429.9, "list_price_text": "R$ 429,90", "stock_quantity": 15, "description": "Violão clássico com cordas de nylon, perfeito para q ...

**Tom:** O mais em conta é o Tagima Memphis AC-39 Nylon Natural, que sai por R$ 429,90. Ele é um violão clássico com cordas de nylon, ótimo para quem está começando, com corpo leve e bem confortável. No Pix tem 5% de desconto, saindo por R$ 408,41, ou você pode parcelar em até 5x sem juros de R$ 85,98. 

Quer saber mais sobre ele ou prefere ver outro modelo?

---
Automatic checks: all passed (4s)
