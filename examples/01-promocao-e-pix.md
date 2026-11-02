# Promotional product: price, no PIX discount, instalments

> The guitar is on promotion, so the PIX discount must not stack (manual 6.2). All numbers must come from the product tool.

Store clock pinned to `2026-02-20T10:00` (America/Campo_Grande). Model: `gemini-3.5-flash-lite`.

**Customer:** Quanto custa o violão Crafter HT-100?

    tool: get_product({"name": "Crafter HT-100"})
    result: {"product_id": 90, "name": "Crafter HT-100 Folk Aço Natural", "category": "Violões", "availability": "available", "list_price": 2399.0, "list_price_text": "R$ 2.399,00", "promotion": {"name": "Desconto Exclusivo", "discount_percent": 18.0, "promo_price": 1967. ...

**Tom:** O violão Crafter HT-100 Folk Aço Natural está saindo por R$ 1.967,18. Ele está com 18% de desconto sobre o valor original de R$ 2.399,00. 🎸

Como ele já está em promoção, o desconto de PIX não é cumulativo, mas você pode parcelar em até 12x sem juros no cartão. 

Posso te ajudar com mais alguma coisa?

**Customer:** E se eu pagar no PIX, tem desconto?

**Tom:** Como ele já está com preço promocional, o desconto de PIX não é cumulativo, infelizmente. O valor no PIX continua sendo R$ 1.967,18. 

Precisa de ajuda com mais alguma informação sobre ele?

**Customer:** Em quantas vezes posso parcelar?

**Tom:** Você pode parcelar em até 12x de R$ 163,93 sem juros no cartão de crédito. 💳

Precisa de mais alguma informação sobre o violão?

---
Automatic checks: all passed (5s)
