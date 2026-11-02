# Catalog search by category and budget

> A budget question must become a filtered search, not a guess from memory.

Store clock pinned to `2026-02-20T10:00` (America/Campo_Grande). Model: `gemini-3.5-flash-lite`.

**Customer:** Quero um violão de até R$ 1000, o que vocês têm?

    tool: search_products({"category": "violões", "max_price": 1000})
    result: {"total_found": 12, "products": [{"product_id": 83, "name": "Tagima Memphis AC-39 Nylon Natural", "category": "Violões", "availability": "available", "list_price": 429.9, "list_price_text": "R$ 429,90", "stock_quantity": 15}, {"product_id": 85, "name": "Rozini ...

**Tom:** Temos várias opções legais de violões até R$ 1.000! 

Olha alguns destaques que separei:
- Tagima Memphis AC-39 (Nylon): R$ 429,90
- Yamaha C40 (Nylon): R$ 599,90
- Giannini GF-1R (Aço Folk): R$ 579,90
- Yamaha F310 (Aço): R$ 699,90
- Tagima Dallas Tuner (Aço): R$ 749,00

Prefere cordas de nylon ou de aço?

**Customer:** Me conta mais sobre o mais barato

    tool: get_product({"product_id": 83})
    result: {"product_id": 83, "name": "Tagima Memphis AC-39 Nylon Natural", "category": "Violões", "availability": "available", "list_price": 429.9, "list_price_text": "R$ 429,90", "stock_quantity": 15, "description": "Violão clássico com cordas de nylon, perfeito para q ...

**Tom:** O Tagima Memphis AC-39 Nylon Natural custa R$ 429,90 (ou R$ 408,41 à vista no PIX). 

Ele é um violão clássico com cordas de nylon, muito recomendado para quem está começando, com corpo leve e confortável. Dá para parcelar em até 5x sem juros de R$ 85,98 no cartão de crédito. Temos 15 unidades em estoque! 🎵

Quer saber o frete para a sua cidade ou precisa de mais alguma informação sobre ele?

---
Automatic checks: all passed (4s)
