# insurers

Insurers the agency is appointed with, their products, and the premium calculator (ADR-0013).

- **Endpoints:**
  - `GET /jurisdiction-pack`;
  - `GET/POST /insurers`, `GET/PATCH /insurers/{id}`;
  - `GET/POST /products`, `GET/PUT /products/{id}` (If-Match);
  - `POST /premium/calculate` (one product);
  - `POST /premium/compare` (up to 8 products, cheapest first).
- **Products:** rating basis (rate on sum insured, flat, per member, manual), minimum premium, benefits
  (flat / % of sum insured / % of premium; optional, selected by default), member tiers, excess wording,
  commission rates (new and renewal).
- **Commission** is hidden (null) for members without `commission:read:own` or `commission:read:all`
  (assistants and viewers).
- **Permissions:** `insurer:read` (everyone), `insurer:manage` (owner, admin, accounts).
- **Service API for quotes (R1.3):** `calculate_product(ctx, product, risk)` returns the engine result and the
  API view.
